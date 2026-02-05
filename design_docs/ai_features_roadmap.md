# AI Features Roadmap

**Document Version:** 1.0
**Created:** 2026-02-05
**Status:** Planning

---

## Executive Summary

Curious Now aggregates science news into clusters. AI features transform it from a **news aggregator** into a **science understanding platform** by:

1. Making complex science accessible to non-experts
2. Providing context and meaning, not just headlines
3. Tracking how stories evolve over time
4. Enabling discovery through semantic understanding

---

## Feature Overview

| Feature | Stage | Priority | Complexity | Dependencies |
|---------|-------|----------|------------|--------------|
| Takeaways | 3 | P0 | Low | LLM API |
| Intuition | 3 | P1 | Low | LLM API |
| Deep-Dives | 3 | P1 | Medium | LLM API |
| Citation Validation | 3 | P2 | Medium | LLM + Web |
| Update Detection | 4 | P1 | Medium | LLM API |
| Story Lineage | 4 | P2 | High | LLM + Graph |
| Semantic Search | 7 | P0 | Medium | Embedding API |

---

## Detailed Feature Specifications

### 1. Takeaways (Stage 3)

**Priority:** P0 - Critical
**Complexity:** Low
**Database Field:** `story_clusters.takeaway`

#### Description
AI-generated 1-2 sentence summary explaining what a story means and why it matters.

#### Current State
```
Cluster: "New CRISPR variant enables precise gene editing in neurons"
User sees: headline + list of 5 source articles
User must: Read multiple articles to understand significance
```

#### With AI
```
Cluster: "New CRISPR variant enables precise gene editing in neurons"

Takeaway: "Scientists developed a CRISPR modification that works
in brain cells, potentially enabling treatments for Huntington's
and Parkinson's that were previously impossible."
```

#### User Value
- Instantly understand *why this matters*
- No need to read multiple articles for basic understanding
- Decide quickly whether to dive deeper

#### Implementation

**Input:**
- Cluster canonical title
- Top 3-5 source article titles and snippets
- Topic tags

**Prompt Template:**
```
You are a science journalist writing for curious non-scientists.

Given these related news articles about a science story:
{articles}

Write a 1-2 sentence takeaway that explains:
1. What happened (the core finding/event)
2. Why it matters (the significance)

Rules:
- Use plain language, no jargon
- Be specific, not vague
- Focus on implications for the reader
- Maximum 280 characters
```

**Output:**
- Single takeaway string
- Confidence score (0-1)

**Trigger:**
- Run when cluster is created or updated
- Re-run if new high-quality sources added

**API Cost Estimate:**
- ~500 tokens per cluster
- At 10,000 clusters/month: ~$5-15/month (Claude Haiku)

---

### 2. Intuition Field (Stage 3)

**Priority:** P1 - High
**Complexity:** Low
**Database Field:** `story_clusters.intuition`

#### Description
Plain-language explanation that builds mental models for non-experts using analogies and simplified concepts.

#### Example

**Technical (from source):**
```
"The modified Cas9 enzyme shows reduced off-target effects
in post-mitotic cells due to enhanced PAM specificity."
```

**Intuition (AI-generated):**
```
"Think of CRISPR like molecular scissors. The old scissors
sometimes cut the wrong DNA in brain cells. These new scissors
are much more precise—important because brain cells don't
regenerate, so you can't undo mistakes."
```

#### User Value
- Complex science becomes accessible
- Builds lasting understanding, not just awareness
- Appeals to "curious but not expert" audience

#### Implementation

**Input:**
- Cluster title and takeaway
- Technical snippets from sources
- Glossary terms mentioned

**Prompt Template:**
```
You are explaining a science concept to a smart friend who
isn't a scientist.

Topic: {title}
Key point: {takeaway}
Technical details: {snippets}

Write 2-3 sentences that:
1. Use an analogy or comparison to everyday things
2. Explain the core concept in plain language
3. Highlight why the technical detail matters

Avoid: jargon, hedging, unnecessary caveats
```

**Output:**
- Intuition text (100-200 words)
- Analogies used (for quality tracking)

---

### 3. Deep-Dive Content (Stage 3)

**Priority:** P1 - High
**Complexity:** Medium
**Database Field:** `story_clusters.deep_dive` (JSONB)

#### Description
Structured explainer content that provides comprehensive context beyond the news.

#### Structure
```json
{
  "what_happened": "...",
  "why_it_matters": "...",
  "background": "...",
  "limitations": "...",
  "whats_next": "...",
  "related_concepts": ["...", "..."],
  "generated_at": "2026-02-05T10:00:00Z",
  "source_count": 5
}
```

#### Example

**Cluster:** "FDA approves first CRISPR-based therapy"

**Deep-Dive:**
```
## What Happened
The FDA approved Casgevy, a CRISPR-based treatment for sickle
cell disease, marking the first time a gene-editing therapy
has received regulatory approval in the US.

## Why It Matters
This approval validates CRISPR as a therapeutic platform, not
just a research tool. It opens the door for treatments targeting
genetic diseases that were previously untreatable.

## Background
CRISPR was discovered in 2012. Early attempts at therapy faced
safety concerns about unintended edits. Casgevy works by editing
cells outside the body, reducing risk.

## Limitations
- Treatment costs ~$2 million per patient
- Requires hospitalization for bone marrow extraction
- Only approved for sickle cell, not other genetic diseases yet

## What's Next
Clinical trials are underway for CRISPR treatments targeting:
- Beta-thalassemia (blood disorder)
- Certain inherited blindness conditions
- Some forms of cancer
```

#### User Value
- One-stop understanding without external research
- Balanced view including limitations
- Context that news articles often skip

#### Implementation

**Input:**
- Full text of top 5 sources (or summaries)
- Cluster metadata
- Related glossary entries
- Previous clusters on similar topics (for context)

**Prompt Template:**
```
You are a science educator creating a comprehensive explainer.

News sources:
{sources}

Create a deep-dive with these sections:
1. What Happened (2-3 sentences, factual)
2. Why It Matters (2-3 sentences, implications)
3. Background (3-4 sentences, context needed to understand)
4. Limitations (bullet points, caveats and concerns)
5. What's Next (2-3 sentences, future directions)

Rules:
- Cite specific facts from sources
- Acknowledge uncertainty where it exists
- No hype or exaggeration
- Reading level: educated non-specialist
```

**API Cost Estimate:**
- ~2000 tokens per cluster
- At 1,000 deep-dives/month: ~$10-30/month

---

### 4. Citation Validation (Stage 3)

**Priority:** P2 - Medium
**Complexity:** Medium
**Database Field:** `story_clusters.citation_check` (JSONB)

#### Description
AI verifies that claims in the takeaway/deep-dive are supported by the source material, flagging potential overstatements.

#### Output Structure
```json
{
  "validated": true,
  "confidence": 0.92,
  "flags": [],
  "checked_claims": [
    {
      "claim": "First FDA-approved CRISPR therapy",
      "supported": true,
      "source": "FDA press release"
    }
  ]
}
```

#### Flags (when validation fails)
```json
{
  "flags": [
    {
      "type": "overstatement",
      "claim": "Cures all genetic diseases",
      "issue": "Sources only mention sickle cell approval",
      "suggestion": "Specify this applies to sickle cell disease"
    }
  ]
}
```

#### User Value
- Trust in AI-generated content
- Prevents misinformation
- Transparency about certainty levels

#### Implementation
- Run after takeaway/deep-dive generation
- Compare generated claims against source text
- Flag discrepancies for human review or auto-correction

---

### 5. Automatic Update Detection (Stage 4)

**Priority:** P1 - High
**Complexity:** Medium
**Database Table:** `update_log_entries`

#### Description
AI detects when a story has meaningful new developments and generates human-readable update summaries.

#### Example

**Original Cluster (January):**
```
"New Alzheimer's drug shows promise in Phase 3 trials"
```

**New Article (March):**
```
"FDA advisory committee votes 6-0 to recommend Alzheimer's drug approval"
```

**AI-Generated Update:**
```
Update Type: Regulatory Progress
Summary: "The Alzheimer's drug from our January story received
unanimous recommendation for FDA approval. The committee cited
strong Phase 3 results despite earlier controversy about
efficacy data."
Change: Trial Results → Regulatory Approval Pending
```

#### Update Types
- `new_findings` - Additional research results
- `regulatory` - FDA/EMA decisions
- `replication` - Study confirmed or contradicted
- `application` - Real-world implementation
- `controversy` - Scientific dispute or retraction
- `follow_up` - Continuation of previous research

#### User Value
- Stay informed on stories they care about
- Understand *what changed*, not just "new article"
- Notification emails become valuable, not noise

#### Implementation

**Trigger:**
- New item added to existing cluster
- Run comparison against cluster summary

**Input:**
- Existing cluster takeaway and deep-dive
- New article content
- Time since last update

**Prompt Template:**
```
Compare this new article to the existing story summary.

Existing story:
{takeaway}
{deep_dive_summary}

New article:
{new_article}

Determine:
1. Is this a meaningful update or just another report of the same thing?
2. If meaningful, what type of update? (new_findings, regulatory, replication, application, controversy, follow_up)
3. Write a 2-sentence update summary explaining what changed.

If not meaningful, respond with: {"meaningful": false}
```

**Output:**
```json
{
  "meaningful": true,
  "update_type": "regulatory",
  "summary": "...",
  "changes": ["Trial Results → Regulatory Approval Pending"]
}
```

---

### 6. Story Lineage (Stage 4)

**Priority:** P2 - Medium
**Complexity:** High
**Database Tables:** `lineage_nodes`, `lineage_edges`

#### Description
AI maps how scientific topics connect and evolve over time, creating a knowledge graph of scientific progress.

#### Example: mRNA Technology Lineage
```
mRNA Vaccine Research (2010s)
    │
    ├──→ COVID-19 mRNA Vaccines (2020)
    │        │
    │        ├──→ mRNA Booster Strategies (2021)
    │        │
    │        └──→ mRNA Flu Vaccines (2023)
    │
    └──→ mRNA Cancer Vaccines (2022)
             │
             └──→ Personalized Cancer Immunotherapy (2024)
```

#### Edge Types
- `leads_to` - Research A enabled Research B
- `builds_on` - Incremental progress
- `contradicts` - Conflicting findings
- `applies` - Basic research → Application
- `combines` - Multiple fields merge

#### User Value
- See the "arc" of scientific progress
- Understand connections between stories
- Navigate related topics naturally

#### Implementation

**Approach 1: Retrospective Analysis**
- Periodically analyze clusters within a topic
- Identify temporal and conceptual relationships
- Build graph edges

**Approach 2: Real-Time Linking**
- When new cluster created, find related predecessors
- Ask LLM to characterize relationship
- Add edge if meaningful connection exists

**Prompt Template:**
```
Given these two science stories:

Story A (earlier):
{title_a}
{takeaway_a}
Date: {date_a}

Story B (later):
{title_b}
{takeaway_b}
Date: {date_b}

Are these stories connected? If yes:
1. Relationship type: leads_to, builds_on, contradicts, applies, combines
2. Explain the connection in one sentence
3. Confidence (0-1)

If not meaningfully connected, respond: {"connected": false}
```

---

### 7. Semantic Search (Stage 7)

**Priority:** P0 - Critical
**Complexity:** Medium
**Database:** `story_clusters.embedding` (vector), pgvector extension

#### Description
Search by meaning rather than keywords, enabling users to find relevant content even when terminology differs.

#### Current State (Full-Text Search)
```
Query: "gene therapy for blindness"
Results: Only articles containing "gene therapy" AND "blindness"
Misses: "CRISPR retinal treatment restores vision in mice"
Misses: "Luxturna FDA approval for inherited eye disease"
```

#### With Semantic Search
```
Query: "gene therapy for blindness"
Results:
1. "CRISPR retinal treatment restores vision" (0.89 similarity)
2. "Luxturna approved for inherited retinal dystrophy" (0.87)
3. "Gene therapy clinical trials for Leber's disease" (0.85)
4. "Optogenetics approach to treating blindness" (0.82)
```

#### User Value
- Find content without knowing exact terminology
- Discover related topics they didn't know to search for
- More forgiving of spelling/phrasing variations

#### Implementation

**Embedding Generation:**
```python
def generate_cluster_embedding(cluster):
    text = f"{cluster.title}. {cluster.takeaway}. {cluster.topic_names}"
    embedding = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return embedding.data[0].embedding  # 1536 dimensions
```

**Search Query:**
```sql
SELECT
    id, canonical_title, takeaway,
    1 - (embedding <=> query_embedding) AS similarity
FROM story_clusters
WHERE status = 'active'
ORDER BY embedding <=> query_embedding
LIMIT 20;
```

**Hybrid Approach (Recommended):**
```python
def search(query: str):
    # Get semantic results
    query_embedding = generate_embedding(query)
    semantic_results = vector_search(query_embedding, limit=50)

    # Get keyword results
    fts_results = full_text_search(query, limit=50)

    # Combine with reciprocal rank fusion
    combined = reciprocal_rank_fusion(semantic_results, fts_results)

    return combined[:20]
```

**API Cost Estimate:**
- Embedding generation: ~$0.02 per 1M tokens
- 10,000 clusters: ~$0.50 one-time
- Search queries: ~$0.0001 per query

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
```
1. Set up LLM API integration (Claude or GPT-4)
2. Create embedding pipeline for existing clusters
3. Implement semantic search endpoint
4. Generate takeaways for existing clusters
```

**Deliverables:**
- [ ] `curious_now/ai/llm_client.py` - LLM API wrapper
- [ ] `curious_now/ai/embeddings.py` - Embedding generation
- [ ] `curious_now/ai/takeaways.py` - Takeaway generation
- [ ] Migration: Add embedding column to story_clusters
- [ ] CLI: `python -m curious_now.cli generate_embeddings`
- [ ] CLI: `python -m curious_now.cli generate_takeaways`

### Phase 2: Understanding Layer (Week 3-4)
```
1. Implement intuition field generation
2. Implement deep-dive generation
3. Add citation validation
4. Create admin UI for reviewing AI content
```

**Deliverables:**
- [ ] `curious_now/ai/intuition.py`
- [ ] `curious_now/ai/deep_dive.py`
- [ ] `curious_now/ai/citation_check.py`
- [ ] Admin endpoint: `GET /v1/admin/ai/review-queue`
- [ ] Admin endpoint: `PATCH /v1/admin/clusters/{id}/ai-content`

### Phase 3: Update Intelligence (Week 5-6)
```
1. Implement update detection
2. Generate update summaries
3. Integrate with notification system
4. Build lineage detection (basic)
```

**Deliverables:**
- [ ] `curious_now/ai/update_detection.py`
- [ ] `curious_now/ai/lineage.py`
- [ ] Enhanced notification emails with AI summaries
- [ ] CLI: `python -m curious_now.cli detect_updates`

### Phase 4: Polish & Scale (Week 7-8)
```
1. Caching layer for AI responses
2. Batch processing optimization
3. Quality monitoring dashboard
4. A/B testing for AI content
```

---

## Technical Architecture

### LLM Integration
```
┌─────────────────────────────────────────────────────────┐
│                    curious_now/ai/                       │
├─────────────────────────────────────────────────────────┤
│  llm_client.py      - API wrapper (Claude/GPT)          │
│  embeddings.py      - Vector embedding generation       │
│  takeaways.py       - Takeaway generation               │
│  intuition.py       - Intuition field generation        │
│  deep_dive.py       - Deep-dive content generation      │
│  citation_check.py  - Claim validation                  │
│  update_detection.py - Story update analysis            │
│  lineage.py         - Story relationship mapping        │
│  prompts/           - Prompt templates (version controlled) │
└─────────────────────────────────────────────────────────┘
```

### Data Flow
```
New Cluster Created
        │
        ▼
┌───────────────────┐
│ Generate Embedding │ ──→ Store in story_clusters.embedding
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Generate Takeaway  │ ──→ Store in story_clusters.takeaway
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Generate Intuition │ ──→ Store in story_clusters.intuition
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Generate Deep-Dive │ ──→ Store in story_clusters.deep_dive
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Validate Citations │ ──→ Flag for review if issues found
└───────────────────┘
```

### New Item Added to Existing Cluster
```
New Item Added
        │
        ▼
┌───────────────────┐
│ Detect Update      │ ──→ Is this meaningful?
└───────────────────┘
        │ Yes
        ▼
┌───────────────────┐
│ Generate Summary   │ ──→ Store in update_log_entries
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Update Cluster AI  │ ──→ Refresh takeaway/deep-dive if needed
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Notify Watchers    │ ──→ Include AI summary in notification
└───────────────────┘
```

---

## Cost Projections

### Monthly Estimates (10,000 active clusters)

| Operation | Volume | Cost (Claude) | Cost (GPT-4) |
|-----------|--------|---------------|--------------|
| Takeaways | 2,000 new/mo | $3-5 | $8-12 |
| Intuition | 2,000 new/mo | $5-8 | $15-20 |
| Deep-Dives | 1,000 new/mo | $10-20 | $30-50 |
| Update Detection | 10,000 items/mo | $5-10 | $15-25 |
| Embeddings | 2,000 new/mo | $0.50 | $0.50 |
| Search Queries | 100,000/mo | $2 | $2 |
| **Total** | | **$25-45/mo** | **$70-110/mo** |

### Recommendations
- Use **Claude Haiku** for high-volume tasks (takeaways, updates)
- Use **Claude Sonnet** for complex tasks (deep-dives, lineage)
- Use **OpenAI text-embedding-3-small** for embeddings (best price/performance)

---

## Quality Assurance

### Guardrails
1. **No medical advice** - Detect and remove treatment recommendations
2. **Uncertainty language** - Require hedging for preliminary findings
3. **Source attribution** - All claims must trace to sources
4. **Hype detection** - Flag superlatives ("breakthrough", "cure")

### Human Review Queue
- All AI content with confidence < 0.8 goes to review
- Random 5% sample for quality monitoring
- All content flagged by citation validation

### Feedback Loop
- Track user engagement with AI content
- A/B test different prompt versions
- Collect explicit feedback (helpful/not helpful)

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Takeaway helpfulness | >80% positive | User feedback |
| Deep-dive read rate | >30% of views | Analytics |
| Search success rate | >70% find relevant | Click-through |
| Update notification CTR | >15% | Email analytics |
| Time on site | +40% | Before/after |
| Return visit rate | +25% | Cohort analysis |

---

## Open Questions

1. **LLM Provider:** Claude vs GPT-4 vs open-source (Llama)?
2. **Embedding Model:** OpenAI vs Cohere vs local (sentence-transformers)?
3. **Human Review:** How much editorial oversight for AI content?
4. **Caching Strategy:** How long to cache AI responses?
5. **Incremental Updates:** Regenerate all AI content when sources change, or patch?

---

## Appendix: Database Schema Additions

```sql
-- Already exists, needs population:
ALTER TABLE story_clusters
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Confidence tracking:
ALTER TABLE story_clusters
    ADD COLUMN IF NOT EXISTS ai_confidence JSONB DEFAULT '{}'::jsonb;

-- Example ai_confidence structure:
-- {
--   "takeaway": {"score": 0.92, "generated_at": "2026-02-05T10:00:00Z"},
--   "intuition": {"score": 0.88, "generated_at": "2026-02-05T10:00:00Z"},
--   "deep_dive": {"score": 0.85, "generated_at": "2026-02-05T10:00:00Z"}
-- }

-- AI content review queue:
CREATE TABLE IF NOT EXISTS ai_review_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id UUID NOT NULL REFERENCES story_clusters(id),
    content_type TEXT NOT NULL, -- takeaway, intuition, deep_dive
    reason TEXT NOT NULL, -- low_confidence, citation_flag, random_sample
    status TEXT NOT NULL DEFAULT 'pending', -- pending, approved, rejected, edited
    reviewer_id UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

*Document maintained by: Engineering Team*
*Last updated: 2026-02-05*
