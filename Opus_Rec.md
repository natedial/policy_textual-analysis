This is a compelling project—tracking the subtle semiotics of Fed communications is genuinely valuable for rates trading. The spec and diagnosis in Document 3 are astute: you're right that counting adjectives misses the point entirely. Fed-speak operates at the level of deliberate framing choices, not lexical frequency.

Let me propose a more rigorous architecture that treats this as a **semantic interpretation problem** rather than a diff problem.

---

## Core Insight: Two-Stage Semantic Extraction

The fundamental issue is that raw text comparison can't capture *intent*. A sentence like "inflation remains elevated" vs "inflation remains somewhat elevated" is a single word change with significant policy implications. You need to extract **structured semantic representations** first, then compare those.

### Stage 1: Thematic Decomposition

For each speech, extract a structured "semantic fingerprint" across a **fixed taxonomy of Fed concerns**:

```
INFLATION: {
  overall_stance: "concerned" | "neutral" | "optimistic",
  trajectory_view: "accelerating" | "sticky" | "moderating" | "controlled",
  emphasis_weight: 0-10,
  key_hedges: ["somewhat", "largely", "remains"],
  causal_attributions: ["shelter", "services", "goods"],
  confidence_level: "high" | "moderate" | "uncertain"
}

LABOR_MARKETS: { ... }
FINANCIAL_CONDITIONS: { ... }
HOUSING: { ... }
CONSUMER_SPENDING: { ... }
POLICY_STANCE: { ... }
BALANCE_OF_RISKS: { ... }
```

This taxonomy becomes your **comparison scaffold**. Instead of asking "what sentences changed," you ask "how did the stance on housing shift?"

### Stage 2: Delta Interpretation

Compare fingerprints to generate structured deltas:

```
{
  theme: "INFLATION",
  shift_type: "SOFTENING",
  from: { stance: "concerned", trajectory: "sticky" },
  to: { stance: "concerned", trajectory: "moderating" },
  evidence: [
    { old_text: "Inflation remains elevated", new_text: "Inflation has eased but remains above target" }
  ],
  interpretation: "Acknowledging disinflation progress while maintaining vigilance",
  market_implication: "Marginally dovish—reduces urgency for further tightening"
}
```

---

## The Orphaned Concepts Problem

Your Day 1 requirement for orphan detection is actually the hardest part. It requires:

1. **Concept extraction**: What ideas are present in speech N?
2. **Concept tracking**: Which of those appeared in speeches N-1, N-2, ... N-k?
3. **Absence detection**: What was present before but is now missing?
4. **Significance filtering**: Is the absence meaningful or just topic-dependent?

The naive approach (check if phrase X appears) fails because the same concept can be expressed many ways. "Transitory inflation" → "temporary price pressures" → "supply-chain-driven increases" are the same concept.

**Proposed solution**: Extract concepts at a semantic level, not lexical. Each speech produces a set of **concept embeddings** that can be compared across the corpus. An orphaned concept is one where the embedding similarity to any passage in the new speech falls below threshold.

---

## Architectural Refinement

### Data Model (Supabase)

```sql
-- Core entities
speeches (id, speaker_id, date, source_url, raw_text, speech_type)
speakers (id, name, institution, role, voting_status)

-- Semantic extractions (one per speech)
semantic_fingerprints (
  speech_id,
  theme,           -- e.g., 'INFLATION', 'LABOR_MARKETS'
  stance,          -- structured JSON
  emphasis_score,
  extracted_phrases,  -- array of key quotes
  embedding         -- vector for this theme's content
)

-- Concept tracking
concepts (
  id,
  canonical_name,   -- e.g., "transitory_inflation"
  description,
  first_seen_speech_id,
  last_seen_speech_id,
  embedding
)

concept_mentions (
  concept_id,
  speech_id,
  passage_text,
  confidence_score
)

-- Analysis outputs
detected_shifts (
  id,
  speech_id,
  comparison_speech_id,
  theme,
  shift_type,       -- 'HAWKISH_DRIFT', 'SOFTENING', 'NEW_EMPHASIS', 'ORPHANED'
  from_state,
  to_state,
  evidence,         -- JSON array of text pairs
  interpretation,
  market_implication,
  created_at
)
```

### Processing Pipeline

```
[New Speech Detected]
        ↓
[1. Ingest & Clean]
   - Scrape, extract main content, strip boilerplate
   - Normalize speaker attribution
        ↓
[2. Thematic Extraction] (LLM)
   - For each theme in taxonomy, extract stance/emphasis/hedges
   - Generate semantic_fingerprint rows
        ↓
[3. Concept Extraction] (LLM + Embeddings)
   - Identify discrete concepts discussed
   - Match to existing concepts or create new
   - Record concept_mentions
        ↓
[4. Comparative Analysis]
   - Pull fingerprints for same speaker's last N speeches
   - Compute deltas per theme
   - Check for orphaned concepts (present in N-1, absent in N)
        ↓
[5. Interpretation Synthesis] (LLM)
   - Generate natural language interpretation of each delta
   - Categorize shift type
   - Assess market implications
        ↓
[6. Store & Alert]
   - Write detected_shifts
   - Trigger notifications for significant changes
```

---

## LLM Prompt Strategy

The quality hinges on prompt engineering. Here's a sketch for thematic extraction:

```
You are an expert analyst of Federal Reserve communications. Given a speech, 
extract the speaker's stance on each of the following themes. For each theme:

1. OVERALL_STANCE: How does the speaker characterize current conditions?
2. TRAJECTORY: Does the speaker see improvement, deterioration, or stability?
3. EMPHASIS: How much of the speech is devoted to this topic? (1-10)
4. KEY_HEDGES: What qualifiers or hedging language is used?
5. CAUSAL_FACTORS: What does the speaker attribute developments to?
6. POLICY_IMPLICATION: What does this suggest about the speaker's policy preference?

Themes: INFLATION, LABOR_MARKETS, FINANCIAL_CONDITIONS, HOUSING, CONSUMER, 
        POLICY_STANCE, BALANCE_OF_RISKS, GLOBAL_FACTORS

Return structured JSON. If a theme is not discussed, return null for that theme.
```

---

## UI Redesign

The current side-by-side diff is the wrong metaphor. You want **insight-first, evidence-on-demand**:

```
┌─────────────────────────────────────────────────────────────────┐
│  SHIFT SUMMARY: Waller (Nov 7 → Nov 25)                         │
├─────────────────────────────────────────────────────────────────┤
│  🔴 HAWKISH DRIFT: Housing Inflation                            │
│     Emphasis: 3/10 → 7/10                                       │
│     Stance: "normalizing" → "persistently elevated"             │
│     [View Evidence ▼]                                           │
│                                                                 │
│  🟢 SOFTENING: Labor Markets                                    │
│     Trajectory: "tight" → "gradually cooling"                   │
│     New hedge: "consistent with our objectives"                 │
│     [View Evidence ▼]                                           │
│                                                                 │
│  ⚪ ORPHANED: "Supply chain normalization"                      │
│     Last mentioned: Oct 15 speech                               │
│     Appeared in 4 of last 6 speeches                            │
│     [View Historical Context ▼]                                 │
├─────────────────────────────────────────────────────────────────┤
│  MARKET IMPLICATION: Net hawkish shift. Housing concerns        │
│  suggest sensitivity to shelter CPI. Watch for rate path        │
│  guidance in December statement.                                │
└─────────────────────────────────────────────────────────────────┘
```

Clicking "View Evidence" expands to show the actual text passages side-by-side, but the *interpretation* is the primary interface, not the raw diff.

---

## Implementation Phases

**Phase 1 (MVP)**: 
- Manual speech ingestion (paste URL, scrape)
- Thematic extraction for single speech
- Pairwise comparison (pick two speeches)
- Basic Streamlit UI with insight cards

**Phase 2**: 
- Automated ingestion pipeline
- N-speech historical tracking
- Orphaned concept detection
- Speaker-specific baselines

**Phase 3**: 
- Real-time alerting
- Historical corpus backfill
- Cross-speaker comparison (FOMC consensus shifts)
- FOMC statement tracking (highly structured, different approach)

---

## Technical Decisions to Make

1. **Embedding model**: OpenAI `text-embedding-3-large` vs open-source (e.g., `bge-large`)? The former is simpler; the latter avoids API costs at scale.

2. **LLM for extraction**: Claude vs GPT-4? Claude tends to be better at nuanced interpretation; GPT-4 is more reliable at structured output. Could use Claude for interpretation, GPT for extraction.

3. **Scraping approach**: BeautifulSoup for static sites, Playwright for JS-rendered. Each Fed site will need a custom parser—worth investing in robust per-site extractors rather than generic "grab paragraphs."

4. **Taxonomy rigidity**: Should the theme list be fixed or extensible? Fixed is easier to compare across time; extensible catches emerging topics. I'd suggest fixed core + "OTHER" bucket that gets reviewed periodically.

---

The key philosophical shift is treating this as a **structured interpretation problem** rather than a diff problem. The LLM does the expert reading; the system organizes and tracks the insights over time.

---

# Definitive Plan: Fed Communications Analysis Tool
Based on the research, there's a rich body of work you can leverage. Here's what academia and industry teach us:

## Key Academic Insights
1. The "Trillion Dollar Words" Dataset & Framework (Shah et al., ACL 2023)
This is the most directly relevant work. Researchers at Georgia Tech constructed the largest tokenized and annotated dataset of FOMC speeches, meeting minutes, and press conference transcripts. They developed a novel hawkish-dovish classification task and benchmarked pre-trained language models, finding RoBERTa-large performed best. arXivarXiv
The critical insight from their annotation guide: The labeling was conducted according to a predefined annotation guide broken down into key sections such as economic status, dollar value change, energy/house prices, future expectations. A common occurrence was the existence of intentional mixed tone—the Federal Reserve by purpose serves to maintain financial/economic stability and any statement they make is projected in a moderating manner to reduce the chance of excess market reaction. arXiv
This means: You can't just do binary hawkish/dovish. The Fed intentionally hedges. Your tool needs to capture the degree and nuance of hedging.
2. Semantic Similarity as Signal (Ehrmann & Talmi, Journal of Monetary Economics 2020)
Over the past few years, several central banks have made their press releases announcing monetary policy decisions increasingly similar semantically. They often use the previous release as a starting point for drafting the current version, making only minor modifications to the text. This practice makes it easy to identify where the central bank has updated the wording and how the bank's views have evolved since the previous release. ScienceDirect
Their key finding: Using variation in the drafting process at the Bank of Canada, this paper finds that similar press releases reduce market volatility, whereas volatility rises when substantial changes occur after sequences of similar statements. ScienceDirect
This validates your core premise: The Fed intentionally drafts incrementally. Changes are signals. Your tool should track the baseline of similarity and flag deviations from that baseline.
3. Hansen, McMahon & Prat's LDA Approach (QJE 2018)
They used Latent Dirichlet Allocation to estimate 40 topics from FOMC transcripts, finding that "policymakers discuss markedly different aspects of the economy in any given meeting" and that "attention appears to fluctuate" across topics over time. Mcmahonecon
The 40 topics provide a rich description of all the language used on the FOMC, though not all are relevant to substantive deliberation. For example, topic 24 about regional economic conditions has the highest overall average share in FOMC1 at 8.3%; however in FOMC2 its share is the lowest at 0.4%. Sekhansen
This means: Topic modeling alone isn't enough—you need to distinguish between procedural/boilerplate topics and substantive policy topics. Your taxonomy should be curated, not purely data-driven.
4. CentralBankRoBERTa (Pfeifer & Marohl, 2023)
This study constructs CentralBankRoBERTa, a state-of-the-art economic agent classifier that distinguishes five basic macroeconomic agents and binary sentiment classifier that identifies the emotional content of sentences in central bank communications. The absence of large-language models in the central bank communications literature may be attributed to a lack of appropriately labeled datasets. ScienceDirect
Implication: Domain-specific fine-tuned models exist and outperform generic sentiment. You should leverage these rather than building from scratch.
5. The Loughran-McDonald Financial Dictionary
The sentiment categories are: negative, positive, uncertainty, litigious, strong modal, weak modal, and constraining. The dictionary reports counts, proportion of total, average proportion per document for each word. Nd
Key insight: The "uncertainty" and "modal" categories are crucial for Fed-speak. Words like "somewhat," "largely," "remains" aren't positive/negative—they're hedging signals. Your tool needs to track these separately.

## Synthesized Architecture
Based on these insights, here's a refined implementation plan:

### Phase 1: Foundation
1.1 Leverage Existing Resources

Use the Trillion Dollar Words dataset (available on HuggingFace: gtfintechlab/fomc-hawkish-dovish) for benchmarking
Use their fine-tuned RoBERTa model for sentence-level hawkish/dovish classification as a baseline
Integrate Loughran-McDonald dictionary for modal/uncertainty word detection

1.2 Build Your Semantic Extraction Layer
Instead of counting words, extract structured representations using an LLM (Claude API):
pythonEXTRACTION_PROMPT = """
Analyze this Fed speech passage and extract:

1. THEMES_DISCUSSED: List each economic theme mentioned
   (inflation, labor, housing, financial_conditions, consumer, global, policy_stance)

2. For each theme:
   - STANCE: {very_concerned, concerned, neutral, optimistic, very_optimistic}
   - TRAJECTORY: {worsening, stable_negative, stable, improving, improving_rapidly}
   - HEDGING_LEVEL: {none, light, moderate, heavy} 
   - KEY_HEDGES: List qualifier words used ("somewhat", "largely", etc.)
   - CONFIDENCE: {high, moderate, low, uncertain}
   - EMPHASIS: 1-10 (how much relative attention)

3. POLICY_IMPLICATIONS:
   - DIRECTION: {hawkish, neutral, dovish}
   - INTENSITY: 1-10
   - CONDITIONALITY: What conditions would change this stance?

4. NEW_CONCEPTS: Any ideas/phrases not in standard Fed vocabulary
5. DROPPED_CONCEPTS: (requires comparison to prior speech)

Return as structured JSON.
"""
1.3 Build the Comparison Engine
The Ehrmann-Talmi insight is crucial here. You need:
pythondef compute_semantic_delta(speech_a: SemanticFingerprint, speech_b: SemanticFingerprint):
    """
    Compare two semantic fingerprints and identify meaningful shifts.
    """
    deltas = []
    
    for theme in THEME_TAXONOMY:
        if theme in speech_a.themes and theme in speech_b.themes:
            # Compare stance, trajectory, hedging, emphasis
            stance_shift = compute_stance_shift(
                speech_a.themes[theme].stance,
                speech_b.themes[theme].stance
            )
            
            emphasis_delta = (
                speech_b.themes[theme].emphasis - 
                speech_a.themes[theme].emphasis
            )
            
            hedge_change = detect_hedge_change(
                speech_a.themes[theme].hedges,
                speech_b.themes[theme].hedges
            )
            
            if is_significant(stance_shift, emphasis_delta, hedge_change):
                deltas.append(ShiftRecord(
                    theme=theme,
                    shift_type=categorize_shift(stance_shift, emphasis_delta),
                    from_state=speech_a.themes[theme],
                    to_state=speech_b.themes[theme],
                    significance=compute_significance(...)
                ))
        
        elif theme in speech_a.themes and theme not in speech_b.themes:
            # ORPHANED CONCEPT
            deltas.append(ShiftRecord(
                theme=theme,
                shift_type="ORPHANED",
                from_state=speech_a.themes[theme],
                to_state=None,
                significance=compute_orphan_significance(theme, speech_history)
            ))
    
    return deltas

### Phase 2: Orphaned Concept Detection (Week 4)
This is your "Day 1 requirement" and the hardest part. Here's the approach:
2.1 Concept Embedding Approach
Rather than tracking phrases lexically, embed concepts semantically:
pythondef extract_concepts(speech_text: str) -> List[Concept]:
    """
    Extract discrete concepts from a speech.
    A concept is an idea that can be expressed multiple ways.
    """
    # Use LLM to extract concept descriptions
    concept_descriptions = llm_extract_concepts(speech_text)
    
    # Embed each concept description
    concepts = []
    for desc in concept_descriptions:
        concepts.append(Concept(
            description=desc,
            embedding=embed(desc),
            source_passages=find_source_passages(speech_text, desc)
        ))
    
    return concepts

def detect_orphaned_concepts(
    current_speech: Speech,
    historical_speeches: List[Speech],
    window_size: int = 5,
    threshold: float = 0.7
) -> List[OrphanedConcept]:
    """
    Find concepts that appeared in recent history but are absent now.
    """
    # Build concept set from historical window
    historical_concepts = {}
    for speech in historical_speeches[-window_size:]:
        for concept in speech.concepts:
            key = concept.canonical_id  # Cluster similar concepts
            if key not in historical_concepts:
                historical_concepts[key] = {
                    'concept': concept,
                    'appearances': 0,
                    'last_seen': None
                }
            historical_concepts[key]['appearances'] += 1
            historical_concepts[key]['last_seen'] = speech.date
    
    # Check which historical concepts are absent from current speech
    orphaned = []
    current_embeddings = [c.embedding for c in current_speech.concepts]
    
    for key, hist in historical_concepts.items():
        if hist['appearances'] >= 2:  # Only care about recurring concepts
            # Check if similar concept exists in current speech
            max_similarity = max(
                cosine_similarity(hist['concept'].embedding, curr_emb)
                for curr_emb in current_embeddings
            ) if current_embeddings else 0
            
            if max_similarity < threshold:
                orphaned.append(OrphanedConcept(
                    concept=hist['concept'],
                    last_seen=hist['last_seen'],
                    frequency_in_window=hist['appearances'],
                    absence_significance=compute_significance(hist)
                ))
    
    return orphaned
2.2 Example: Detecting "Transitory" Dropout
When "transitory inflation" disappeared from Fed communications, your system should detect:
json{
  "type": "ORPHANED_CONCEPT",
  "concept": "inflation_transitory_framing",
  "description": "Characterization of inflation as temporary/transitory",
  "last_seen": "2021-11-03",
  "frequency_in_window": "4 of last 5 speeches",
  "semantic_neighbors_in_current": [
    "inflation persistence concerns",
    "price pressures"
  ],
  "interpretation": "Speaker has dropped 'transitory' framing entirely, replaced with language emphasizing persistence",
  "market_significance": "HIGH - signals policy stance shift"
}

### Phase 3: Shift Categorization (Week 5)
Build a taxonomy of shift types that matter to traders:
```
pythonSHIFT_TAXONOMY = {
    "HAWKISH_DRIFT": {
        "indicators": ["stance more concerned", "trajectory worsening", "hedge reduction"],
        "themes": ["inflation", "labor_tightness", "financial_conditions"],
        "market_implication": "Rates higher for longer"
    },
    "DOVISH_PIVOT": {
        "indicators": ["stance softening", "trajectory improving", "new hedges added"],
        "themes": ["inflation", "growth_risks", "labor_cooling"],
        "market_implication": "Cut expectations should rise"
    },
    "NEW_RISK_EMPHASIS": {
        "indicators": ["new theme introduced", "emphasis spike on existing theme"],
        "themes": ["any"],
        "market_implication": "Potential policy consideration emerging"
    },
    "CONVICTION_CHANGE": {
        "indicators": ["confidence level change", "hedge intensity change"],
        "themes": ["any"],
        "market_implication": "Uncertainty about policy path"
    },
    "ORPHANED_CONCEPT": {
        "indicators": ["recurring concept absent"],
        "themes": ["any"],
        "market_implication": "Narrative shift, prior framing abandoned"
    }
}
```

### Phase 4: UI That Surfaces Insights First (Week 6)

The key insight from your earlier conversation: **don't make the user read the diff**. Present interpreted shifts with evidence on-demand.
┌────────────────────────────────────────────────────────────────────────┐
│  📊 ANALYSIS: Waller Speech Comparison                                  │
│  Nov 7, 2025 → Nov 25, 2025                                            │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  🔴 HAWKISH DRIFT: Housing Inflation                                   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                           │
│  Emphasis:  ████░░░░░░ 3/10  →  ███████░░░ 7/10                       │
│  Stance:    "normalizing" → "persistently elevated"                    │
│  Hedging:   Removed "largely" qualifier                                │
│                                                                        │
│  Market Take: Housing inflation now viewed as structural rather        │
│  than cyclical. Watch shelter CPI prints closely.                      │
│                                                                        │
│  [📄 View Text Evidence]  [📈 Historical Context]                      │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ⚪ ORPHANED: "Supply Chain Normalization"                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                           │
│  Last mentioned: Oct 15 speech (4 of last 6 speeches)                  │
│                                                                        │
│  This narrative framing is no longer being used. Supply-side           │
│  factors may now be considered fully resolved or irrelevant            │
│  to current inflation dynamics.                                        │
│                                                                        │
│  [📜 View Historical Usage]                                            │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  💡 SYNTHESIS                                                          │
│  Net hawkish shift. Housing concerns suggest sensitivity to shelter    │
│  CPI. Dropping supply-chain language indicates focus has moved to      │
│  demand-side factors. Watch for rate path guidance in December         │
│  statement.                                                            │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

Data Model Refinement
Based on the academic literature, here's the refined schema:
sql-- Core speech storage
speeches (
    id UUID PRIMARY KEY,
    speaker_id UUID REFERENCES speakers(id),
    date DATE NOT NULL,
    source_url TEXT,
    raw_text TEXT,
    speech_type ENUM('speech', 'testimony', 'interview', 'statement'),
    processed_at TIMESTAMP
);

-- Semantic extraction per speech
semantic_fingerprints (
    id UUID PRIMARY KEY,
    speech_id UUID REFERENCES speeches(id),
    theme TEXT,  -- from THEME_TAXONOMY
    stance TEXT,
    trajectory TEXT,
    emphasis_score FLOAT,
    hedging_level TEXT,
    key_hedges TEXT[],
    confidence_level TEXT,
    policy_direction TEXT,
    policy_intensity FLOAT,
    raw_extraction JSONB,  -- full LLM output
    created_at TIMESTAMP
);

-- Concept tracking (for orphan detection)
concepts (
    id UUID PRIMARY KEY,
    canonical_name TEXT,
    description TEXT,
    embedding VECTOR(1536),
    first_seen_speech_id UUID,
    last_seen_speech_id UUID,
    created_at TIMESTAMP
);

concept_mentions (
    id UUID PRIMARY KEY,
    concept_id UUID REFERENCES concepts(id),
    speech_id UUID REFERENCES speeches(id),
    passage_text TEXT,
    passage_location INT,  -- character offset
    confidence FLOAT
);

-- Analysis outputs
detected_shifts (
    id UUID PRIMARY KEY,
    speech_id UUID REFERENCES speeches(id),
    comparison_speech_id UUID,
    shift_type TEXT,  -- from SHIFT_TAXONOMY
    theme TEXT,
    from_state JSONB,
    to_state JSONB,
    evidence JSONB,  -- [{old_text, new_text, similarity}]
    interpretation TEXT,
    market_implication TEXT,
    significance_score FLOAT,
    created_at TIMESTAMP
);

-- For orphaned concepts specifically
orphaned_concepts (
    id UUID PRIMARY KEY,
    concept_id UUID REFERENCES concepts(id),
    detected_in_speech_id UUID REFERENCES speeches(id),
    last_seen_speech_id UUID,
    frequency_in_window INT,
    window_size INT,
    interpretation TEXT,
    created_at TIMESTAMP
);

Implementation Stack Recommendation
Based on what works in the literature:
ComponentRecommendationRationaleSentence ClassificationFine-tuned RoBERTa (use Trillion Dollar Words model)RoBERTa-large performed best on hawkish-dovish classification SSRNEmbeddingsOpenAI text-embedding-3-large or bge-large-en-v1.5High quality, well-tested on financial textSemantic ExtractionClaude API (claude-sonnet-4-20250514)Best at nuanced interpretation; structured outputDictionary BaselineLoughran-McDonald + custom Fed hedging wordsCategories include uncertainty, strong modal, weak modal—crucial for Fed-speak NdTopic ModelingOptional: BERTopic for discoveryOnly for exploratory analysis, not core pipelineDatabaseSupabase (PostgreSQL + pgvector)Your spec; good choiceUIStreamlitYour spec; appropriate for MVP

What You Should Build First
MVP (2-3 weeks):

Manual speech ingestion (paste URL → scrape → clean)
Semantic fingerprint extraction via Claude API
Pairwise comparison between two selected speeches
Basic shift detection and categorization
Simple Streamlit UI showing interpreted shifts

Then iterate to add:

Automated scraping pipeline
N-speech historical tracking
Orphaned concept detection
Real-time alerting