"""
Milestone 5 — Grounded generation for "The Unofficial Guide".

Final stage of the planning.md pipeline:

    ... [ RETRIEVAL ] -> [ GENERATION ] -> [ AI Response ]
          top-k chunks     Groq / Llama-3.3-70b    answer + sources

generate_answer(query):
    1. retrieve the top-k chunks for the query (embed.retrieve)
    2. if nothing clears the relevance floor, return the refusal string WITHOUT
       calling the LLM — no context means no chance to hallucinate
    3. otherwise build a context block and ask Groq's llama-3.3-70b-versatile to
       answer using ONLY that context
    4. append the source URLs PROGRAMMATICALLY from the retrieved chunks — source
       attribution is guaranteed by code, never left to the model to invent

Grounding is enforced three ways, not merely suggested:
    - structural: no relevant chunks -> hard-coded refusal, the LLM is never called
    - prompt: the system prompt forbids outside knowledge and fixes the exact
      refusal string for "not in the context"
    - attribution: the Sources list is computed from retrieved metadata in Python

Setup:
    pip install -r requirements.txt
    cp .env.example .env   # then put your real GROQ_API_KEY in .env
Ask one question:
    python generate.py --query "Is there a photography club at Georgia Tech?"
"""

from __future__ import annotations

import argparse
import os

from embed import DEFAULT_K, retrieve

MODEL = "llama-3.3-70b-versatile"   # Groq free-tier, recommended default
REFUSAL = "I don't have enough information on that."
# Drop candidates whose cosine similarity to the query is below this floor, so
# off-domain questions fall through to the refusal instead of grabbing noise.
# Calibrated empirically: off-domain queries top out around 0.32 cosine sim
# against this corpus, while real in-domain questions score ~0.46+ — so 0.38
# separates them with margin and makes the "no relevant context" refusal a
# structural guarantee, not just a prompt instruction.
MIN_SCORE = 0.38

SYSTEM_PROMPT = (
    "You are \"The Unofficial Guide,\" a question-answering assistant for "
    "Georgia Tech student engagement and events.\n"
    "Follow these rules without exception:\n"
    "1. Answer using ONLY the information in the CONTEXT block. Do not use any "
    "prior, outside, or general knowledge.\n"
    f"2. If the CONTEXT does not contain enough information to answer, reply with "
    f"exactly this sentence and nothing else: \"{REFUSAL}\"\n"
    "3. Never invent organizations, events, dates, locations, or links that are "
    "not present in the CONTEXT.\n"
    "4. Quote names, dates, and locations exactly as they appear in the CONTEXT. "
    "If a relevant 'More info:' link is in the CONTEXT, include it.\n"
    "5. Be concise and specific."
)

_client = None


def _get_client():
    """Initialize the Groq client from GROQ_API_KEY in .env (loaded once)."""
    global _client
    if _client is None:
        from dotenv import load_dotenv
        from groq import Groq

        load_dotenv()
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your "
                "free Groq key from https://console.groq.com"
            )
        _client = Groq(api_key=key)
    return _client


def build_context(chunks: list[dict]) -> tuple[str, list[str]]:
    """Render retrieved chunks as a numbered CONTEXT block.

    Returns (context_text, ordered_unique_sources). The sources list is what we
    later attach to the answer, so attribution is derived from retrieval — not
    from anything the model writes.
    """
    blocks, sources = [], []
    for i, c in enumerate(chunks, 1):
        src = c.get("source", "")
        blocks.append(f"[{i}] Source: {src}\n{c['text']}")
        if src and src not in sources:
            sources.append(src)
    return "\n\n".join(blocks), sources


def build_messages(query: str, context: str) -> list[dict]:
    """Assemble the chat messages: rules in system, context + question in user."""
    user = (
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {query}\n\n"
        f"Answer using ONLY the CONTEXT above. If it does not contain enough "
        f"information, reply exactly: \"{REFUSAL}\""
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def format_sources(sources: list[str]) -> str:
    """Render the programmatic Sources list appended to grounded answers."""
    if not sources:
        return ""
    return "Sources:\n" + "\n".join(f"- {s}" for s in sources)


def _call_groq(messages: list[dict]) -> str:
    """One non-streaming completion from Groq's llama-3.3-70b-versatile."""
    resp = _get_client().chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2,        # low: stick to the context, don't get creative
        max_tokens=600,
    )
    return resp.choices[0].message.content.strip()


def generate_answer(
    query: str,
    k: int = DEFAULT_K,
    min_score: float = MIN_SCORE,
    llm=_call_groq,
) -> dict:
    """Answer `query`, grounded in retrieved context, with source attribution.

    `llm` is injectable (defaults to Groq) so the grounding/attribution logic can
    be unit-tested without a network call.

    Returns {answer, sources, grounded, chunks}:
        answer   - the model's answer with a programmatic Sources list appended,
                   or the refusal string when nothing relevant was retrieved
        sources  - the unique source URLs that back the answer (empty on refusal)
        grounded - True if the answer was produced from retrieved context
        chunks   - the retrieved chunks used (for inspection / the UI)
    """
    chunks = retrieve(query, k=k, min_score=min_score)
    if not chunks:
        # Structural grounding: no relevant context -> never call the LLM.
        return {"answer": REFUSAL, "sources": [], "grounded": False, "chunks": []}

    context, sources = build_context(chunks)
    answer = llm(build_messages(query, context))

    # If the model refused despite having context, don't attach sources to it.
    refused = answer.strip().rstrip(".").lower() == REFUSAL.rstrip(".").lower()
    if refused:
        return {"answer": REFUSAL, "sources": [], "grounded": False, "chunks": chunks}

    # Programmatic attribution: append sources computed from retrieval.
    full = answer.strip() + "\n\n" + format_sources(sources)
    return {"answer": full, "sources": sources, "grounded": True, "chunks": chunks}


def main() -> None:
    ap = argparse.ArgumentParser(description="Grounded Q&A over the guide (M5).")
    ap.add_argument("--query", required=True, help="the question to answer")
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    args = ap.parse_args()

    result = generate_answer(args.query, k=args.k)
    print(f"\nQ: {args.query}\n")
    print(result["answer"])


if __name__ == "__main__":
    main()
