"""
debug.py - Retrieval health checks for the Deadlock RAG knowledge base.

Bundles the debugging steps into one runnable script so you don't have to
remember the one-liners. Reuses retrieve() and the collection from embed.py and
reads chunks.json directly.

Run standalone:        python debug.py
Reproduce a run:       python debug.py <seed>

Randomization: every run picks DIFFERENT chunks, sample sizes, and orderings
(the eval queries themselves stay fixed) so the output isn't a predetermined,
cherry-picked set of results. A seed is printed each run; pass it back as an
argument to reproduce that exact run.

The checks:
  1. Print top chunks IN FULL for a randomly chosen eval query
  2. Distance scores across the eval questions (weak matches? enough separation?)
  3. Chunk content scan (HTML leftovers / fragments from bad cleaning?)
  4. Metadata integrity (correct + non-empty hero/section/source?)
  5. Chunk-size stats (are chunks too short to carry semantic context?)
  6. Random raw-chunk spot-check (proof the corpus is clean across the board)
"""

import json
import random
import re
import sys

from embed import retrieve, get_collection, CHUNKS_PATH

# The 5 evaluation questions from planning.md. These stay fixed on purpose -
# only the chunks/sampling/ordering around them are randomized.
EVAL_QUESTIONS = [
    "Does Haze throw a knife when using her ultimate ability?",
    "How many playable heroes are in the game?",
    "What tier is Ivy placed at?",
    "What is Ivy's pick rate and win rate?",
    "Does Haze have a passive ability?",
]

# Distance above this = treat as a weak match (matches embed.py's threshold).
WEAK_MATCH_THRESHOLD = 0.6

# Patterns that should NOT survive cleaning/chunking if ingest.py ran correctly.
ARTIFACT_PATTERN = re.compile(
    r"<[a-z/][^>]*>"        # HTML tags like <td>, </tr>, </spawn>
    r"|&nbsp;|&amp;|&lt;"   # HTML entities
    r"|\[edit\]"            # wiki edit links
    r"|\bclass=|colspan",   # leftover table attributes
    re.IGNORECASE,
)

# Chunks shorter than this are likely fragments rather than whole ideas.
SHORT_CHUNK_CHARS = 40


def _load_chunks():
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _sample(seq, k):
    """random.sample, but safe when k is larger than the sequence."""
    return random.sample(seq, min(k, len(seq)))


def _header(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# --------------------------------------------------------------------------- #
# CHECK 1 - Print retrieved chunks in full (random query + random k each run)
# --------------------------------------------------------------------------- #
def check_full_chunks():
    query = random.choice(EVAL_QUESTIONS)
    k = random.randint(2, 4)
    _header(f"CHECK 1 - Full text of top {k} chunks for a RANDOMLY chosen query")
    print(f"QUERY (random pick this run): {query}\n")
    for rank, hit in enumerate(retrieve(query, k), start=1):
        print(f"--- [{rank}] distance={hit['distance']:.4f} | "
              f"{hit['hero']} / {hit['section']} ---")
        print(f"source: {hit['source']}")
        # repr() exposes hidden junk (stray newlines, odd spacing) that a plain
        # print would hide - useful for spotting bad cleaning.
        print(repr(hit["text"]))
        print()
    print("Judge: does the #1 chunk actually answer the query, or just share a "
          "few words with it?")


# --------------------------------------------------------------------------- #
# CHECK 2 - Distance scores across all eval questions (shuffled order)
# --------------------------------------------------------------------------- #
def check_distances():
    _header("CHECK 2 - Distance scores across the 5 eval questions (shuffled)")
    questions = EVAL_QUESTIONS[:]
    random.shuffle(questions)  # order varies per run; the question set does not
    for q in questions:
        hits = retrieve(q, k=3)
        top = hits[0]["distance"]
        # "Separation" = gap between the best and 2nd-best hit. A tiny gap means
        # the retriever can't tell the right chunk from the runners-up.
        gap = hits[1]["distance"] - top if len(hits) > 1 else 0.0
        flag = "WEAK" if top > WEAK_MATCH_THRESHOLD else "OK  "
        print(f"[{flag}] top={top:.3f}  gap_to_2nd={gap:+.3f}  | {q}")
        for rank, hit in enumerate(hits, start=1):
            print(f"         {rank}. {hit['distance']:.3f}  "
                  f"{hit['hero']}/{hit['section']}")
    print(f"\nWeak = top distance > {WEAK_MATCH_THRESHOLD}. Healthy = low top "
          "distance AND a positive gap to the 2nd result.")


# --------------------------------------------------------------------------- #
# CHECK 3 - Scan chunk content for artifacts / fragments (random examples)
# --------------------------------------------------------------------------- #
def check_chunk_content(chunks):
    _header("CHECK 3 - Chunk content scan (HTML leftovers / fragments)")

    artifacts = [c["id"] for c in chunks if ARTIFACT_PATTERN.search(c["text"])]
    short = [c["id"] for c in chunks if len(c["text"]) < SHORT_CHUNK_CHARS]

    print(f"chunks with HTML/wiki artifacts: {len(artifacts)}")
    if artifacts:
        print("  random sample:", _sample(artifacts, 10))
    print(f"chunks shorter than {SHORT_CHUNK_CHARS} chars: {len(short)}")
    if short:
        print("  random sample:", _sample(short, 10))

    if not artifacts and not short:
        print("Clean: no artifacts and no suspiciously short fragments.")


# --------------------------------------------------------------------------- #
# CHECK 4 - Metadata integrity
# --------------------------------------------------------------------------- #
def check_metadata(chunks):
    _header("CHECK 4 - Metadata integrity")

    missing = [c["id"] for c in chunks
               if not (c.get("hero") and c.get("section") and c.get("source"))]
    print(f"chunks missing hero/section/source: {len(missing)}")
    if missing:
        print("  random sample:", _sample(missing, 10))

    # Spot-check that a known query lands on the expected source. The Ivy tier
    # fact should come from metabot.gg (the tier list), not a wiki hero page.
    top = retrieve("What tier is Ivy placed at?", k=1)[0]
    print(f"\nSpot-check 'Ivy tier' -> hero={top['hero']} | "
          f"source={top['source']}")
    print("Expected source: the metabot.gg tier-list URL.")


# --------------------------------------------------------------------------- #
# CHECK 5 - Chunk-size statistics
# --------------------------------------------------------------------------- #
def check_chunk_sizes(chunks):
    _header("CHECK 5 - Chunk-size statistics")

    lengths = sorted(len(c["text"]) for c in chunks)
    n = len(lengths)
    total = sum(lengths)
    median = lengths[n // 2]
    print(f"total chunks: {n}")
    print(f"min: {lengths[0]}  median: {median}  "
          f"mean: {total // n}  max: {lengths[-1]} (chars)")
    # If the median is far below the ~400 target, chunks may be too small to
    # carry enough context per embedding - consider a larger CHUNK_SIZE.
    if median < 200:
        print("NOTE: median is low - chunks may be too short for good context. "
              "Try a larger CHUNK_SIZE in ingest.py, then re-ingest + re-embed.")
    else:
        print("Chunk sizes look reasonable for the ~400-char target.")


# --------------------------------------------------------------------------- #
# CHECK 6 - Random raw-chunk spot-check (different chunks every run)
# --------------------------------------------------------------------------- #
def check_random_spotcheck(chunks):
    n = random.randint(3, 6)
    _header(f"CHECK 6 - Random raw-chunk spot-check ({n} chunks, random each run)")
    for c in _sample(chunks, n):
        print(f"--- {c['id']} | {c['hero']} / {c['section']} "
              f"({len(c['text'])} chars) ---")
        print(f"source: {c['source']}")
        print(repr(c["text"]))
        print()
    print("These are pulled at random from chunks.json - proof the corpus is "
          "clean across the board, not just on the eval queries.")


def main():
    # Seed from the CLI arg if given, else a random seed we print so the run
    # is reproducible on demand without being predetermined.
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else random.randrange(1_000_000)
    random.seed(seed)
    print(f"Random seed: {seed}  (run `python debug.py {seed}` to reproduce this run)")

    collection = get_collection()
    count = collection.count()
    if count == 0:
        print("Collection is empty - run `python embed.py` first to populate it.")
        return 1
    print(f"Collection '{collection.name}' holds {count} embedded documents.")

    chunks = _load_chunks()

    check_full_chunks()
    check_distances()
    check_chunk_content(chunks)
    check_metadata(chunks)
    check_chunk_sizes(chunks)
    check_random_spotcheck(chunks)

    print("\nAll checks complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
