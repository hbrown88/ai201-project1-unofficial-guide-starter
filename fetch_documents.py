"""
Milestone 3 (step 0) — Fetch RAW documents from the source URLs.

The Documents table in planning.md lists web sources (GT Engage, the campus
calendar, CRC, SCPC, r/gatech, Discover Atlanta, ...). This script scrapes each
URL and saves the *raw, uncleaned* response into a new folder (documents/raw/).

Why a separate fetch step:
    Cleaning and chunking (ingest.py) should be reproducible and offline. By
    snapshotting the raw page text to disk first, you can re-run / tweak the
    cleaning logic as many times as you want WITHOUT re-hitting the network
    (and without your chunks changing because a live page updated).

What "consistent format" means here:
    - one file per source, named  NN_slug.<ext>  (ext from the content type)
    - the file holds the raw response body, exactly as returned (no cleaning)
    - documents/raw/sources.json   maps each saved file -> its URL
      (ingest.py reads this for source attribution)
    - documents/raw/manifest.json  records the full fetch result for every
      source (url, status, bytes, content type, timestamp, ok/error)

Run:
    python fetch_documents.py
Then clean + chunk the raw snapshots:
    python ingest.py --docs-dir documents/raw

Notes:
    - Uses only the Python standard library (urllib) — no extra installs.
    - Some sources block automated requests (Reddit and the JS-rendered GT
      Engage pages are the usual offenders). Those are reported as failures;
      for any that fail, just open the page in a browser, Save As, and drop the
      file into documents/raw/ manually — ingest.py will pick it up.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# -----------------------------------------------------------------------------
# Source list, derived from the planning.md Documents table.
# Multi-URL cells are expanded into separate entries (e.g. Engage orgs + events,
# Career Center workshops + career fair) so each page is fetched on its own.
# -----------------------------------------------------------------------------
SOURCES: list[tuple[str, str]] = [
    # 1  r/gatech — student voice (Reddit's .json endpoint is the scrapable one)
    ("reddit_gatech", "https://www.reddit.com/r/gatech/.json?limit=75"),
    # 2  GT Engage — orgs directory + event listings
    ("gt_engage_orgs", "https://gatech.campuslabs.com/engage/organizations"),
    ("gt_engage_events", "https://gatech.campuslabs.com/engage/events"),
    # 3  Georgia Tech campus calendar
    ("gt_campus_calendar", "https://calendar.gatech.edu/event/listings"),
    # 4  Student Center Programs Council
    ("scpc", "https://studentcenter.gatech.edu/scpc"),
    # 5  Campus Recreation programs
    ("crc_programs", "https://crc.gatech.edu/programs/"),
    # 6  Career Center workshops + career fair
    ("career_workshops", "https://career.gatech.edu/workshops/"),
    ("career_fair", "https://careerfair.gatech.edu/"),
    # 7  Georgia Tech Arts (Ferst Center) events
    ("gt_arts_events", "https://arts.gatech.edu/events"),
    # 8  Center for Student Engagement
    ("student_engagement", "https://studentengagement.gatech.edu/"),
    # 9  Ramblin' Wreck athletics
    ("ramblin_wreck", "https://ramblinwreck.com/"),
    # 10 Discover Atlanta events
    ("discover_atlanta_events", "https://discoveratlanta.com/events/all/"),
]

# A real-ish User-Agent; many sites reject the default Python urllib agent.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
        "unofficial-guide-coursework/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Map response content type -> file extension, so the raw store is consistent
# and ingest.py routes each file to the right cleaner.
_EXT_BY_TYPE = {
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "application/json": ".json",
    "text/plain": ".txt",
}


def _ext_for(content_type: str) -> str:
    return _EXT_BY_TYPE.get(content_type, ".txt")


def fetch(url: str, timeout: int, retries: int) -> tuple[str, str, int]:
    """Return (raw_text, content_type, status) for a URL, retrying on failure."""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get_content_type()
                charset = resp.headers.get_content_charset() or "utf-8"
                raw = resp.read().decode(charset, errors="replace")
                return raw, content_type, resp.status
        except urllib.error.HTTPError as exc:
            # 4xx/5xx — usually a hard block (403) or missing page; don't retry.
            raise RuntimeError(f"HTTP {exc.code} {exc.reason}") from exc
        except Exception as exc:  # timeout, DNS, connection reset, etc.
            last_err = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_err))


# -----------------------------------------------------------------------------
# API-based fetchers.
# GT Engage (orgs + events) and the campus calendar render their content with
# JavaScript, so a plain GET returns an empty shell. Their data is available as
# JSON from the Anthology/CampusLabs discovery API; we pull it directly and emit
# clean, attributable text (one block per org/event, with its own deep link).
# -----------------------------------------------------------------------------
ENGAGE_BASE = "https://gatech.campuslabs.com/engage"


def _api_get(url: str, timeout: int) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset, errors="replace"))


def _clean_field(s: str) -> str:
    """Strip HTML tags + decode entities from an API description field."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _fmt_when(starts: str, ends: str) -> str:
    """Render ISO start/end timestamps in US Eastern, human-readable."""
    try:
        from zoneinfo import ZoneInfo

        et = ZoneInfo("America/New_York")
        s = datetime.fromisoformat(starts).astimezone(et)
        e = datetime.fromisoformat(ends).astimezone(et)
        if s.date() == e.date():
            return s.strftime("%A, %B %d, %Y, %I:%M %p") + e.strftime(" - %I:%M %p ET")
        return s.strftime("%A, %B %d, %Y %I:%M %p") + e.strftime(
            " to %A, %B %d, %Y %I:%M %p ET"
        )
    except Exception:
        return f"{starts} to {ends}".strip(" to")


def fetch_engage_orgs(timeout: int, retries: int) -> tuple[str, str]:
    """Pull the full registered-organization directory from the Engage API."""
    collected: list[dict] = []
    skip, top = 0, 500
    while True:
        url = (
            f"{ENGAGE_BASE}/api/discovery/search/organizations?"
            f"orderBy%5B0%5D=UpperName%20asc&top={top}&skip={skip}"
        )
        data = _api_get(url, timeout)
        batch = data.get("value", [])
        collected.extend(batch)
        skip += top
        if not batch or skip >= data.get("@odata.count", len(collected)):
            break

    # No directory-wide header line: a "...718 Registered Student Organizations"
    # banner becomes a chunk that is magnetically similar to every "student org"
    # query, crowding out the specific org the user actually wants.
    lines: list[str] = []
    for o in collected:
        name = (o.get("Name") or "").strip()
        short = (o.get("ShortName") or "").strip()
        cats = ", ".join(o.get("CategoryNames") or [])
        body = (o.get("Summary") or "").strip() or _clean_field(o.get("Description"))
        key = o.get("WebsiteKey") or ""
        link = f"{ENGAGE_BASE}/organization/{key}" if key else f"{ENGAGE_BASE}/organizations"
        head = name + (f" ({short})" if short and short.lower() != name.lower() else "")
        block = [head]
        if cats:
            block.append(f"Categories: {cats}")
        if body:
            block.append(body)
        block.append(f"More info: {link}")
        lines.append("\n".join(block))
        lines.append("")
    return "\n".join(lines), ".txt"


def fetch_engage_events(timeout: int, retries: int) -> tuple[str, str]:
    """Pull upcoming approved campus events from the Engage API."""
    from urllib.parse import quote

    now_dt = datetime.now(timezone.utc)
    # Use a 'Z' suffix (not '+00:00') and URL-quote it: a literal '+' in a query
    # string decodes to a space, which silently voids the endsAfter filter.
    now = quote(now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    url = (
        f"{ENGAGE_BASE}/api/discovery/event/search?endsAfter={now}"
        f"&orderByField=endsOn&orderByDirection=ascending&status=Approved&take=300"
    )
    events = _api_get(url, timeout).get("value", [])

    # Belt-and-suspenders: keep only genuinely upcoming events, earliest first,
    # in case the server-side filter is ever ignored again.
    def _ends_after_now(e: dict) -> bool:
        try:
            return datetime.fromisoformat(e.get("endsOn", "")) >= now_dt
        except Exception:
            return False

    events = sorted(
        (e for e in events if _ends_after_now(e)),
        key=lambda e: e.get("startsOn", ""),
    )
    lines: list[str] = []  # no global header (see fetch_engage_orgs)
    for e in events:
        name = (e.get("name") or "").strip()
        org = (e.get("organizationName") or "").strip()
        loc = (e.get("location") or "").strip()
        theme = (e.get("theme") or "").strip()
        cats = ", ".join(e.get("categoryNames") or [])
        desc = _clean_field(e.get("description"))
        link = f"{ENGAGE_BASE}/event/{e.get('id')}" if e.get("id") else f"{ENGAGE_BASE}/events"
        block = [name + (f" - hosted by {org}" if org else "")]
        block.append(f"When: {_fmt_when(e.get('startsOn', ''), e.get('endsOn', ''))}")
        if loc:
            block.append(f"Where: {loc}")
        tags = "; ".join(t for t in [f"Theme: {theme}" if theme else "",
                                     f"Categories: {cats}" if cats else ""] if t)
        if tags:
            block.append(tags)
        if desc:
            block.append(desc)
        block.append(f"More info: {link}")
        lines.append("\n".join(block))
        lines.append("")
    return "\n".join(lines), ".txt"


# Sources whose name maps to a custom fetcher instead of a plain GET.
FETCHERS = {
    "gt_engage_orgs": fetch_engage_orgs,
    "gt_engage_events": fetch_engage_events,
}


def load_sources(sources_json: str | None) -> list[tuple[str, str]]:
    """Use the built-in SOURCES, or an override file (JSON list or object)."""
    if not sources_json:
        return SOURCES
    data = json.loads(Path(sources_json).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.items())
    return [(name, url) for name, url in data]


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch raw source documents (Milestone 3).")
    ap.add_argument("--out-dir", default="documents/raw", help="folder for raw files")
    ap.add_argument("--timeout", type=int, default=30, help="per-request timeout (s)")
    ap.add_argument("--retries", type=int, default=2, help="retries per URL")
    ap.add_argument("--delay", type=float, default=1.0, help="pause between requests (s)")
    ap.add_argument("--limit", type=int, default=0, help="fetch only first N (0 = all)")
    ap.add_argument("--sources-json", help="optional override list of [name, url]")
    args = ap.parse_args()

    sources = load_sources(args.sources_json)
    if args.limit > 0:
        sources = sources[: args.limit]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    file_to_url: dict[str, str] = {}
    ok_count = 0

    print(f"Fetching {len(sources)} source(s) into {out_dir}/ ...\n")
    for i, (name, url) in enumerate(sources, start=1):
        record = {
            "name": name,
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ok": False,
        }
        try:
            if name in FETCHERS:  # JSON-API source -> clean text
                raw, ext = FETCHERS[name](args.timeout, args.retries)
                content_type, status = "application/json (api)", 200
                filename = f"{i:02d}_{name}{ext}"
            else:
                raw, content_type, status = fetch(url, args.timeout, args.retries)
                filename = f"{i:02d}_{name}{_ext_for(content_type)}"
            (out_dir / filename).write_text(raw, encoding="utf-8")
            record.update(
                ok=True,
                file=filename,
                status=status,
                content_type=content_type,
                bytes=len(raw.encode("utf-8")),
            )
            file_to_url[filename] = url
            ok_count += 1
            print(f"  [{i:02d}/{len(sources)}] OK    {name:<24} {len(raw):>8} chars  -> {filename}")
        except Exception as exc:
            record.update(error=str(exc))
            print(f"  [{i:02d}/{len(sources)}] FAIL  {name:<24} {exc}")

        manifest.append(record)
        if args.delay and i < len(sources):
            time.sleep(args.delay)

    # Preserve attribution for files saved by an earlier run that weren't
    # (re)fetched now — the raw store accumulates, so a source that is
    # temporarily unreachable (e.g. an intermittent 403) shouldn't lose its URL.
    smap = out_dir / "sources.json"
    if smap.exists():
        try:
            for fn, u in json.loads(smap.read_text(encoding="utf-8")).items():
                if fn not in file_to_url and (out_dir / fn).exists():
                    file_to_url[fn] = u
        except json.JSONDecodeError:
            pass

    # sources.json — consumed by ingest.py for source attribution.
    smap.write_text(json.dumps(file_to_url, indent=2), encoding="utf-8")
    # manifest.json — full fetch log (successes and failures).
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    failed = len(sources) - ok_count
    print(f"\nSaved {ok_count}/{len(sources)} raw documents to {out_dir}/")
    if failed:
        names = [r["name"] for r in manifest if not r["ok"]]
        print(
            f"  {failed} source(s) could not be fetched: {', '.join(names)}\n"
            "  Open those pages in a browser, Save As (.html), drop them into\n"
            f"  {out_dir}/, and add their URLs to {out_dir}/sources.json."
        )
    print(f"\nNext: python ingest.py --docs-dir {out_dir}")


if __name__ == "__main__":
    main()
