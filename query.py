"""
Milestone 5 — Grounded generation for the Deadlock RAG knowledge base.

Ties retrieval (Milestone 4) to a Groq-hosted LLM. ask() retrieves the top-5
most similar chunks from ChromaDB, builds a context block with each chunk's
source inline, and asks llama-3.3-70b-versatile to answer ONLY from those
excerpts. Sources are pulled from the retrieved chunk metadata afterwards — the
LLM is never trusted to list them.

Public API:
    ask(question) -> {"answer": str, "sources": list[str]}

Reuses embed.retrieve() so the query is embedded with the same local
all-MiniLM-L6-v2 model and hits the same "deadlock_chunks" collection used at
ingest time — the embedding spaces must match for retrieval to mean anything.
"""

import os

from dotenv import load_dotenv
from groq import Groq

from embed import retrieve

# --- Config ---------------------------------------------------------------
TOP_K = 5
LLM_MODEL = "llama-3.3-70b-versatile"

# The fallback is a fixed string, returned verbatim by the model when the
# excerpts don't answer the question. Keep it identical to the system prompt.
FALLBACK_ANSWER = "I don't have enough information on that."

# Hard grounding contract. This forbids training knowledge outright — it does
# not merely "prefer" the documents — and pins the out-of-scope reply to a fixed
# string so it can be detected. Do not soften this wording.
SYSTEM_PROMPT = """You are a Deadlock game assistant. You ONLY answer using the document excerpts provided below. Do not use any knowledge from your training data.

Rules you must follow without exception:
- If the answer is present in the excerpts, answer it directly and cite which source(s) it came from using the format: (Source: <url>)
- If the excerpts do not contain enough information to answer the question, respond with exactly: "I don't have enough information on that."
- Never speculate, infer, or answer from general game knowledge.
- Never mention that you are an AI or reference your training data."""

# Load GROQ_API_KEY from .env. The Groq client is created lazily inside ask()
# so importing this module never requires a key (e.g. when tests import only
# the helpers, or the embed-side retrieval).
load_dotenv()
_client = None


def _get_client() -> Groq:
    """Create (once) and return the Groq client."""
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = Groq(api_key=api_key)
    return _client


def _build_context(hits: list[dict]) -> str:
    """Format retrieved chunks into a context block with the source inline.

    Each chunk's source URL travels with its text so any (Source: <url>)
    citation the model writes is verifiable against what it was actually given.
    """
    blocks = []
    for hit in hits:
        header = (
            f"[Source: {hit['source']} | Hero: {hit['hero']} "
            f"| Section: {hit['section']}]"
        )
        blocks.append(f"{header}\n{hit['text']}")
    return "\n\n".join(blocks)


def _dedupe_sources(hits: list[dict]) -> list[str]:
    """Collect source URLs from chunk metadata, deduplicated, order preserved.

    Sources come from ChromaDB metadata — never from the LLM output — so the
    attribution can't be hallucinated. First-seen order keeps the most relevant
    (closest) chunk's source first.
    """
    seen = set()
    sources = []
    for hit in hits:
        url = hit.get("source")
        if url and url not in seen:
            seen.add(url)
            sources.append(url)
    return sources


def ask(question: str) -> dict:
    """Answer `question` from the Deadlock corpus, grounded in retrieved chunks.

    Returns {"answer": str, "sources": list[str]} where sources are the
    deduplicated source URLs of the retrieved chunks (from ChromaDB metadata).
    """
    hits = retrieve(question, k=TOP_K)

    # No chunks at all — don't even call the LLM; nothing to ground on.
    if not hits:
        return {"answer": FALLBACK_ANSWER, "sources": []}

    context = _build_context(hits)
    sources = _dedupe_sources(hits)

    user_message = (
        f"Document excerpts:\n\n{context}\n\n"
        f"Question: {question}"
    )

    response = _get_client().chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        # Low temperature keeps the model close to the excerpts rather than
        # filling gaps with fluent-sounding invention.
        temperature=0.0,
    )

    answer = response.choices[0].message.content.strip()
    return {"answer": answer, "sources": sources}
