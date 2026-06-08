"""
Milestone 3 — Document ingestion and chunking for "The Unofficial Guide".

This script implements the first two stages of the pipeline in planning.md:

    [ DOCUMENT INGEST ] -> [ CHUNKING ] -> (Milestone 4: embedding + vector store)

It reads the source documents you saved into documents/ (the GT Engage, campus
calendar, CRC, SCPC, r/gatech, Discover Atlanta, etc. pages from the Documents
table), strips their markup/boilerplate, and splits them into overlapping chunks
sized for the all-MiniLM-L6-v2 embedding model.

Chunking Strategy (from planning.md):
    - chunk size : 150-200 tokens
    - overlap    : 50 tokens
    - rationale  : each source is mostly a short event/org TITLE plus a small
                   description, so a ~150-200 token window keeps one listing
                   (and its link) together in a single chunk.

Tokens are counted with the *same* tokenizer the embedding model uses
(sentence-transformers/all-MiniLM-L6-v2), so the 150-200 token target matches
what actually gets embedded — and stays well under that model's 256-token limit.

How to provide documents
-------------------------
Drop one file per source into documents/ using any of these types:
    .html / .htm   saved web pages (GT Engage, calendar, CRC, ...)
    .txt  / .md    pasted text or notes
    .json          structured dumps (e.g. a Reddit thread export)
    .pdf           requires `pip install pdfplumber`

Source links (for attribution in later milestones) are resolved in this order:
    1. documents/sources.json  -> {"crc.html": "https://crc.gatech.edu/programs/"}
    2. a leading "Source:" / "URL:" line inside a .txt/.md file
    3. a <link rel="canonical"> or <title> inside an .html file
    4. the file name itself

Run:
    python ingest.py
Output:
    chunks.json   a list of {id, source, text, token_count} ready for Milestone 4
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from pathlib import Path

# --- Chunking parameters (from planning.md > Chunking Strategy) ---------------
MAX_TOKENS = 200      # upper bound of the 150-200 token window
MIN_TOKENS = 150      # soft lower bound; a tiny tail chunk is merged back
OVERLAP_TOKENS = 50   # shared context carried between consecutive chunks

SUPPORTED_EXTS = {".html", ".htm", ".txt", ".md", ".json", ".pdf"}

# Directory-style sources (one short record per blank-line block, e.g. the
# Engage org/event API pulls) are chunked one-record-per-chunk instead of being
# packed to 150-200 tokens — so each org/event embeds as its own vector and a
# specific query (e.g. "photography club") matches it precisely.
_RECORD_SOURCES = ("campuslabs.com/engage", "eventbrite.com")

# HTML tags that imply a line/paragraph break when stripped to plain text.
_BLOCK_TAGS = {
    "p", "br", "div", "li", "ul", "ol", "tr", "table", "h1", "h2", "h3",
    "h4", "h5", "h6", "section", "article", "header", "footer", "nav",
}

# Void (self-closing) elements — they never have a matching end tag.
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

# Whole subtrees whose text is chrome, not content — dropped entirely.
_DROP_TAGS = {
    "script", "style", "noscript", "template", "svg", "iframe", "form",
    "button", "select", "option", "nav", "aside", "footer", "dialog",
}

# Content-root tags are never dropped by class/role heuristics — theme layout
# classes on <body> (e.g. "has-sidebar", "events-template") would otherwise nuke
# the whole page.
_ROOT_TAGS = {"html", "body", "main", "article"}

# ARIA landmark roles that precisely mark non-content regions.
_DROP_ROLES = {
    "navigation", "banner", "contentinfo", "complementary", "search",
    "dialog", "menu", "menubar", "toolbar", "alert",
}

# class / id tokens that mark boilerplate containers (cookie bars, share bars,
# sidebars, comment widgets, ads, pagination, ...). Matched against the element's
# class+id string with token boundaries so "site-header"/"c-nav__list" both hit.
_DROP_CLASS_RE = re.compile(
    r"(?:^|[-_ ])(?:"
    r"nav(?:bar|igation)?|menu|breadcrumbs?|masthead|toolbar|"
    r"(?:site|global|page)-?header|(?:site|global|page)-?footer|footer|"
    r"cookie\w*|consent|gdpr|"
    r"advert\w*|adsense|ad-(?:slot|unit|container|wrapper|box|banner)|"
    r"google-?ads?|sponsor\w*|promo|"
    r"share\w*|social\w*|"
    r"subscribe|newsletter|sign-?up|"
    r"sign-?in|log-?in|login|signin|account|"
    r"search|"
    r"modal|popup|pop-?up|overlay|lightbox|"
    r"sidebar|widget|"
    r"related|recommend\w*|read-?more|"
    r"comments?|"
    r"pagination|pager|"
    r"skip-?(?:link|nav|to|content)|"
    r"screen-?reader|sr-only|visually-hidden|"
    r"back-?to-?top"
    r")(?:[-_ ]|$)",
    re.IGNORECASE,
)

# Whole lines that are UI labels / boilerplate rather than substantive content.
_BOILERPLATE_LINE_RE = re.compile(
    r"^(?:"
    r"read more|learn more|get started|view details|continue reading|"
    r"show (?:more|less)|load more|view (?:more|all)[\w ]*|see (?:more|all)[\w ]*|"
    r"share(?: this)?(?: on \w+)?|tweet|pin it|email this|print|"
    r"facebook|twitter|instagram|linkedin|youtube|tiktok|"
    r"subscribe[\w ]*|newsletter[\w ]*|sign ?up[\w ]*|"
    r"log ?in|sign ?in|register|create (?:an )?account|my account|"
    r"menu|main menu|navigation|skip to (?:main )?content|search|"
    r"(?:accept|manage)(?: all)?(?: cookies)?|we use cookies.*|"
    r"this (?:site|website) uses cookies.*|cookie (?:policy|preferences|settings|notice)|"
    r"privacy policy|terms(?: of (?:use|service))?(?: & conditions)?|"
    r"all rights reserved.*|copyright.*|©.*|"
    r"back to top|add to(?: \w+)? calendar|"
    r"follow (?:us|@?[\w.]+)(?: on .*)?|"
    r"@[\w.]+(?: (?:instagram|twitter|facebook|tiktok|youtube|x))?|"
    r"\d+ comments?|\d+ min(?:ute)? read|"
    r"previous(?: page)?|next(?: page)?|page \d+ of \d+|"
    r"home|about|contact(?: us)?|donate|give|apply|visit"
    r")\.?$",
    re.IGNORECASE,
)

# Documents shorter than this after cleaning are treated as empty (e.g. the
# JavaScript-rendered Engage shells that carry no real text in their HTML).
MIN_DOC_CHARS = 50


# =============================================================================
# Token counting — uses the all-MiniLM-L6-v2 tokenizer so chunk sizes match
# what the embedding model in Milestone 4 will actually see.
# =============================================================================
_tokenizer = None
_tokenizer_loaded = False


def _get_tokenizer():
    """Lazily load the embedding model's tokenizer (None if unavailable)."""
    global _tokenizer, _tokenizer_loaded
    if not _tokenizer_loaded:
        _tokenizer_loaded = True
        try:
            from transformers import AutoTokenizer

            _tokenizer = AutoTokenizer.from_pretrained(
                "sentence-transformers/all-MiniLM-L6-v2"
            )
        except Exception as exc:  # offline / not installed -> word-based fallback
            print(f"  (tokenizer unavailable: {exc}; using word-count estimate)")
            _tokenizer = None
    return _tokenizer


def count_tokens(text: str) -> int:
    """Number of tokens in `text` per the embedding model's tokenizer."""
    tok = _get_tokenizer()
    if tok is not None:
        return len(tok.encode(text, add_special_tokens=False))
    # Fallback: ~1.3 sub-word tokens per whitespace word.
    return max(1, round(len(text.split()) * 1.3))


# =============================================================================
# Document loading + cleaning
# =============================================================================
@dataclass
class Document:
    source: str   # URL or human-readable origin, used for attribution later
    text: str     # cleaned plain text


class _ContentExtractor(HTMLParser):
    """Extract substantive text from HTML, dropping whole chrome subtrees.

    Maintains a tag-depth stack. When a start tag is identified as boilerplate
    (by tag name, ARIA role, or class/id), everything until its matching end
    tag is suppressed — so a <nav>, cookie banner, or comments widget and all
    of its descendants are removed, not just the wrapper tag.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []           # open (non-void) tags
        self._drop_depth: int | None = None  # stack len where a dropped region began
        self._in_title = False
        self.title: str | None = None
        self.canonical: str | None = None

    def _should_drop(self, tag, attrs) -> bool:
        if tag in _DROP_TAGS:
            return True
        # Drop a page-level <header> (site banner) but keep article/section headers.
        if tag == "header" and (not self.stack or self.stack[-1] in ("body", "html")):
            return True
        if tag in _ROOT_TAGS:  # never drop a content root by its attributes
            return False
        d = dict(attrs)
        if (d.get("role") or "").strip().lower() in _DROP_ROLES:
            return True
        if (d.get("aria-hidden") or "").lower() == "true":
            return True
        blob = f"{d.get('class') or ''} {d.get('id') or ''}".strip()
        if blob and _DROP_CLASS_RE.search(blob):
            return True
        return False

    def handle_starttag(self, tag, attrs):
        if tag == "link":
            d = dict(attrs)
            if "canonical" in (d.get("rel") or "") and d.get("href"):
                self.canonical = d["href"]
        if tag in _VOID_TAGS:
            if tag == "br" and self._drop_depth is None:
                self.parts.append("\n")
            return
        if tag == "title":
            self._in_title = True
        if self._drop_depth is None and self._should_drop(tag, attrs):
            self._drop_depth = len(self.stack)
        self.stack.append(tag)
        if self._drop_depth is None and tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        # Self-closing tag (<br/>, <img/>, ...): emit a break but never push.
        if tag == "link":
            d = dict(attrs)
            if "canonical" in (d.get("rel") or "") and d.get("href"):
                self.canonical = d["href"]
        if self._drop_depth is None and tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        if tag == "title":
            self._in_title = False
        if tag in self.stack:  # pop down to the matching tag (tolerates bad nesting)
            while self.stack:
                popped = self.stack.pop()
                if self._drop_depth is not None and len(self.stack) <= self._drop_depth:
                    self._drop_depth = None
                if popped == tag:
                    break
        if self._drop_depth is None and tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data
        if self._drop_depth is None:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces/blank lines so chunking sees clean structure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Exotic spaces (nbsp, thin/figure/ideographic) -> plain space; strip
    # zero-width characters and soft hyphens that leave invisible gaps.
    text = re.sub(r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]", " ", text)
    text = re.sub(r"[\u200b-\u200d\ufeff\u00ad]", "", text)
    # Trim trailing/leading spaces on each line.
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    # Collapse 3+ newlines into a paragraph break.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_boilerplate_lines(text: str) -> str:
    """Drop UI-label lines (Read more, Share, cookie notices, ...) and junk."""
    kept: list[str] = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            kept.append("")
            continue
        if not re.search(r"[A-Za-z0-9]", s):   # bullets / arrows / separators
            continue
        if _BOILERPLATE_LINE_RE.match(s):
            continue
        kept.append(s)
    return "\n".join(kept)


def _json_strings(node, out: list[str]) -> None:
    """Recursively pull human-readable strings out of arbitrary JSON."""
    if isinstance(node, dict):
        for value in node.values():
            _json_strings(value, out)
    elif isinstance(node, list):
        for item in node:
            _json_strings(item, out)
    elif isinstance(node, str):
        s = node.strip()
        if len(s) > 1 and not s.startswith(("http://", "https://", "/")):
            out.append(s)


def clean_text(raw: str, ext: str) -> tuple[str, str | None]:
    """Return (clean_text, embedded_source_or_None) for one raw file."""
    embedded_source: str | None = None

    if ext in (".html", ".htm"):
        parser = _ContentExtractor()
        parser.feed(raw)
        embedded_source = parser.canonical or (
            parser.title.strip() if parser.title else None
        )
        text = parser.text()

    elif ext == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
        # Common Reddit-style fields, then any leftover strings.
        pieces: list[str] = []
        if isinstance(data, dict):
            embedded_source = data.get("url") or data.get("permalink")
        _json_strings(data, pieces)
        text = "\n".join(pieces)

    else:  # .txt / .md / .pdf (already plain text)
        text = raw
        # Honor a leading "Source:" / "URL:" line for attribution.
        head = raw.lstrip().split("\n", 1)[0].strip()
        m = re.match(r"(?:source|url)\s*[:\-]\s*(\S+)", head, re.IGNORECASE)
        if m:
            embedded_source = m.group(1)
            text = raw.split("\n", 1)[1] if "\n" in raw else ""

    text = _strip_boilerplate_lines(_normalize_whitespace(text))
    return _normalize_whitespace(text), embedded_source


def _read_raw(path: Path, ext: str) -> str | None:
    """Read a file to text, or None if it can't be read."""
    if ext == ".pdf":
        try:
            import pdfplumber
        except ImportError:
            print(f"  skipping {path.name}: install pdfplumber to read PDFs")
            return None
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def _remove_cross_doc_boilerplate(
    documents: list[Document], min_ratio: float = 0.5
) -> list[Document]:
    """Drop lines that repeat across many documents (shared header/footer/nav).

    A line appearing (verbatim) in at least `min_ratio` of the documents is
    almost certainly site chrome — the Georgia Tech global nav/footer shows up
    on every gatech.edu page — so it is removed from all of them.
    """
    from collections import Counter
    from math import ceil

    if len(documents) < 3:
        return documents

    doc_freq: Counter = Counter()
    for doc in documents:
        for line in {ln.strip() for ln in doc.text.split("\n") if ln.strip()}:
            doc_freq[line] += 1

    threshold = max(3, ceil(min_ratio * len(documents)))
    boilerplate = {ln for ln, n in doc_freq.items() if n >= threshold}
    if not boilerplate:
        return documents

    print(f"  removing {len(boilerplate)} cross-page boilerplate line(s)")
    cleaned: list[Document] = []
    for doc in documents:
        lines = [ln for ln in doc.text.split("\n") if ln.strip() not in boilerplate]
        cleaned.append(
            Document(source=doc.source, text=_normalize_whitespace("\n".join(lines)))
        )
    return cleaned


def load_documents(docs_dir: str | Path) -> list[Document]:
    """Load and clean every supported file in `docs_dir`."""
    docs_dir = Path(docs_dir)
    source_map: dict[str, str] = {}
    smap_path = docs_dir / "sources.json"
    if smap_path.exists():
        try:
            source_map = json.loads(smap_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("  warning: documents/sources.json is not valid JSON; ignoring")

    # Metadata files written by fetch_documents.py — not documents to chunk.
    reserved = {"sources.json", "manifest.json"}
    documents: list[Document] = []
    for path in sorted(docs_dir.rglob("*")):
        if path.is_dir() or path.name in reserved or path.name.startswith("."):
            continue
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            continue
        raw = _read_raw(path, ext)
        if raw is None:
            continue
        text, embedded_source = clean_text(raw, ext)
        if len(text.strip()) < MIN_DOC_CHARS:
            print(f"  skipping {path.name}: no substantive text after cleaning")
            continue
        source = source_map.get(path.name) or embedded_source or path.stem
        documents.append(Document(source=source, text=text))

    documents = _remove_cross_doc_boilerplate(documents)
    # A document can fall below the content threshold once shared chrome is gone.
    return [d for d in documents if len(d.text.strip()) >= MIN_DOC_CHARS]


# =============================================================================
# Chunking — sentence/line aware packing with token-level overlap.
# =============================================================================
def _segments(text: str) -> list[str]:
    """Split text into atomic units (one listing line / sentence each)."""
    out: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            for sentence in re.split(r"(?<=[.!?])\s+", line):
                sentence = sentence.strip()
                if sentence:
                    out.append(sentence)
    return out


def _hard_split(text: str, max_tokens: int, overlap: int) -> list[str]:
    """Token-window a single oversized segment so no chunk exceeds max_tokens."""
    tok = _get_tokenizer()
    if tok is not None:
        ids = tok.encode(text, add_special_tokens=False)
        step = max(1, max_tokens - overlap)
        pieces = []
        for start in range(0, len(ids), step):
            window = ids[start : start + max_tokens]
            if not window:
                break
            pieces.append(tok.decode(window).strip())
            if start + max_tokens >= len(ids):
                break
        return [p for p in pieces if p]
    # Fallback: word windows approximating the token budget.
    words = text.split()
    size = max(1, int(max_tokens / 1.3))
    step = max(1, int((max_tokens - overlap) / 1.3))
    pieces = []
    for start in range(0, len(words), step):
        window = words[start : start + size]
        if not window:
            break
        pieces.append(" ".join(window))
        if start + size >= len(words):
            break
    return pieces


def _overlap_tail(
    current: list[tuple[str, int]], overlap: int, next_tok: int, max_tokens: int
) -> tuple[list[tuple[str, int]], int]:
    """Build the ~`overlap`-token seed carried into the next chunk.

    Trims from the front so the next segment is still guaranteed to fit,
    which keeps the packing loop from stalling.
    """
    tail: list[tuple[str, int]] = []
    total = 0
    for seg, t in reversed(current):
        if total + t > overlap and tail:
            break
        tail.insert(0, (seg, t))
        total += t
    while tail and total + next_tok > max_tokens:
        seg, t = tail.pop(0)
        total -= t
    return tail, total


def chunk_text(
    text: str,
    max_tokens: int = MAX_TOKENS,
    overlap: int = OVERLAP_TOKENS,
    min_tokens: int = MIN_TOKENS,
) -> list[str]:
    """Split `text` into overlapping chunks of <= max_tokens tokens.

    Packs whole sentences/listing-lines together (so a single event title +
    description stays intact) and carries ~`overlap` tokens of context into the
    next chunk. Segments longer than max_tokens are token-windowed.
    """
    # Expand segments, hard-splitting any that are individually too large.
    units: list[tuple[str, int]] = []
    for seg in _segments(text):
        t = count_tokens(seg)
        if t <= max_tokens:
            units.append((seg, t))
        else:
            for piece in _hard_split(seg, max_tokens, overlap):
                units.append((piece, count_tokens(piece)))

    chunks: list[str] = []
    current: list[tuple[str, int]] = []
    current_tokens = 0
    i = 0
    while i < len(units):
        seg, t = units[i]
        if not current or current_tokens + t <= max_tokens:
            current.append((seg, t))
            current_tokens += t
            i += 1
        else:
            chunks.append(" ".join(s for s, _ in current))
            current, current_tokens = _overlap_tail(current, overlap, t, max_tokens)

    if current:
        tail_text = " ".join(s for s, _ in current)
        # Merge a too-small final chunk back into the previous one if it fits.
        if (
            chunks
            and current_tokens < min_tokens
            and count_tokens(chunks[-1] + " " + tail_text) <= max_tokens
        ):
            chunks[-1] = chunks[-1] + " " + tail_text
        else:
            chunks.append(tail_text)

    return chunks


def chunk_records(
    text: str,
    max_tokens: int = MAX_TOKENS,
    overlap: int = OVERLAP_TOKENS,
    min_tokens: int = MIN_TOKENS,  # unused; kept for a common chunker signature
) -> list[str]:
    """One chunk per blank-line-separated record (directory-style sources).

    Each org/event block stays atomic so it embeds as its own vector; only a
    record longer than max_tokens is token-windowed. Records are intentionally
    allowed to fall below the 150-token target — precision matters more than
    size for a lookup directory.
    """
    chunks: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = " ".join(block.split())
        if not block:
            continue
        if count_tokens(block) <= max_tokens:
            chunks.append(block)
        else:
            chunks.extend(_hard_split(block, max_tokens, overlap))
    return chunks


# =============================================================================
# Assembly + CLI
# =============================================================================
def _slug(text: str) -> str:
    slug = re.sub(r"^https?://", "", text)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-").lower()
    return slug[:40] or "doc"


def build_chunks(documents: list[Document], **kwargs) -> list[dict]:
    """Turn loaded documents into id/source/position/text/token_count records.

    `position` is the chunk's 0-based index within its source document — kept as
    explicit metadata so the vector store can attribute and order results later.
    """
    records: list[dict] = []
    for doc in documents:
        record_style = any(s in doc.source for s in _RECORD_SOURCES)
        chunker = chunk_records if record_style else chunk_text
        for idx, chunk in enumerate(chunker(doc.text, **kwargs)):
            records.append(
                {
                    "id": f"{_slug(doc.source)}__{idx:04d}",
                    "source": doc.source,
                    "position": idx,
                    "text": chunk,
                    "token_count": count_tokens(chunk),
                }
            )
    return records


def _print_summary(documents: list[Document], chunks: list[dict]) -> None:
    print(f"\nLoaded {len(documents)} document(s) -> {len(chunks)} chunk(s)")
    if not chunks:
        return
    counts = [c["token_count"] for c in chunks]
    in_range = sum(1 for c in counts if MIN_TOKENS <= c <= MAX_TOKENS)
    print(
        f"  token counts: min={min(counts)} "
        f"median={int(statistics.median(counts))} max={max(counts)}"
    )
    print(
        f"  {in_range}/{len(chunks)} chunks within the "
        f"{MIN_TOKENS}-{MAX_TOKENS} token target "
        f"({in_range / len(chunks):.0%})"
    )
    sample = chunks[0]
    preview = sample["text"][:200] + ("..." if len(sample["text"]) > 200 else "")
    print(f"\n  sample chunk [{sample['id']}] ({sample['token_count']} tokens)")
    print(f"  source: {sample['source']}")
    print(f"  text  : {preview}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest + chunk documents (Milestone 3).")
    ap.add_argument("--docs-dir", default="documents", help="folder of source files")
    ap.add_argument("--out", default="chunks.json", help="output JSON path")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--min-tokens", type=int, default=MIN_TOKENS)
    ap.add_argument("--overlap", type=int, default=OVERLAP_TOKENS)
    args = ap.parse_args()

    docs_dir = Path(args.docs_dir)
    if not docs_dir.exists():
        print(f"No '{docs_dir}/' folder found. Create it and add your sources.")
        return

    print(f"Loading documents from {docs_dir}/ ...")
    documents = load_documents(docs_dir)
    if not documents:
        print(
            f"\nNo readable documents in {docs_dir}/.\n"
            "Save each source from your planning.md Documents table as a\n"
            ".html/.txt/.md/.json/.pdf file in that folder (optionally add a\n"
            "documents/sources.json mapping filenames to their URLs), then re-run."
        )
        return

    chunks = build_chunks(
        documents,
        max_tokens=args.max_tokens,
        overlap=args.overlap,
        min_tokens=args.min_tokens,
    )

    Path(args.out).write_text(json.dumps(chunks, indent=2, ensure_ascii=False))
    _print_summary(documents, chunks)
    print(f"\nWrote {len(chunks)} chunks to {args.out}")


if __name__ == "__main__":
    main()
