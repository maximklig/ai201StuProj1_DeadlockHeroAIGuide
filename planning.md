# Project 1 Planning: The Unofficial Guide

---

## Domain

The Domain I chose pertains to the unreleased Valve game, "Deadlock". Deadlock is a MOBA 3rd person hero shooter
and has a mix of game mechanics that may be difficult for players to understand. In addition Deadlock is technically in
alpha / playtest, continously updating with weekly and even daily patches that have the potential to change the game completely.
With this being said, any new player who gets invited to the play test are thrust upon new game mechanics, an immense 
roster of heroes, and what seems to be an obscene amount of items/abilities to choose from to work specifically with their specific character.
I would also like to pointout that I have been playing the game for roughly 2 years and have amounted to 850~ hours.

---

## Documents

| #      | Source      | URL or location                                 | Description                                         |
|--------|-------------|-------------------------------------------------|-----------------------------------------------------| 
| 1      | URL/Scraper | https://deadlock.wiki/Hero_Comparison_Table     | Comparative stats across all heroes                 |
| 2      | URL/Scraper | https://deadlock.wiki/Heroes                    | General hero mechanics, how abilities work          |
| 3      | URL/Scraper | https://metabot.gg/en/deadlock/heroes/tier-list | Win rates, pick rates, meta context                 |
| 4 - 41 | URL/Scraper | https://deadlock.wiki/[Hero Name]               | Abilities, stats, lore per hero                     |
| 42     | URL/Scraper | https://deadlock.wiki/Abilities                 | How ability unlocks, upgrades, spirit scaling works |
| 43     | URL/Scraper | https://deadlock.wiki/Items                     | Item builds, what synergizes with abilities         |

---

## Chunking Strategy

<!-- How will you split documents into chunks?
     State your chunk size (in tokens or characters), overlap size, and explain why those
     numbers fit the structure of your documents.
     A review-heavy corpus warrants different chunking than a long FAQ. -->

**Chunk size: 400 Characters (ROughly 80 - 100 tokens)**

**Overlap: 80 characters (roughly 16 - 20 tokens)**

**Reasoning: 400 characters with 80 characters is enough to capture a sentence from the deadlock wiki. 
Sentences are long though to capture an idea about a specific ability, item, or hero specific detail but
short enough to not go endlessley into specifics.**

---

## Retrieval Approach

<!-- Which embedding model are you using (e.g., all-MiniLM-L6-v2 via sentence-transformers)?
     How many chunks will you retrieve per query (top-k)?
     If you were deploying this for real users and cost wasn't a constraint, what tradeoffs
     would you weigh in choosing a different embedding model — context length, multilingual
     support, accuracy on domain-specific text, latency? -->

**Embedding model: Groq - all-MiniLM-L6-v2 via sentence-transformers**

**Top-k: 5**

**Production tradeoff reflection: If possible I would use a llm such as GPT-4o to have better context awarness,
reasoning for output, and nuanced output that helps the beginning player understand some game mechanics/heroes. 
**

---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

| # | Question                                                                              | Expected answer |
|---|---------------------------------------------------------------------------------------|-----------------|
| 1 | Does Haze throw a knife when using her ultimate ability (or ult for deadlock jargon)? | |
| 2 | How many playable heroes are in the game?                                             | |
| 3 | What tier is Ivy placed at?                                                           | |
| 4 | What is Ivy's pick rate and win rate?                                                 | |
| 5 | Does Haze have a passive ability?                                                     | |

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1. An issue which can occur is inconsistency in font and layout for the heroes in the wiki
leading to an issue in which the scraper / url converter exports the wrong information, or misses information.

2. Another issue I forsee are chunk splicing in where the chunks don't hold the full sentence of data and get clipped 
and are unable to give the user asking the query a fully informative answer, a wrong answer, or a partial answer.

---

## Architecture

┌─────────────────────┐
│  Document Ingestion │  ← requests + BeautifulSoup (wiki.deadlock.gg)
└────────┬────────────┘
         │
┌────────▼────────────┐
│      Chunking       │  ← custom chunk_text() — 400 char / 80 overlap
└────────┬────────────┘
         │
┌────────▼────────────┐
│  Embedding +        │  ← sentence-transformers (all-MiniLM-L6-v2)
│  Vector Store       │    + ChromaDB (local)
└────────┬────────────┘
         │
┌────────▼────────────┐
│     Retrieval       │  ← ChromaDB similarity search, top-k = 5
└────────┬────────────┘
         │
┌────────▼────────────┐
│     Generation      │  ← LLM (course-specified) + retrieved chunks as context
└─────────────────────┘

---

## AI Tool Plan

<!-- For each part of the pipeline below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, which requirements)
     - What you expect it to produce
     - How you'll verify the output matches your spec

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Chunking Strategy section and ask it to implement chunk_text()
     with my specified chunk size and overlap" is a plan. -->

**Milestone 3 — Ingestion and chunking:**
For the ingestion portion I will be converting the above URLs into a raw data JSON file. The tags
will be abilities 1-3, pasive or active, upgrades, the 3 tags assocaited with the hero's, overview of the heroes,
the heroes weapon name, and specifics. This will be done using a scraper.py (BeautifulSOup and requests).
There will be a chunk_text() function that adheres to those parameters set and will tag each chunk with hero name + 
source section. The strategy will be to have the Chunks contain 400 characters with an 80 character overlap.

**Milestone 4 — Embedding and retrieval:**
I will code to embed chunks with the Groq API Key - all-MiniLM-L6-v2 and store it all into a chromaDB collection.

**Milestone 5 — Generation and interface:**
I will make a query function that takes a user question, retrieves top-5 chunks, and passes them to an
LLM with a prompt. 