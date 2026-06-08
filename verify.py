"""
verify.py - Milestone 3 sanity check for the Deadlock RAG ingestion.

Two layers of checking:

  1. Structural - chunks.json exists, every chunk has the required tags
     (hero / section / source / text), and the chunk sizes obey the
     400-char / 80-overlap strategy from planning.md.

  2. Content smoke test - a tiny keyword search over the chunks confirms the
     corpus actually contains the answers to the 5 evaluation questions in
     planning.md. (This is a stand-in for real embedding retrieval, which
     arrives in Milestone 4 - if the answer text isn't even present here, no
     embedding model will find it.)

Usage:
  python verify.py
Exit code is 0 if all structural checks pass, 1 otherwise.
"""

import json
import re
import sys
from pathlib import Path

CHUNKS_PATH = Path(__file__).parent / "chunks.json"
CHUNK_SIZE = 400

# Each smoke-test question: keywords to score chunks by, plus a substring we
# expect to see in the top hit (case-insensitive). Mirrors planning.md's
# Evaluation Plan.
SMOKE_TESTS = [
    {
        "q": "Does Haze throw a knife when using her ultimate?",
        "keywords": ["haze", "bullet dance", "flurry", "dagger"],
        # Her ult is Bullet Dance (a gun flurry); the knife is the Sleep Dagger.
        "expect": "Enter a flurry, firing your weapon",
    },
    {
        "q": "How many playable heroes are in the game?",
        "keywords": ["hero", "heroes"],
        "expect": None,               # answered by the hero count, printed separately
    },
    {
        "q": "What tier is Ivy placed at?",
        "keywords": ["ivy", "tier"],
        "expect": "Ivy is a A-tier",
    },
    {
        "q": "What is Ivy's pick rate and win rate?",
        "keywords": ["ivy", "win rate", "pick rate"],
        "expect": "52.5% win rate and 27.2% pick rate",
    },
    {
        "q": "Does Haze have a passive ability? (Fixation)",
        "keywords": ["haze", "fixation", "stack"],
        "expect": "Fixation",
    },
]


def load_chunks():
    if not CHUNKS_PATH.exists():
        print(f"FAIL: {CHUNKS_PATH.name} not found. Run scraper.py then ingest.py.")
        sys.exit(1)
    return json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# 1. Structural checks
# --------------------------------------------------------------------------- #
def structural_checks(chunks) -> bool:
    print("=" * 70)
    print("1. Structural checks")
    print("=" * 70)
    ok = True

    if not chunks:
        print("  FAIL: chunks.json is empty.")
        return False

    required = ("id", "hero", "section", "source", "text")
    missing = [c for c in chunks if any(not c.get(k) for k in required)]
    if missing:
        ok = False
        print(f"  FAIL: {len(missing)} chunk(s) missing required tags "
              f"({', '.join(required)}).")
    else:
        print(f"  PASS: all {len(chunks)} chunks carry hero / section / source / text.")

    oversized = [c for c in chunks if len(c["text"]) > CHUNK_SIZE]
    if oversized:
        ok = False
        print(f"  FAIL: {len(oversized)} chunk(s) exceed {CHUNK_SIZE} chars "
              f"(largest = {max(len(c['text']) for c in oversized)}).")
    else:
        print(f"  PASS: every chunk is <= {CHUNK_SIZE} chars.")

    dup_ids = len(chunks) - len({c["id"] for c in chunks})
    if dup_ids:
        ok = False
        print(f"  FAIL: {dup_ids} duplicate chunk id(s).")
    else:
        print("  PASS: all chunk ids are unique.")

    # Source coverage
    wiki = sum(1 for c in chunks if "deadlock.wiki" in c["source"])
    meta = sum(1 for c in chunks if "metabot.gg" in c["source"])
    print(f"  INFO: {wiki} chunks from deadlock.wiki, {meta} from metabot.gg.")
    if meta == 0:
        ok = False
        print("  FAIL: no metabot.gg tier chunks present (run scraper.py --meta).")

    return ok


# --------------------------------------------------------------------------- #
# 2. Content smoke test (keyword retrieval stand-in)
# --------------------------------------------------------------------------- #
def _score(text: str, keywords):
    """
    Score a chunk by keyword coverage first, raw frequency second.

    Coverage (how many distinct keywords appear) matters more than frequency:
    a chunk mentioning both 'ivy' and 'tier' should beat one that just repeats
    'ivy' many times in trivia. Returns (distinct_hits, total_count).
    """
    low = text.lower()
    counts = [low.count(k.lower()) for k in keywords]
    distinct = sum(1 for n in counts if n > 0)
    return (distinct, sum(counts))


def search(chunks, keywords, top_k=3):
    scored = [(_score(c["text"], keywords), c) for c in chunks]
    scored = [pair for pair in scored if pair[0][0] > 0]
    scored.sort(key=lambda p: p[0], reverse=True)
    return scored[:top_k]


def smoke_test(chunks) -> None:
    print()
    print("=" * 70)
    print("2. Content smoke test - can the corpus answer the eval questions?")
    print("=" * 70)

    # Hero count: distinct heroes that have a wiki hero page (exclude the
    # overview/table pseudo-heroes and the metabot 'Tier List' tag).
    non_hero = {"Heroes", "Hero_Comparison_Table", "Tier List"}
    hero_pages = {
        c["hero"] for c in chunks
        if "deadlock.wiki" in c["source"] and c["hero"] not in non_hero
    }
    print(f"\n  [hero count] distinct wiki hero pages: {len(hero_pages)}")

    for t in SMOKE_TESTS:
        print(f"\n  Q: {t['q']}")

        # (a) Presence check: is the answer text actually in the knowledge base?
        if t["expect"]:
            matches = [c for c in chunks if t["expect"].lower() in c["text"].lower()]
            if matches:
                m = matches[0]
                domain = m["source"].split("//")[-1].split("/")[0]
                snippet = re.sub(r"\s+", " ", m["text"])[:150]
                print(f"     answer present: YES  ->  [{m['hero']} / {m['section']}]  "
                      f"({len(matches)} chunk(s), {domain})")
                print(f'       "{snippet}"')
            else:
                print(f"     answer present: NO  -  expected text "
                      f"'{t['expect']}' not found (review manually)")

        # (b) Retrieval preview: what a naive keyword search surfaces first.
        hits = search(chunks, t["keywords"], top_k=1)
        if hits:
            (distinct, _total), c = hits[0]
            print(f"     keyword top hit: [{c['hero']} / {c['section']}]  "
                  f"({distinct}/{len(t['keywords'])} keywords)")


def main() -> int:
    chunks = load_chunks()
    ok = structural_checks(chunks)
    smoke_test(chunks)
    print()
    print("=" * 70)
    print("RESULT:", "ALL STRUCTURAL CHECKS PASSED" if ok else "STRUCTURAL CHECKS FAILED")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
