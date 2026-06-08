"""
inspect_chunks.py - Milestone 3 quality check for chunks.json.

Loads chunks.json and prints summary stats plus 5 evenly-spaced sample chunks
(with their hero / section / source tags and length) so you can eyeball chunk
quality: are they tagged correctly, is the size/overlap sensible, is the text
clean?

Usage:
  python inspect_chunks.py
"""

import json
import sys
from pathlib import Path

CHUNKS_PATH = Path(__file__).parent / "chunks.json"
NUM_SAMPLES = 5


def main(argv=None) -> int:
    if not CHUNKS_PATH.exists():
        print(f"{CHUNKS_PATH.name} not found. Run ingest.py first.")
        return 1

    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    if not chunks:
        print("chunks.json is empty.")
        return 1

    # ---- Summary stats ---------------------------------------------------- #
    lengths = [len(c["text"]) for c in chunks]
    heroes = sorted({c["hero"] for c in chunks})
    sections = sorted({c["section"] for c in chunks})

    print("=" * 70)
    print("chunks.json summary")
    print("=" * 70)
    print(f"  total chunks : {len(chunks)}")
    print(f"  heroes/pages : {len(heroes)}")
    print(f"  sections     : {len(sections)}")
    print(f"  chunk length : min={min(lengths)} max={max(lengths)} "
          f"avg={sum(lengths) // len(lengths)}")
    print()

    # ---- 5 evenly-spaced samples ----------------------------------------- #
    n = min(NUM_SAMPLES, len(chunks))
    # Spread the picks across the whole file rather than just the first few.
    step = max(1, len(chunks) // n)
    sample_idxs = list(range(0, len(chunks), step))[:n]

    print(f"Showing {n} sample chunks:\n")
    for rank, i in enumerate(sample_idxs, start=1):
        c = chunks[i]
        print("-" * 70)
        print(f"Sample {rank}  (chunk index {i})")
        print(f"  id      : {c['id']}")
        print(f"  hero    : {c['hero']}")
        print(f"  section : {c['section']}")
        print(f"  source  : {c['source']}")
        print(f"  length  : {len(c['text'])} chars")
        print("  text    :")
        print(f"    {c['text']}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
