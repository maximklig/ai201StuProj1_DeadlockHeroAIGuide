"""
Milestone 5 — Gradio interface for the Deadlock RAG assistant.

A minimal Blocks UI over query.ask(): type a question, get a grounded answer
plus the source URLs the answer was retrieved from. Submitting works on both
the Ask button and the Enter key.

Run:  python app.py
"""

import gradio as gr

from query import ask

TITLE = "Deadlock Unofficial Guide"
DESCRIPTION = (
    "Ask questions about heroes, abilities, items, and meta. Answers come only "
    "from scraped wiki and tier-list data."
)


def answer_question(question: str):
    """Call the RAG pipeline and format its result for the two output boxes."""
    if not question or not question.strip():
        return "Please enter a question.", ""

    result = ask(question)

    answer = result["answer"]
    sources = result["sources"]
    sources_text = "\n".join(f"• {url}" for url in sources)
    return answer, sources_text


with gr.Blocks(title=TITLE) as demo:
    gr.Markdown(f"# {TITLE}")
    gr.Markdown(DESCRIPTION)

    inp = gr.Textbox(label="Ask about a Deadlock hero or mechanic")
    btn = gr.Button("Ask")

    out_answer = gr.Textbox(label="Answer", lines=10)
    out_sources = gr.Textbox(label="Retrieved from", lines=4)

    # Submit on button click AND on Enter in the textbox.
    btn.click(answer_question, inputs=inp, outputs=[out_answer, out_sources])
    inp.submit(answer_question, inputs=inp, outputs=[out_answer, out_sources])


if __name__ == "__main__":
    demo.launch()
