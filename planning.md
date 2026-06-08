# Project 1 Planning: The Unofficial Guide

> Write this document before you write any pipeline code.
> Your spec and architecture diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Update the Retrieval Approach and Chunking Strategy sections if you change your approach during implementation.
> Update this file before starting any stretch features.

---

## Domain

<!-- What domain did you choose? Why is this knowledge valuable and hard to find through official channels? -->

--- I chose Student Engagement & Events as my domain because as a college student at Georgia Tech, I sometimes find myself looking for something new to do on campus or in the city. The idea behind this AI is to help bridge that gap and provide unique and various engagement opportunities. The hardest part about finding this information is the way a lot of the sources are formatted, many with multiple links or short explanations.

## Documents

<!-- List your specific sources: URLs, subreddit names, forum threads, or file descriptions.
     Aim for at least 10 sources that together cover different subtopics or perspectives within your domain. -->

| # | Source | Description | URL or location |
|---|--------|-------------|-----------------|
| 1 | r/gatech (Reddit) | Student voice — candid threads on what to do when bored, hidden gems, club opinions, weekend plans, and survival advice. Captures perspective official pages won't. | https://www.reddit.com/r/gatech/ |
| 2 | GT Engage (Anthology/CampusLabs) | Directory of ~600 registered student organizations plus campus event listings — the canonical "what clubs and events exist" source. | https://gatech.campuslabs.com/engage/ (orgs: `/engage/organizations` · events: `/engage/events`) |
| 3 | Georgia Tech Campus Calendar | Official institute-wide calendar of events open to the Tech community: talks, festivals, socials, info sessions. | https://calendar.gatech.edu/event/listings |
| 4 | Student Center Programs Council (SCPC) | Student-run programming — concerts, movie nights, Homecoming, Midnight Breakfast, and Atlanta trips. Core leisure/social events. | https://studentcenter.gatech.edu/scpc |
| 5 | Campus Recreation (CRC) | Active leisure — intramural sports, sport clubs, group fitness classes, outdoor rec trips, and how to sign up. | https://crc.gatech.edu/programs/ |
| 6 | GT Career Center — Workshops & Career Fairs | Professionalism — resume/interview workshops, employer info sessions, and all-majors/college career fairs. | https://career.gatech.edu/workshops/ · https://careerfair.gatech.edu/ |
| 7 | Georgia Tech Arts (Ferst Center) | Arts & culture leisure — performances, DramaTech theater, School of Music concerts, exhibitions, and festivals. | https://arts.gatech.edu/events |
| 8 | Center for Student Engagement | Official hub on how to get involved — org registration, campus traditions, leadership programs, and engagement resources. | https://studentengagement.gatech.edu/ |
| 9 | Ramblin' Wreck Athletics | Game-day events and student spirit — football/basketball schedules, student tickets, and traditions. | https://ramblinwreck.com/ |
| 10 | Discover Atlanta — Events | Off-campus leisure for students leaving campus — Midtown/Atlanta concerts, festivals, food, and free things to do. | https://discoveratlanta.com/events/all/ |
| 11 | Eventbrite — Atlanta Events | Ticketed and free events in the Atlanta area (concerts, workshops, networking, community events) not always listed on official GT pages. | https://www.eventbrite.com/d/ga--atlanta/events/ |

---

## Chunking Strategy

<!-- How will you split documents into chunks?
     State your chunk size (in tokens or characters), overlap size, and explain why those
     numbers fit the structure of your documents.
     A review-heavy corpus warrants different chunking than a long FAQ. -->

**Chunk size:** 150-200 tokens

**Overlap:** 50 token overlap

**Reasoning:** A lot of the links have a title for the event or engagement opportunity and then a small description of what it is. This chunk size and overlap should provide specific context per chunk

---

## Retrieval Approach

<!-- Which embedding model are you using (e.g., all-MiniLM-L6-v2 via sentence-transformers)?
     How many chunks will you retrieve per query (top-k)?
     If you were deploying this for real users and cost wasn't a constraint, what tradeoffs
     would you weigh in choosing a different embedding model — context length, multilingual
     support, accuracy on domain-specific text, latency? -->

**Embedding model:** `all-MiniLM-L6-v2` via `sentence-transformers` (local CPU, no API key required)

**Top-k:** 5

**Production tradeoff reflection:** Tradeoffs that I would consider would be language support and event specifics. Since this AI has access to the links, I would leave most of the inspection to lie in the users hands by allowing them to click on the link and find any specifics that the AI can't answer on their own

---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | What upcoming events are there on campus or in the city that can help enhance my resume? | There is an AI hackathon taking place in three days 6/10 on campus at the campus rec center. Here is the link for signup [Expected Link]|
| 2 | I finished class around 1:00pm today and don't have anything else planned for the rest of the day. What is going on on campus today that I could attend?| Today Georgia Tech is hosting their weekly market on Tech Green from 12-5 and there is a basketball tournament being held at the Campus Rec Center starting at 6pm|
| 3 | I'm new to campus and want to meet people who are into photography. Are there any student organizations at Georgia Tech I could join? | Yes, Georgia Tech has a Photography Club registered on Engage. The AI should name the org, mention how to view its meetings, and point me to the org page to contact a leader. [Expected Link] |
| 4 | I want to stay active but don't like working out alone. What group fitness or intramural options does the Campus Rec Center have? | The CRC offers 20+ group fitness classes (e.g. cycling, yoga, martial arts) that require a group fitness membership, plus intramural sports for men's, women's, and co-rec teams that you sign up for through IMLeagues. [Expected Link] |
| 5 | It's the weekend and I want to get off campus. What's a free or cheap thing to do in Midtown Atlanta? | A short walk/bus from campus, Piedmont Park hosts the free Saturday Green Market in season; Discover Atlanta also lists free Midtown festivals and concerts for that weekend. The AI should name a specific option and link it. [Expected Link] |

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1. Events that get postponed or cancelled due to weather or unforeseen reasons may have trouble being recognized and explained to the user.

2. The way some of these links are formatted could cause chunking issues due to the way the texts are formatted in different tabs and sometimes different links.

---

## Architecture

<!-- Draw a diagram of your pipeline showing the five stages:
     Document Ingestion → Chunking → Embedding + Vector Store → Retrieval → Generation
     Label each stage with the tool or library you're using.
     You can use ASCII art, a Mermaid diagram, or embed a sketch as an image.
     You'll use this diagram as context when prompting AI tools to implement each stage. -->

--- 
+----------------------+       +-----------------------+       +-------------------------+
| [ DOCUMENT INGEST ]  |       |     [ CHUNKING ]      |       |      [ EMBEDDING ]      |
|                      |       |                       |       |                         |
|      /=======/       |       |   Sentence A.=========|       |   ~~~~~~~~~~~~~~~~~~~   |
|     /       /  ======+======>|                       +======>|                         |
|    /_______/  /      |       |   Sentence B.=========|       |   all-MiniLM-L6-v2      |
|      /_______/       |       |                       |       |                         |
|     (LangChain)      |       |  (Semantic Splitter)  |       |     (HuggingFace)       |
+----------------------+       +-----------------------+       +-------------------------+
                                                                            |
                                                                            v
+----------------------+       +-----------------------+       +-------------------------+
|    [ GENERATION ]    |       |     [ RETRIEVAL ]     |       |     [ VECTOR STORE ]    |
|                      |       |                       |       |       .-------.         |
|        +----+        |       |       .-.   | | |     |       |      /   .   /|         |
|        | LLM|        |<======+       | |===| | |     |<======+     +-------+ |         |
|        +----+        |       |       '-'   | | |     |       |     |   .   |/          |
|                      |       |                       |       |     '-------'           |
| (Groq / Llama-3)     |       |        ( k = 5 )      |       |    (ChromaDB)           |
+----------+-----------+       +-----------------------+       +------------+------------+
           |                                                                ^
           |                                                                |
           v                                                            [ Query ]
     [ AI Response ]

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

- *AI tool:* Claude / Claude Code, Github Copilot if needed.
- *Input I'll give it:* My **Documents** table, **Chunking Strategy** section (150–200 token chunks, 50 token overlap), and the **Architecture** diagram's ingestion/chunking stages. I'll tell it the corpus is mostly short event/org listings — a title plus a brief description, sometimes with a link — and that ingestion reads from the `documents/` folder.
- *What I expect it to produce:* A `load_documents()` function that reads my saved sources (HTML/text, with `pdfplumber` only if I add PDFs) and strips boilerplate, plus a `chunk_text()` function using a semantic/recursive splitter set to ~150–200 tokens with 50 token overlap, returning chunks that keep each event's title and description together along with its source URL for attribution.
- *How I'll verify it:* Print a sample of chunks and confirm sizes land in my 150–200 token range, overlap is present, and no single event gets split mid-description (my anticipated chunking risk). I'll also confirm every chunk carries its source link so I can surface attribution later.

**Milestone 4 — Embedding and retrieval:**

- *AI tool:* Claude / Claude Code.
- *What I'll give it:* My **Retrieval Approach** section (all-MiniLM-L6-v2 via sentence-transformers, top-k = 5) and the embedding/vector-store/retrieval stages of the **Architecture** diagram, plus the chunk objects produced in Milestone 3 and the note that I'm using ChromaDB.
- *What I expect it to produce:* Code that embeds each chunk with `all-MiniLM-L6-v2`, persists vectors + source metadata in a ChromaDB collection, and a `retrieve(query, k=5)` function that embeds the query and returns the 5 nearest chunks with their text, source URL, and similarity score.
- *How I'll verify it:* Run my 5 **Evaluation Plan** questions through `retrieve()` and check that the top-k chunks are actually on-topic (e.g., Q3 returns the Photography Club org chunk, Q4 returns CRC group-fitness/intramural chunks). I'll eyeball similarity scores to make sure off-topic chunks aren't ranking high, which is my off-topic-retrieval risk.

**Milestone 5 — Generation and interface:**

- *AI tool:* Claude / Claude Code for the prompt + generation logic.
- *What I'll give it:* The generation stage of the **Architecture** diagram (Groq / Llama-3 via the `groq` client, key from `.env`), the retrieved chunks from Milestone 4, my 5 **Evaluation Plan** questions and their expected answers, and the requirement that answers must stay grounded in retrieved context and cite the source link.
- *What I expect it to produce:* A `generate_answer(query, chunks)` function that builds a prompt injecting the retrieved chunks as context, with a system instruction to answer only from that context, say "I don't have that information" when the context doesn't cover it, and include the relevant source URL — plus a simple Gradio or Streamlit interface that takes a question and shows the answer with its sources.
- *How I'll verify it:* Run all 5 evaluation questions end-to-end and compare responses to my expected answers, confirming each answer cites a real source link from the retrieved chunks. I'll also ask an out-of-domain question to confirm it refuses rather than hallucinating, and sanity-check that postponed/cancelled-event wording (my first anticipated challenge) is handled honestly rather than invented.

---

## Changes during development

<!-- Running log of where the implementation diverged from the original plan above, and why. -->

### Pipeline as built
- **`fetch_documents.py`** (scrape) → **`ingest.py`** (clean + chunk → `chunks.json`) → **`embed.py`** (embed + ChromaDB + `retrieve()`). The raw scrape is saved verbatim to `documents/raw/` first so cleaning/chunking is reproducible offline.
- **Embedding model:** the plan said "Semantic"; the actual model is **`all-MiniLM-L6-v2`** via `sentence-transformers` (local, no API key), exactly as the diagram shows. Vectors are L2-normalized and stored in a **persistent ChromaDB** collection using **cosine** distance.

### Fetching
- **Recovered the JavaScript-rendered sources via their JSON APIs.** A plain GET of GT Engage (orgs + events) and the campus calendar returned empty SPA shells (~33 chars after cleaning). I added API-based fetchers that pull the Anthology/CampusLabs **discovery API** directly: **718 registered organizations** and **~76 upcoming events**, emitted as clean text with one block per org/event and each item's own deep link for attribution. This was the single biggest quality win — it is what makes the "photography org" and "upcoming events" questions answerable at all.
- **Bug fixed — stale events.** My first events pull returned 307 events *all dated 2016*: the `endsAfter` timestamp was formatted as `...+00:00`, and the `+` decoded to a space in the URL, silently voiding the filter. Fixed by using a `Z` suffix, URL-quoting the value, and adding a Python-side "ends after now" filter as backup. Result: only genuinely upcoming events (2026–2027).
- **`sources.json` is now merged, not overwritten,** so a source that is temporarily unreachable on a re-run (e.g. Discover Atlanta intermittently returns 403) keeps the attribution from its previously-saved file.
- **Still blocked (documented, not fixed):** r/gatech returns HTTP 403 to all automated requests (Reddit is OAuth-only now), and the campus calendar's Localist API path 404s. Both contribute no chunks; recover by browser "Save As" if needed.

### Cleaning
- Upgraded HTML cleaning from tag-stripping to **subtree removal** (drop `<nav>`/`<footer>`/`<aside>`/forms/scripts, ARIA landmark roles, and class/id chrome like cookie/share/sidebar/comments), a **line-level filter** (UI labels, social handles, "Read more", cookie notices), and **cross-document boilerplate removal** (lines repeated across ≥ half the pages = shared GT header/footer). Also normalized exotic/zero-width whitespace (`\xa0`, `​`). Guardrail learned the hard way: never apply class heuristics to `body`/`html`/`main`/`article` — WordPress layout classes there (`has-sidebar`, an `ad` token) were nuking whole pages.

### Chunking
- **Directory-style sources (the Engage org/event pulls) are chunked one record per chunk** instead of packed to 150–200 tokens (`chunk_records()` in `ingest.py`, triggered for `campuslabs.com/engage` sources). Packing ~3 orgs per chunk diluted the signal so much that "Photography @ GT" never surfaced; one-record-per-chunk made it the **#1 hit (0.62)** for the verbatim Q3. Trade-off: these records are intentionally below the 150-token target, so the "% within 150–200" stat drops — precision matters more than size for a lookup directory. Prose pages (CRC, SCPC, Discover Atlanta, …) still use the original 150–200 / 50-overlap `chunk_text()`.
- **Total chunks: 1,060** across 11 usable documents (within the healthy 50–2,000 band). Largest sources: Engage orgs 731, Discover Atlanta 175, Engage events 105, Eventbrite 32.

### Retrieval
- `retrieve(query, k=5)` now over-fetches `k×4` candidates and re-ranks with **Maximal Marginal Relevance** (`mmr_lambda=0.8`, relevance-favoring) to suppress near-duplicate / "magnetic" overview chunks, plus an optional **`min_score`** floor so generation (M5) can refuse low-relevance matches instead of being fed noise. Also removed the orgs/events directory **header lines**, which were forming a chunk that matched every "student organizations" query.
- **Chunk metadata** stored for attribution: `source` (URL) and `position` (index within the document), per the M4 requirement.
- After these changes the 5 eval queries retrieve sensibly: Q1→resume workshops, Q2→real upcoming events, Q3→Photography @ GT (#1), Q4→CRC programs (#1), Q5→Discover Atlanta / Piedmont Park (#1). Remaining soft spot: broad campus-life org descriptions still occasionally rank above a more specific page (e.g. a couple of club orgs above CRC's fitness detail on Q4) — a k/threshold tuning question for after M5.

### Sources (M6 addition)
- **Added Eventbrite — Atlanta Events** (`https://www.eventbrite.com/d/ga--atlanta/events/`) as source #11. Rationale: Discover Atlanta covers broad city events but Eventbrite surfaces ticketed and free community events (workshops, networking nights, concerts) that often go unlisted on official GT or city tourism pages — particularly relevant for Q1-style resume-building queries. Added to the Documents table above and to `sources.json`; fetched and re-indexed into `chunks.json`.

