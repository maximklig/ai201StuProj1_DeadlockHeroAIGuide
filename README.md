# The Unofficial Guide — Project 1

> **How to use this template:**
> Complete each section *after* you've built and tested the corresponding part of your system.
> Do not write placeholder text — if a section isn't done yet, leave it blank and come back.
> Every section below is required for submission. One-liners will not receive full credit.

---

## Domain

<!-- The Domain I chose pertains to the unreleased Valve game, "Deadlock". Deadlock is a MOBA 3rd person hero shooter
and has a mix of game mechanics that may be difficult for players to understand. In addition Deadlock is technically in
alpha / playtest, continously updating with weekly and even daily patches that have the potential to change the game completely.
With this being said, any new player who gets invited to the play test are thrust upon new game mechanics, an immense 
roster of heroes, and what seems to be an obscene amount of items/abilities to choose from to work specifically with their specific character.
I would also like to pointout that I have been playing the game for roughly 2 years and have amounted to 850~ hours. -->

---

## Document Sources

<!-- List every source you collected documents from.
     Be specific: include URLs, subreddit names, forum thread titles, or file names.
     Aim for variety — sources that together cover different subtopics or perspectives. -->

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

<!-- Describe your chunking approach with enough specificity that someone else could reproduce it.
     Include:
     - Chunk size (characters or tokens) and why that size fits your documents
     - Overlap size and why (or why not) you used overlap
     - Any preprocessing you did before chunking (e.g., stripping HTML, removing headers)
     - What your final chunk count was across all documents -->

**Chunk size: 400 Char **

**Overlap: 80 Char **

**Why these choices fit your documents: When evaluating the sources (primarily the deadlock wiki) and meta.gg
most of the information if not all are shorter style, descriptive sentences, focusing on specific gameplay mechanics
or information. These are not long convoluted guides or descriptions and 400 characters is roughly enough to capture a 
sentence or two pertaining to each hero. The 80 char overlap (20%) aims to preserve the idea of a sentence that spans
a chunk boundary. Chunking is done per section so that way a chunk never spans over 2 or more sections.**

**Final chunk count: 660 Chunks (over 41 sources)**

---

## Embedding Model

<!-- Name the embedding model you used and explain your choice.
     Then answer: if you were deploying this system for real users and cost wasn't a constraint,
     what tradeoffs would you weigh in choosing a different model?
     Consider: context length limits, multilingual support, accuracy on domain-specific text,
     latency, and local vs. API-hosted. -->

**Model used: Groq - all-MiniLM-L6-v2 via sentence-transformers**

**Production tradeoff reflection: **

---

## Grounded Generation

<!-- Explain how your system enforces grounding — how does it prevent the LLM from answering
     beyond the retrieved documents?
     Describe both your system prompt (what instruction you gave the model) and any structural
     choices (e.g., how you formatted the context, whether you filtered low-relevance chunks).
     Do not just say "I told it to use the documents" — show the actual instruction or explain
     the mechanism. -->

**System prompt grounding instruction:**
▎ You are a Deadlock game assistant. You ONLY answer using the document excerpts provided below. Do not use any knowledge from your training data.
▎
▎ Rules you must follow without exception:
▎ - If the answer is present in the excerpts, answer it directly and cite which source(s) it came from using the format: (Source: <url>)
▎ - If the excerpts do not contain enough information to answer the question, respond with exactly: "I don't have enough information on that."
▎ - Never speculate, infer, or answer from general game knowledge.
▎ - Never mention that you are an AI or reference your training data.

This was implimented in query.py

Within every retrieved chunk, the source url / hero / and section are prepended so the model checks
against what is being handed.
A fixed fallback string is implemented ("I don't have enough information on that") and the system prompt
pins the model to its verbatim, so a refusal is machine-detectable rather than a paraphrase.

**How source attribution is surfaced in the response:**
Sources are not taken from the LLM's text. After generation, _dedupe_sources() pulls the source field from each
retrieved chunk's ChromaDB metadata, deduplicates (first-seen order, so the closest chunk's source ranks first), and 
returns it as a separate sources list. The Gradio UI renders these as • {url} bullets in the "Retrieved from" box.
So even if the model mis-cites or omits a citation in its prose, the displayed source list is grounded in the retrieval 
metadata, not the generation.

---

## Evaluation Report

<!-- Run your 5 test questions from planning.md through your system and record the results.
     Be honest — a partially accurate or inaccurate result that you explain well is more
     valuable than a suspiciously perfect result. -->

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | Does Haze throw a knife when using her ultimate ability? | No - her ultimate is Bullet Dance (gunfire); the knife is her Sleep Dagger, a basic ability | "I don't have enough information on that." (top chunk: Haze/Overview, dist 0.438) | Partially relevant | Partially accurate |
| 2 | How many playable heroes are in the game? | 38 (per the wiki Heroes page) | "There are currently 38 heroes available... (Source: deadlock.wiki/Heroes)" | Relevant | Accurate |
| 3 | What tier is Ivy placed at? | A-tier | "Ivy is a A-tier champion (Source: metabot.gg tier-list)" | Relevant | Accurate |
| 4 | What is Ivy's pick rate and win rate? | 27.2% pick, 52.5% win (Patch 2026) | "Ivy's pick rate is 27.2% and her win rate is 52.5%... (Source: metabot.gg)" | Relevant | Accurate |
| 5 | Does Haze have a passive ability? | Yes - Fixation is her passive | "I don't have enough information on that." (top chunk: Haze/Tier & Meta, dist 0.423) | Off-target | Inaccurate |

**Retrieval quality:** Relevant / Partially relevant / Off-target  
**Response accuracy:** Accurate / Partially accurate / Inaccurate

---

## Failure Case Analysis

<!-- Identify at least one question where retrieval or generation did not work as expected.
     Write a specific explanation of *why* it failed, tied to a part of the pipeline.

     "The answer was wrong" is not an explanation.

     "The relevant information was split across a chunk boundary, so retrieval returned
     only half the context — the model didn't have enough to answer correctly" is an explanation.

     "The embedding model treated the professor's nickname as out-of-vocabulary and returned
     results from an unrelated review" is an explanation. -->

**Question that failed:"Does Haze have a passive ability?"**

**What the system returned:"I don't have enough information on that."**

**Root cause (tied to a specific pipeline stage): Despite giving claude an outline to do so, when all the data was scraped
no chunk holds the word "passive" for haze despite her third ability being passive, being described so, but never labeled
as so. The retriever falls back to generic Haze-similarity and returns Tier & Meta (0.423), Overview, Trivia, and 
Backstory — the Fixation chunk isn't even in the top-5. And even if it were, the grounded LLM would still be right to 
refuse, because the chunk never states Fixation is a passive. The grounding behaved correctly given a corpus that 
doesn't encode the fact the question asks about.**

**What you would change to fix it: I would fix it in upstream within the scraper/ingest program and have every hero's 
ability labeled with a passive or active tag.**

---

## Spec Reflection

<!-- Reflect on how planning.md shaped your implementation.
     Answer both questions with at least 2–3 sentences each. -->

**One way the spec helped you during implementation: Spec helped me during implementation by creating an outline of the
direction this project would be heading. It helped in seperating the main goal into smaller steps which then can be 
expounded on through the use of claude and were used as a set of directions for Claude.**

**One way your implementation diverged from the spec, and why: Originally I was supposed to **
have items as well being scraped but I thought against it since I wanted to put an emphasis on the heroes
themselves.

---

## AI Usage

<!-- Describe at least 2 specific instances where you used an AI tool during this project.
     For each: what did you give the AI as input, what did it produce, and what did you
     change, override, or direct differently?

     "I used Claude to help me code" is not sufficient.
     "I gave Claude my Chunking Strategy section from planning.md and asked it to implement
     chunk_text(). It returned a function using a fixed character split. I overrode the
     chunk size from 500 to 200 because my documents are short reviews, not long guides." -->

**Instance 1**

- *What I gave the AI: I asked Claude to build scraper.py in order to pull all information from the deadlock
wiki pages and mark each section in the output so ingest.py could tag the chunks by section. I also curated
a text document 'OutlineForMyself.txt' whih lists the fields I wanted to be implemented and sorted by which includes:*
each ability regarding an individual hero, ability upgrade points, the three description tags per hero, passive/active
decriptive factors, and hero statistics. 
- *What it produced: A lot of noise/clutter in the data scraped from the wikis and issues such as hero stat tables
being captured twice (Once flattened, once row by row). Ability sections contained unlabled stat numbers and completely
missed ability description text as well as the three description tags assocaited with every hero.*
- *What I changed or overrode: I directed to test the scraper on 3 original heroes (as their data is at this point of the 
game is well documented and are for the most part static) which allowed me to capture these problems. 
I had claude rewrite the extractor to capture the ability description prose, herotags, the three upgrade tiers, whilst 
identifying and skipping over the chrome sections and de-duplicating the stat tables. Once everything was confirmed
I confirmed everything was being scraped correctly and ran it against the other 38 heroes. *

**Instance 2**

- *What I gave the AI: I gave Claude a Milestone 5 spec to build query.py with an ask(question) function
that embeds the question with the SAME all-MiniLM-L6-v2 model, pulls the top-5 chunks, and calls a Groq
hosted LLM with a strict system prompt that forbids using training knowledge. I ran my three test queries
against it, including "Does Haze throw a knife when using her ultimate ability?" which I expected to come
back grounded with a source.*
- *What it produced: Instead of an answer the system returned "I don't have enough information on that"
and I asked claude why. It inspected the corpus and showed me the question has a false premise - Haze's
ultimate is Bullet Dance (a gun ability, no knife), the knife is a seperate basic ability called Sleep Dagger.
So the excerpts never say her ultimate involves a knife and the grounded model refused rather than
hallucinating a yes. To prove the system does answer when the premise is right it ran "Does Haze throw a
knife with her Sleep Dagger?" which came back grounded and cited the source.*
- *What I changed or overrode: I directed that the grounding NOT be weakened to force a "yes" on that test.
Refusing to rubber-stamp a false premise is the correct behavior and is a stronger demonstration of grounding
than a plausible sounding answer. I kept all three original test queries as-is for the record and noted that
test 1's "failure" is actually the system working - it cites when supported and refuses when the question
assumes a fact the documents don't contain.*
