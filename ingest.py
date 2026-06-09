"""
ingest.py - Milestone 3 chunking for the Deadlock RAG knowledge base.

Reads the section-marked text files produced by scraper.py in documents/,
cleans the text, splits it into overlapping chunks, tags every chunk with its
hero name + source section, and writes the result to chunks.json.

Chunking strategy (from planning.md):
  - 400 characters per chunk
  - 80 character overlap

Each output chunk looks like:
  {
    "id": "Haze__Abilities__0",
    "hero": "Haze",
    "section": "Abilities",
    "source": "https://deadlock.wiki/Haze",
    "text": "..."
  }
"""

import json
import re
import sys
from pathlib import Path

CHUNK_SIZE = 400
CHUNK_OVERLAP = 80

DOCUMENTS_DIR = Path(__file__).parent / "documents"
OUTPUT_PATH = Path(__file__).parent / "chunks.json"

SECTION_MARKER = "## SECTION:"


# --------------------------------------------------------------------------- #
# Cleaning
# --------------------------------------------------------------------------- #
# Map fancy Unicode punctuation to plain ASCII so chunks render consistently
# everywhere (terminals, JSON viewers) and search behaves predictably. These
# are real characters from the wiki (e.g. em dashes in captions, curly quotes),
# not corruption - they just display as "?" in some consoles.
_PUNCT_NORMALIZE = {
    "‘": "'", "’": "'",          # ‘ ’ curly single quotes
    "“": '"', "”": '"',          # “ ” curly double quotes
    "–": "-", "—": "-",          # – — en / em dashes
    "…": "...",                        # … ellipsis
    " ": " ", "​": "",            # non-breaking space, zero-width space
    "�": "",                            # true replacement character
}


def clean_text(text: str) -> str:
    """Normalise punctuation/whitespace and strip leftover wiki artifacts."""
    for src, dst in _PUNCT_NORMALIZE.items():
        text = text.replace(src, dst)
    text = re.sub(r"\[edit\]", "", text)
    text = re.sub(r"\[\s*\d+\s*\]", "", text)       # reference markers [1] / [ 1 ]
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)   # strip stray HTML tags like </spawn>
    # Tidy the wiki infobox "Label : | value" pattern into "Label: value".
    text = re.sub(r"\s*:\s*\|\s*", ": ", text)
    text = re.sub(r"[ \t]+", " ", text)            # collapse runs of spaces/tabs
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)    # drop space before punctuation
    text = re.sub(r"\n{3,}", "\n\n", text)         # collapse blank-line runs
    # Trim trailing spaces on each line.
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #
# Split after sentence-ending punctuation (. ! ?) followed by whitespace.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_units(text: str):
    """
    Break text into atomic units that must not be cut mid-way.

    Splits on line breaks first (preserves the wiki's stat rows like
    'Health: 800 +52'), then on sentence boundaries within each line.
    """
    units = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for sentence in _SENT_SPLIT.split(line):
            sentence = sentence.strip()
            if sentence:
                units.append(sentence)
    return units


def _split_long_unit(unit: str, size: int):
    """Fallback for a single unit longer than `size`: split on word
    boundaries so we still never cut a word in half."""
    pieces, current = [], ""
    for word in unit.split():
        if current and len(current) + 1 + len(word) > size:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """
    Split text into ~`size`-character chunks on sentence / line boundaries.

    Unlike a raw character window, this never cuts a word or sentence in half.
    The text is broken into atomic units (stat lines and sentences) which are
    greedily packed up to `size` characters. Consecutive chunks share roughly
    `overlap` characters of trailing sentences, so context spanning a boundary
    is still recoverable. A trailing sentence may push a chunk slightly over
    `size` rather than be cut — keeping sentences whole is the goal here.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    # Atomic units, with any oversized unit pre-split on word boundaries.
    units = []
    for unit in _split_units(text):
        if len(unit) > size:
            units.extend(_split_long_unit(unit, size))
        else:
            units.append(unit)

    chunks = []
    current = []  # units accumulated for the chunk currently being built

    for unit in units:
        # If adding this unit would exceed `size`, close the current chunk and
        # seed the next one with trailing sentences worth ~`overlap` chars.
        if current and len(" ".join(current + [unit])) > size:
            chunks.append(" ".join(current))
            carry = []
            for prev in reversed(current):
                if len(" ".join([prev] + carry)) > overlap:
                    break
                carry.insert(0, prev)
            current = carry
        current.append(unit)

    if current:
        chunks.append(" ".join(current))
    return chunks


# --------------------------------------------------------------------------- #
# Document parsing
# --------------------------------------------------------------------------- #
def parse_document(path: Path):
    """
    Parse a scraper.py output file into (hero, source, [(section, text), ...]).

    Falls back gracefully if the header lines are missing (e.g. a hand-added
    document) by using the filename as the hero and 'General' as the section.
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    hero = path.stem.replace("_", " ")
    source = ""
    body_start = 0

    # Header lines: HERO:, SOURCE:, then a '====' divider.
    for i, line in enumerate(lines[:5]):
        if line.startswith("HERO:"):
            hero = line[len("HERO:"):].strip() or hero
        elif line.startswith("SOURCE:"):
            source = line[len("SOURCE:"):].strip()
        elif set(line.strip()) == {"="} and line.strip():
            body_start = i + 1
            break

    body = "\n".join(lines[body_start:])

    sections = []
    if SECTION_MARKER in body:
        # Split on the section marker, keeping each section's title.
        parts = re.split(rf"^{re.escape(SECTION_MARKER)}\s*", body, flags=re.MULTILINE)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            title, _, content = part.partition("\n")
            sections.append((title.strip() or "General", content.strip()))
    else:
        sections.append(("General", body.strip()))

    return hero, source, sections


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_") or "x"


def ingest(documents_dir: Path = DOCUMENTS_DIR, output_path: Path = OUTPUT_PATH):
    files = sorted(p for p in documents_dir.glob("*.txt"))
    if not files:
        print(f"No .txt documents found in {documents_dir}/. Run scraper.py first.")
        return []

    all_chunks = []
    # Running index per (hero, section) so chunk ids stay unique even when a
    # page repeats a section title (e.g. the Heroes page has two 'Overview's).
    counters: dict[tuple[str, str], int] = {}
    for path in files:
        hero, source, sections = parse_document(path)
        file_chunk_count = 0
        for section, text in sections:
            cleaned = clean_text(text)
            key = (_slug(hero), _slug(section))
            for piece in chunk_text(cleaned):
                idx = counters.get(key, 0)
                counters[key] = idx + 1
                all_chunks.append({
                    "id": f"{key[0]}__{key[1]}__{idx}",
                    "hero": hero,
                    "section": section,
                    "source": source,
                    "text": piece,
                })
                file_chunk_count += 1
        print(f"  {path.name:<28} hero={hero!r:<24} chunks={file_chunk_count}")

    output_path.write_text(
        json.dumps(all_chunks, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nWrote {len(all_chunks)} chunks -> {output_path}")
    return all_chunks


def main(argv=None) -> int:
    chunks = ingest()
    return 0 if chunks else 1


if __name__ == "__main__":
    sys.exit(main())
