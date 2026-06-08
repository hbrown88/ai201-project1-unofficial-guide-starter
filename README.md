# The Unofficial Guide — Project 1

> **How to use this template:**
> Complete each section *after* you've built and tested the corresponding part of your system.
> Do not write placeholder text — if a section isn't done yet, leave it blank and come back.
> Every section below is required for submission. One-liners will not receive full credit.

---

## Domain

This system covers Georgia Tech student engagement — registered student organizations, campus events, campus recreation programs, career development opportunities, and off-campus Atlanta activities. The knowledge is valuable because the official GT pages are scattered across a dozen different sites (GT Engage, the CRC, the Career Center, the Arts center, Discover Atlanta, etc.) with no single place to ask a natural-language question and get a grounded answer. Official pages are also optimized for browsing, not Q&A — they don't explain *why* a student would care about a given org or event, and they require knowing where to look in advance.

---

## Document Sources

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | GT Engage — Student Organizations | API (CampusLabs discovery API) | https://gatech.campuslabs.com/engage/organizations |
| 2 | GT Engage — Campus Events | API (CampusLabs discovery API) | https://gatech.campuslabs.com/engage/events |
| 3 | GT Campus Calendar | HTML (scraped) | https://calendar.gatech.edu/event/listings |
| 4 | Student Center Programs Council (SCPC) | HTML (scraped) | https://studentcenter.gatech.edu/scpc |
| 5 | Campus Recreation Center — Programs | HTML (scraped) | https://crc.gatech.edu/programs/ |
| 6 | GT Career Center — Workshops | HTML (scraped) | https://career.gatech.edu/workshops/ |
| 7 | GT Career Fair | HTML (scraped) | https://careerfair.gatech.edu/ |
| 8 | Georgia Tech Arts (Ferst Center) | HTML (scraped) | https://arts.gatech.edu/events |
| 9 | Center for Student Engagement | HTML (scraped) | https://studentengagement.gatech.edu/ |
| 10 | Ramblin' Wreck Athletics | HTML (scraped) | https://ramblinwreck.com/ |
| 11 | Discover Atlanta — Events | HTML (scraped) | https://discoveratlanta.com/events/all/ |
| 12 | Eventbrite — Atlanta Events | HTML (scraped) | https://www.eventbrite.com/d/ga--atlanta/events/ |

Note: r/gatech (Reddit) was in the original plan but returned HTTP 403 during fetch and contributed no documents. The GT Campus Calendar page is JavaScript-rendered and returned an empty shell; it is listed above for completeness but produced no usable chunks.

---

## Chunking Strategy

**Chunk size:** 150–200 tokens, counted with the all-MiniLM-L6-v2 tokenizer (the same tokenizer used by the embedding model), which keeps every chunk comfortably under that model's 256-token context limit.

**Overlap:** 50 tokens. Each chunk carries 50 tokens of context from the prior chunk so that a sentence that straddles a boundary is fully represented in at least one chunk.

**Why these choices fit your documents:** The corpus is a mix of two document types. HTML pages (CRC, SCPC, Career Center, etc.) are medium-length descriptions — a 150–200 token window keeps one coherent section (e.g., "Group Fitness" or "Intramural Sports") together without splitting it. GT Engage organization and event records are short by nature — a single org listing is often 30–80 tokens — so those chunks naturally fall below the 150-token target. The overlap matters most for the HTML pages where a program description may run longer than 200 tokens and must be split.

Preprocessing before chunking: HTML is stripped to plain text using Python's HTMLParser (script/style/noscript tags dropped, block elements emit line breaks). Whitespace is normalized (collapsed repeated blank lines, trimmed lines). Documents with no readable text after cleaning are skipped entirely.

**Final chunk count:** 1,060 chunks across 11 sources. GT Engage organizations, GT Engage events, and Eventbrite events are chunked one-record-per-chunk (so each org or event embeds as its own vector and a specific query like "photography club" matches it precisely). HTML prose pages (CRC, SCPC, Career Center, Discover Atlanta, etc.) use the 150–200 token sliding window with 50-token overlap. Token distribution: 18–200 tokens per chunk; the short tail reflects the compact directory-listing format of the record-style sources.

---

## Embedding Model

**Model used:** `sentence-transformers/all-MiniLM-L6-v2`, run locally via the `sentence-transformers` library with ChromaDB as the vector store.

This model was chosen because it runs entirely on CPU with no API key, no rate limits, and no inference cost — critical for a project where the embedding step needs to be re-run whenever documents are updated. Its 256-token context window matches the chunk size target exactly. It produces 384-dimensional dense vectors that work well for English-language semantic similarity.

**Production tradeoff reflection:** If I were deploying this for real users and cost weren't a constraint, I'd weigh several factors. For accuracy, OpenAI's `text-embedding-3-large` or Cohere's `embed-v3` produce substantially higher-quality embeddings for domain-specific text, especially for short queries that are phrased differently from the document text. For context length, `text-embedding-3-large` supports 8,191 tokens, which would let me embed longer document sections without chunking as aggressively. For latency, a locally-hosted model like all-MiniLM-L6-v2 has zero network round-trip, which matters for a real-time UI. For multilingual support, GT has a large international student population — a multilingual model like `multilingual-e5-large` would handle queries in other languages. The main trade-off is accuracy vs. cost/latency: API-hosted models are more accurate but add ~100ms per query and per-token cost.

---

## Grounded Generation

**System prompt grounding instruction:**

The system prompt (in `generate.py`) enforces grounding through five explicit rules given to the model before every query:

```
You are "The Unofficial Guide," a question-answering assistant for Georgia Tech
student engagement and events.
Follow these rules without exception:
1. Answer using ONLY the information in the CONTEXT block. Do not use any
   prior, outside, or general knowledge.
2. If the CONTEXT does not contain enough information to answer, reply with
   exactly this sentence and nothing else: "I don't have enough information on that."
3. Never invent organizations, events, dates, locations, or links that are
   not present in the CONTEXT.
4. Quote names, dates, and locations exactly as they appear in the CONTEXT.
   If a relevant 'More info:' link is in the CONTEXT, include it.
5. Be concise and specific.
```

Beyond the prompt, grounding is enforced structurally in two additional ways:

- **Relevance floor (MIN_SCORE = 0.38):** Before the LLM is called at all, the top-k retrieved chunks are filtered by cosine similarity. If none clear 0.38, the function returns the refusal string immediately — the LLM is never invoked. This threshold was calibrated empirically: off-domain queries score ≤0.32 against this corpus; genuine in-domain questions score ≥0.46.
- **Programmatic source attribution:** The `Sources:` list appended to every answer is computed in Python from the retrieval metadata (chunk `source` fields), not generated by the model. This means sources are guaranteed to be real URLs from the index, not invented citations.

**How source attribution is surfaced in the response:**

After the model's answer text, the function appends a `Sources:` block listing the unique URLs from the retrieved chunks. This is done in Python (`format_sources()` in `generate.py`), completely independent of what the model writes, so the model cannot fabricate or omit a source.

---

## Evaluation Report

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | What upcoming events are there on campus or in the city that can help enhance my resume? | AI hackathon on 6/10 at the CRC with signup link | Named 3 career-relevant GT Engage events: Resume Workshop (NSBE, 7/11/26), Experiential Learning Showcase (10/30/26), International Opportunities Open House (9/1/26) — with links; Eventbrite in sources | Relevant | Partially accurate — correct event type and real links, but expected event (AI hackathon) was not in the corpus |
| 2 | I finished class around 1pm today and don't have anything else planned. What is going on on campus today that I could attend? | Weekly market on Tech Green 12–5pm, basketball tournament at CRC 6pm | "I don't have enough information on that." (refusal) | Partially relevant — future events retrieved (July/Aug 2026) but none match today's date (June 8, 2026) | Inaccurate — corpus is a fixed snapshot with no real-time event data |
| 3 | I'm new to campus and want to meet people who are into photography. Are there any student organizations at Georgia Tech I could join? | Photography Club on GT Engage with org page link | "Photography @ GT (PGT) — inclusive environment for all skill levels. More info: https://gatech.campuslabs.com/engage/organization/photography-at-gt" | Relevant | Accurate |
| 4 | I want to stay active but don't like working out alone. What group fitness or intramural options does the Campus Rec Center have? | 20+ group fitness classes (cycling, yoga, martial arts), intramural sports via IMLeagues | Listed 20+ non-credit fitness classes, intramural sports for Men's/Women's/Co-Rec, 44 sport clubs — sourced to CRC and GT Engage; also surfaced GT Swim Club | Relevant | Partially accurate — correct programs, IMLeagues not mentioned, swim club added tangentially |
| 5 | It's the weekend and I want to get off campus. What's a free or cheap thing to do in Atlanta? | Specific free event with link (e.g. Piedmont Park Green Market) | Named Amplify Decatur Music Festival and Atlanta Greek Picnic but acknowledged the corpus doesn't confirm cost; noted Eventbrite and Discover Atlanta as sources | Partially relevant — Eventbrite + Discover Atlanta chunks retrieved, but no chunk has explicit "free" pricing metadata | Partially accurate — finds real Atlanta events but cannot confirm "free or cheap" from retrieved text |

**Retrieval quality:** Relevant / Partially relevant / Off-target  
**Response accuracy:** Accurate / Partially accurate / Inaccurate

---

## Failure Case Analysis

**Question that failed:**
"It's the weekend and I want to get off campus. What's a free or cheap thing to do in Atlanta?"

**What the system returned:**
Named the Amplify Decatur Music Festival and Atlanta Greek Picnic but added: *"the CONTEXT does not specify if it's free or not"* — hedging rather than answering the actual question.

**Root cause (tied to a specific pipeline stage):**
This is a **document quality / fetch stage** failure. Retrieval works correctly: chunks from both Discover Atlanta and Eventbrite are retrieved with scores above the MIN_SCORE floor, and the LLM is called with real event context. The problem is that neither the Discover Atlanta scraper nor the Eventbrite ld+json parser captures admission cost. On Discover Atlanta, pricing is rendered in CSS badge elements (`Free`, `$10–$20`) that are stripped during HTML cleaning. On Eventbrite, the schema.org `ld+json` block used to extract events doesn't include an `offers` or `isAccessibleForFree` field for this listing page. The model is left with event names and descriptions but no pricing signal, so it correctly hedges rather than inventing a cost claim.

**What you would change to fix it:**
Two complementary fixes: (1) In the fetch stage, extract cost/pricing text before stripping HTML from Discover Atlanta — look specifically for badge/tag elements and price spans and include them in the cleaned text. (2) For Eventbrite, request individual event detail pages or use Eventbrite's API which returns structured `ticket_availability` and `is_free` fields, then prepend `[Free]` or `[Paid — $X]` to each event block so the embedding captures that attribute and the model can answer definitively.

---

## Spec Reflection

**One way the spec helped you during implementation:**
The planning.md Architecture section defined strict pipeline boundaries — each milestone (ingest → embed → retrieve → generate) had its own inputs and outputs specified before any code was written. This paid off when GT Engage and the campus calendar turned out to be JavaScript-rendered SPA shells that returned empty HTML. Because the boundary between fetch and ingest was clean, I could swap in a direct CampusLabs API client (fetching the discovery endpoint for orgs and events as structured JSON) without touching a single line in embed.py or generate.py. The architecture diagram made the module boundary load-bearing, not cosmetic.

**One way your implementation diverged from the spec, and why:**
The spec assumed HTML scraping would work for all 10 sources, including GT Engage organizations, GT Engage events, and the campus calendar. In practice, all three are client-side-rendered SPAs — a plain HTTP GET returns ~33 characters of meaningful HTML. The implementation diverged by adding direct API-based fetchers for GT Engage (pulling the Anthology/CampusLabs discovery API for `/organizations` and `/events`) and emitting their data as plain-text files with one block per record. This was not anticipated in the spec at all and required understanding the underlying API by inspecting network requests. The divergence was necessary — without it, the two most information-rich sources (718 registered orgs, ~76 upcoming events) would have contributed zero chunks.

---

## AI Usage

**Instance 1**

- *What I gave the AI:* The Chunking Strategy section from planning.md (target: 150–200 tokens, 50-token overlap, rationale tied to the all-MiniLM-L6-v2 tokenizer) and asked Claude Code to implement `chunk_text()`.
- *What it produced:* A sliding window function that split on character count with a fixed 800-character window and 200-character overlap, using `len()` to measure size.
- *What I changed or overrode:* I overrode the split unit entirely — character count does not match what the embedding model sees, which is subword tokens. I directed the implementation to use the all-MiniLM-L6-v2 tokenizer's `encode()` and `decode()` cycle to count and split by actual token IDs, so a 200-token chunk is exactly 200 tokens in the model's vocabulary, not an approximation.

**Instance 2**

- *What I gave the AI:* The Generation stage from the planning.md Architecture diagram (Groq/Llama-3 via the `groq` client, retrieved chunks as context, grounding requirement) and the requirement that answers stay grounded with source citation.
- *What it produced:* A `generate_answer()` function with a system prompt that told the model to "answer only from the provided context." Source attribution was left to the model — it was expected to include the source URL if it appeared in a chunk.
- *What I changed or overrode:* I added two grounding mechanisms the AI did not include: (1) the structural MIN_SCORE threshold (0.38) that prevents the LLM from being called at all when no relevant chunks pass — this turns grounding from a prompt suggestion into a hard guarantee; and (2) programmatic source attribution, where the `Sources:` list is computed in Python from retrieval metadata rather than relying on the model to mention the URL. Both changes were explicitly directed because I wanted grounding to be a code-level property of the system, not a behavioral property of the model.
