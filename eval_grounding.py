"""
Milestone 5 — end-to-end grounding eval for "The Unofficial Guide".

The grounding test (from the assignment):
    "Could this response have come from anywhere other than your retrieved
     chunks? If yes, it's a grounding failure — even if the answer is correct."

So for each query we print BOTH the retrieved chunks and the final answer, side
by side, so every claim in the answer can be traced back to a chunk (or shown to
be a refusal). Three query types are exercised:

    1. in-domain, answerable      -> expect a grounded answer + real sources
    2. in-domain, answerable      -> expect a grounded answer + real sources
    3. on-topic but NOT in corpus -> expect the refusal (this is the trap: the
       LLM *knows* the answer from training, so answering it = grounding failure)

Run:  .venv/bin/python eval_grounding.py
"""

from __future__ import annotations

from generate import MIN_SCORE, REFUSAL, generate_answer

QUERIES = [
    # 1. In-domain: should be answerable straight from retrieved chunks.
    "Are there student organizations at Georgia Tech for people into photography?",
    # 2. In-domain: specific facts (programs/options) that must come from chunks.
    "What group fitness or intramural options does the Campus Rec Center have?",
    # 3. The trap: on-topic (GT) and the LLM knows this from training data, but it
    #    is not the kind of fact this events/engagement corpus contains. A correct
    #    answer here would be a GROUNDING FAILURE; a grounded system must refuse.
    "What year was the Georgia Institute of Technology founded?",
]


def show(query: str) -> None:
    result = generate_answer(query)
    chunks = result["chunks"]

    print("=" * 100)
    print(f"QUERY: {query}")
    print("-" * 100)

    print(f"RETRIEVED CHUNKS (min_score floor = {MIN_SCORE}):")
    if not chunks:
        print("  (none cleared the relevance floor -> structural refusal, LLM never called)")
    for i, c in enumerate(chunks, 1):
        snippet = " ".join(c["text"].split())[:220]
        print(f"  [{i}] score={c['score']:.3f}  source={c['source']}")
        print(f"      {snippet}...")

    print("-" * 100)
    print("ANSWER:")
    print(result["answer"])
    print(f"\ngrounded={result['grounded']}  "
          f"is_refusal={result['answer'].strip() == REFUSAL}")
    print()


if __name__ == "__main__":
    for q in QUERIES:
        show(q)
