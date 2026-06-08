"""
scraper.py - Milestone 3 document ingestion for the Deadlock RAG knowledge base.

Scrapes two sources and writes section-marked plain-text files into documents/.
The section markers (## SECTION: ...) let ingest.py tag each chunk with the hero
name + the source section it came from.
  1. deadlock.wiki   - hero / overview pages (abilities, lore, stats).
  2. metabot.gg       - tier list (tier / win rate / pick rate per hero), written
                        as one Meta_<hero>.txt file per hero.

Politeness:
  - A real browser User-Agent is sent on every request.
  - Requests are rate-limited to ~1 request/second.

Usage:
  python scraper.py --check                 # verify BOTH sources are reachable
  python scraper.py --list-only             # discover hero pages, print them, don't scrape
  python scraper.py                         # full scrape (wiki pages + heroes + tier list)
  python scraper.py --limit 5               # overview pages + first 5 heroes + tier list
  python scraper.py --heroes Haze Ivy       # scrape only the named heroes (no tier list)
  python scraper.py --meta                  # scrape ONLY the metabot.gg tier list
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_URL = "https://deadlock.wiki"

# metabot.gg tier list (source #3 in planning.md): win rates, pick rates, tier.
METABOT_TIER_URL = "https://metabot.gg/en/deadlock/heroes/tier-list"

# General overview pages (not tied to a single hero). These map to the
# "Documents" table in planning.md.
OVERVIEW_PAGES = [
    ("Heroes", "Heroes"),                              # general hero mechanics
    ("Hero_Comparison_Table", "Hero_Comparison_Table"),  # comparative stats
]

DOCUMENTS_DIR = Path(__file__).parent / "documents"

# A real, current desktop browser UA. Being a polite scraper means identifying
# as something the server expects rather than a default python-requests string.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

RATE_LIMIT_SECONDS = 1.0  # ~1 request/second
REQUEST_TIMEOUT = 20      # seconds

# MediaWiki namespaces / meta pages we never want to treat as hero pages.
_SKIP_PREFIXES = (
    "Special:", "File:", "Category:", "Template:", "Help:", "Talk:",
    "User:", "Map:", "Item:", "MediaWiki:", "Property:",
)
_SKIP_PAGES = {
    "Heroes", "Hero_Comparison_Table", "Abilities", "Items", "Main_Page",
}

# Section headings that are site chrome rather than content. Compared
# case-insensitively. Skipping these keeps chunks focused on hero info.
_SKIP_SECTIONS = {
    "contents", "references", "navigation", "gallery", "update history",
    "external links", "see also",
}


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def polite_get(session: requests.Session, url: str) -> requests.Response:
    """GET a URL, then sleep to honour the ~1 request/second rate limit."""
    resp = session.get(url, timeout=REQUEST_TIMEOUT)
    time.sleep(RATE_LIMIT_SECONDS)
    return resp


def page_url(page: str) -> str:
    """Build a wiki URL for a page title (e.g. 'Haze' -> https://deadlock.wiki/Haze)."""
    return urljoin(BASE_URL + "/", page)


# --------------------------------------------------------------------------- #
# Reachability check (--check)
# --------------------------------------------------------------------------- #
def check_reachable(session: requests.Session) -> int:
    """HTTP GET each source and print the status. No scraping. Returns exit code."""
    targets = [
        ("deadlock.wiki", BASE_URL),
        ("metabot.gg tier list", METABOT_TIER_URL),
    ]
    rc = 0
    for label, url in targets:
        print(f"Checking reachability of {label} ({url}) ...")
        try:
            resp = polite_get(session, url)
        except requests.RequestException as exc:
            print(f"  UNREACHABLE: {exc}")
            rc = 1
            continue
        print(f"  HTTP {resp.status_code} {resp.reason}  ({len(resp.content)} bytes)")
        if resp.ok:
            print("  OK - reachable.")
        else:
            print("  WARNING - non-2xx status returned.")
            rc = 1
    return rc


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _clean_inline(text: str) -> str:
    """Light cleanup of a text fragment pulled from the page."""
    text = text.replace("\xa0", " ")
    text = text.replace("�", "")            # stray replacement glyphs
    text = re.sub(r"\[edit\]", "", text)         # MediaWiki [edit] links
    text = re.sub(r"\[\s*\d+\s*\]", "", text)    # reference markers like [1] / [ 1 ]
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _table_rows(table) -> list[str]:
    """Render a leaf table's rows as 'cell | cell | cell' lines."""
    rows = []
    for tr in table.find_all("tr"):
        cells = [
            _clean_inline(c.get_text(" ", strip=True))
            for c in tr.find_all(["th", "td"])
        ]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    return rows


def _ability_card_lines(section) -> list[str]:
    """
    Extract readable lines from a deadlock.wiki '.ability-section' card:
    header (name + cooldown), the description prose, and the upgrade points.

    The raw unlabeled stat grid inside the card is intentionally skipped - it
    is low value for retrieval and the labeled numbers live in the infobox.
    """
    lines: list[str] = []

    header = section.select_one(".ac-header")
    if header:
        h = _clean_inline(header.get_text(" ", strip=True))
        if h:
            lines.append(h)

    for desc in section.select(".ac-info-desc"):
        t = _clean_inline(desc.get_text(" ", strip=True))
        if t and t not in lines:
            lines.append(t)

    upgrades = []
    for up in section.select(".ability-upgrade"):
        head = up.select_one(".ability-upgrade-header")
        body = up.select_one(".ac-upgrade-desc")
        head_t = _clean_inline(head.get_text(" ", strip=True)) if head else ""
        body_t = _clean_inline(body.get_text(" ", strip=True)) if body else ""
        combo = " ".join(x for x in (head_t, body_t) if x)
        if combo:
            upgrades.append(combo)
    if upgrades:
        lines.append("Upgrades: " + " ; ".join(upgrades))

    return lines


def extract_sections(html: str):
    """
    Parse a deadlock.wiki article into (section_title, section_text) pairs.

    Walks the content tree in document order so sections come out in order.
    Recognized content blocks (paragraphs, lists, leaf tables, hero-tag pills,
    and ability cards) are emitted and not descended into; everything else is
    recursed through. Chrome sections (see _SKIP_SECTIONS) are dropped, and
    duplicate lines within a section (the wiki repeats infobox blocks) are
    collapsed.
    """
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("div.mw-parser-output") or soup.body or soup
    if content is None:
        return []

    sections = []
    state = {"title": "Overview", "parts": [], "seen": set(), "skip": False}

    def flush():
        text = "\n".join(p for p in state["parts"] if p).strip()
        if text:
            sections.append((state["title"], text))

    def add(line: str):
        if line and line not in state["seen"]:
            state["seen"].add(line)
            state["parts"].append(line)

    def walk(node):
        for el in node.children:
            name = getattr(el, "name", None)
            if name is None or name in ("script", "style", "sup"):
                continue  # sup = reference superscripts

            # Headings can be bare (<h2>) or, in newer MediaWiki output, wrapped
            # in <div class="mw-heading">. Detect both BEFORE the skip check so a
            # chrome section never hides the heading that ends it.
            heading_el = None
            if name in ("h2", "h3", "h4"):
                heading_el = el
            elif name == "div" and any(
                c.startswith("mw-heading") for c in (el.get("class") or [])
            ):
                heading_el = el.find(["h2", "h3", "h4"])

            if heading_el is not None:
                headline = heading_el.select_one(".mw-headline")
                title = _clean_inline((headline or heading_el).get_text(" ", strip=True))
                if title:
                    flush()
                    state["title"] = title
                    state["parts"] = []
                    state["seen"] = set()
                    state["skip"] = title.lower() in _SKIP_SECTIONS
                continue

            if state["skip"]:
                continue

            cls = set(el.get("class") or [])

            if "ability-section" in cls:
                for line in _ability_card_lines(el):
                    add(line)
                continue
            if "infobox-h-herotags-inner" in cls:
                tags = _clean_inline(el.get_text(" ", strip=True))
                if tags:
                    add("Tags: " + tags)
                continue
            if name == "p":
                add(_clean_inline(el.get_text(" ", strip=True)))
                continue
            if name in ("ul", "ol"):
                for li in el.find_all("li", recursive=False):
                    add("- " + _clean_inline(li.get_text(" ", strip=True)))
                continue
            if name == "dl":
                add(_clean_inline(el.get_text(" ", strip=True)))
                continue
            if name == "table":
                if el.find("table") is None:        # leaf table -> render rows
                    for row in _table_rows(el):
                        add(row)
                else:                                # wrapper -> dig for content
                    walk(el)
                continue

            walk(el)  # generic container

    walk(content)
    flush()
    return sections


def discover_hero_links(session: requests.Session) -> list[str]:
    """
    Scrape /Heroes and return a sorted list of hero page titles.

    Discovery is scoped to the hero grid (div.HeroCard > div.hero-link-wrapper)
    rather than every link on the page, so game-mechanic pages, map features,
    and MediaWiki edit links are excluded.
    """
    resp = polite_get(session, page_url("Heroes"))
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    content = soup.select_one("div.mw-parser-output") or soup

    anchors = content.select("div.hero-link-wrapper a[href]")
    if not anchors:  # fall back to HeroCard if the inner wrapper class changes
        anchors = content.select("div.HeroCard a[href]")

    titles: list[str] = []
    seen = set()
    for a in anchors:
        href = a["href"]
        if not href.startswith("/") or href.startswith("//"):
            continue
        title = unquote(href.lstrip("/")).split("#")[0]
        # Skip namespaced pages (':'), query/edit links ('?', '='), and meta.
        if not title or any(ch in title for ch in (":", "?", "=")):
            continue
        if title in _SKIP_PAGES or title in seen:
            continue
        if any(title.startswith(p) for p in _SKIP_PREFIXES):
            continue
        seen.add(title)
        titles.append(title)
    return sorted(titles)


# --------------------------------------------------------------------------- #
# metabot.gg tier list
# --------------------------------------------------------------------------- #
def _iter_jsonld_hero_entries(node):
    """
    Recursively yield (hero_name, description) from schema.org ItemList blocks.

    metabot.gg embeds the tier list as JSON-LD: each hero is a ListItem whose
    'item' has a name and a ready-made sentence such as
    "Ivy is a A-tier champion with 52.5% win rate and 27.2% pick rate ...".
    """
    if isinstance(node, dict):
        if node.get("@type") == "ItemList":
            for el in node.get("itemListElement", []) or []:
                item = el.get("item") if isinstance(el, dict) else None
                if isinstance(item, dict) and item.get("name") and item.get("description"):
                    yield item["name"], item["description"]
        for value in node.values():
            yield from _iter_jsonld_hero_entries(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_jsonld_hero_entries(value)


def fetch_tier_list(session: requests.Session) -> dict:
    """Return {hero_name: description} parsed from the metabot tier-list page."""
    resp = polite_get(session, METABOT_TIER_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    entries: dict[str, str] = {}
    for block in soup.find_all("script", type="application/ld+json"):
        if not block.string:
            continue
        try:
            data = json.loads(block.string)
        except json.JSONDecodeError:
            continue
        for name, desc in _iter_jsonld_hero_entries(data):
            # Keep the first description seen per hero (the master list).
            entries.setdefault(name, _clean_inline(desc))
    return entries


def scrape_tier_list(session: requests.Session) -> int:
    """
    Scrape the metabot.gg tier list and write one Meta_<hero>.txt per hero.

    Each file is tagged with the real hero name so ingest.py attaches the tier /
    win-rate / pick-rate chunk to that hero. Returns the number of files written.
    """
    print("Scraping metabot.gg tier list ...")
    try:
        entries = fetch_tier_list(session)
    except requests.RequestException as exc:
        print(f"  FAILED: {exc}")
        return 0
    if not entries:
        print("  WARNING: no tier entries parsed (page structure may have changed).")
        return 0

    DOCUMENTS_DIR.mkdir(exist_ok=True)
    for hero, description in sorted(entries.items()):
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", hero).strip("_") or "hero"
        path = DOCUMENTS_DIR / f"Meta_{slug}.txt"
        lines = [
            f"HERO: {hero}",
            f"SOURCE: {METABOT_TIER_URL}",
            "=" * 60,
            "",
            "## SECTION: Tier & Meta",
            description,
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  saved {len(entries)} hero meta files (Meta_*.txt).")
    return len(entries)


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #
def save_document(hero: str, url: str, sections) -> Path:
    """Write a section-marked text file into documents/."""
    DOCUMENTS_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", hero).strip("_") or "page"
    path = DOCUMENTS_DIR / f"{slug}.txt"

    lines = [f"HERO: {hero}", f"SOURCE: {url}", "=" * 60, ""]
    for title, text in sections:
        lines.append(f"## SECTION: {title}")
        lines.append(text)
        lines.append("")  # blank line between sections

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def scrape_page(session: requests.Session, page: str, hero_name: str) -> bool:
    """Scrape a single wiki page and save it. Returns True on success."""
    url = page_url(page)
    print(f"  scraping {hero_name:<22} {url}")
    try:
        resp = polite_get(session, url)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"    FAILED: {exc}")
        return False

    sections = extract_sections(resp.text)
    if not sections:
        print("    WARNING: no sections extracted (page layout may differ).")
        return False

    path = save_document(hero_name, url, sections)
    print(f"    saved {len(sections)} sections -> {path.name}")
    return True


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Scrape deadlock.wiki hero pages.")
    parser.add_argument(
        "--check", action="store_true",
        help="Only verify the wiki is reachable (HTTP GET + status). No scraping.",
    )
    parser.add_argument(
        "--list-only", action="store_true",
        help="Discover hero pages and print them without scraping.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Scrape at most this many hero pages (overview pages always included).",
    )
    parser.add_argument(
        "--heroes", nargs="+", metavar="HERO",
        help="Scrape only these specific hero page titles (skips discovery).",
    )
    parser.add_argument(
        "--meta", action="store_true",
        help="Scrape only the metabot.gg tier list (tier / win rate / pick rate).",
    )
    args = parser.parse_args(argv)

    session = make_session()

    if args.check:
        return check_reachable(session)

    if args.meta:
        count = scrape_tier_list(session)
        print(f"\nDone. {count} meta files saved into {DOCUMENTS_DIR}/.")
        return 0 if count else 1

    # Resolve which hero pages to scrape.
    if args.heroes:
        heroes = list(args.heroes)
    else:
        print("Discovering hero pages from /Heroes ...")
        heroes = discover_hero_links(session)
        print(f"  found {len(heroes)} candidate hero pages.")

    if args.limit is not None:
        heroes = heroes[: args.limit]

    if args.list_only:
        print("\nOverview pages:")
        for _hero, page in OVERVIEW_PAGES:
            print(f"  - {page}")
        print(f"\nHero pages ({len(heroes)}):")
        for h in heroes:
            print(f"  - {h}")
        return 0

    print(f"\nScraping {len(OVERVIEW_PAGES)} overview pages + {len(heroes)} hero pages...")
    ok = 0
    total = 0
    for hero_name, page in OVERVIEW_PAGES:
        total += 1
        ok += scrape_page(session, page, hero_name)
    for page in heroes:
        total += 1
        hero_name = unquote(page).replace("_", " ")
        ok += scrape_page(session, page, hero_name)

    # Source #3: metabot.gg tier list (tier / win rate / pick rate per hero).
    meta_count = scrape_tier_list(session)

    print(f"\nDone. {ok}/{total} wiki pages + {meta_count} meta files "
          f"saved into {DOCUMENTS_DIR}/.")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
