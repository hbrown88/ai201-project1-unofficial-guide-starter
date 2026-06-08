"""
Milestone 5 — Gradio interface for "The Unofficial Guide".

A thin UI over generate_answer(): the grounding and source attribution live in
generate.py; this file only collects the question and renders the answer, the
programmatic source list, and (optionally) the retrieved chunks for transparency.

Run:
    pip install -r requirements.txt
    python app.py            # then open the local URL it prints
"""

from __future__ import annotations

import gradio as gr

from generate import DEFAULT_K, generate_answer

EXAMPLES = [
    "Is there a photography club at Georgia Tech I could join?",
    "What group fitness or intramural options does the Campus Rec Center have?",
    "What upcoming events on campus could help me build my resume?",
    "What's a free or cheap thing to do off campus in Atlanta this weekend?",
]


def answer(query: str, k: int):
    """Run one grounded query and return (answer_markdown, sources_markdown)."""
    query = (query or "").strip()
    if not query:
        return "Ask a question to get started.", ""

    result = generate_answer(query, k=int(k))

    if not result["grounded"]:
        # Honest empty state: no sources to show when we couldn't ground it.
        return result["answer"], ""

    sources_md = "**Sources**\n" + "\n".join(f"- {s}" for s in result["sources"])
    return result["answer"], sources_md


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="The Unofficial Guide") as demo:
        gr.Markdown(
            "# The Unofficial Guide\n"
            "Ask about Georgia Tech student organizations, campus events, rec "
            "programs, and things to do around Atlanta. Answers come only from "
            "the retrieved sources — if the guide doesn't have it, it will say so."
        )
        with gr.Row():
            query = gr.Textbox(
                label="Your question",
                placeholder="e.g. Is there a photography club at Georgia Tech?",
                scale=4,
                autofocus=True,
            )
            k = gr.Slider(1, 10, value=DEFAULT_K, step=1, label="Chunks (k)", scale=1)
        ask = gr.Button("Ask", variant="primary")

        answer_box = gr.Markdown(label="Answer")
        sources_box = gr.Markdown(label="Sources")

        gr.Examples(examples=EXAMPLES, inputs=query)

        # Wire it together: button click and Enter both run answer().
        ask.click(answer, inputs=[query, k], outputs=[answer_box, sources_box])
        query.submit(answer, inputs=[query, k], outputs=[answer_box, sources_box])

    return demo


if __name__ == "__main__":
    build_ui().launch()
