# Pipeline Manager — Phase Data Visualization Plan

## Executive Summary

The Pipeline Manager needs a comprehensive data visualization system that displays **all collected data** at each phase—both during execution (real-time) and after completion (historical review). This plan details the exact data to show, UI components to build, and API enhancements required.

---

## Core Requirements

### Must Support Two Viewing Modes

1. **Live Mode (Run in Progress)**
   - Real-time data streaming via SSE
   - Show completed phases with full data
   - Show current phase with live progress + incoming data
   - Pending phases show "Waiting..." state

2. **Review Mode (Run Completed)**
   - All phases accessible via tabs/navigation
   - Full data export capabilities
   - Story-centric "journey" view

---

## Phase Data Architecture

### What Each Phase Produces

| Phase | Primary Output | Key Metrics | Visual Elements |
|-------|---------------|-------------|-----------------|
| **1. Lead Generation** | Leads (filtered candidates) | Discovered → Filtered → Approved counts | Filter funnel diagram, score distributions |
| **2. Story Research** | Research packages | Ground truth + Hook + Sources | Expandable research cards, source links |
| **3. Text Generation** | Slides + Cover options + Captions | Slide count, character counts, option count | Slide preview cards, cover option selector |
| **4. Photo Research** | Curated images | Found → Approved → Rejected + scores | Image grid with scores, placement diagram |
| **5. Thumbnails** | AI cover images | 3 concepts per story | Thumbnail gallery with concept types |

---

## Phase 1: Lead Generation & Curation — Data Display

### Data Available in Database

From `leads` table (filtered by `pipeline_run_id`):
```sql
SELECT 
    id, title, url, summary, 
    brand_score, virality_score, interestingness_score,
    viral_hook, status, source_origin, created_at
FROM leads 
WHERE pipeline_run_id = $1
ORDER BY virality_score DESC;
```

From `story_research` for curator reasoning:
```sql
SELECT sr.notes as curator_reasoning, l.*
FROM leads l
LEFT JOIN story_research sr ON sr.lead_id = l.id
WHERE l.pipeline_run_id = $1;
```

### UI Components

#### 1.1 Discovery Funnel Visualization
A vertical funnel diagram showing the filter cascade:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  DISCOVERY FUNNEL                                                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  RSS Feeds ─────────────────────────────────────────▶ 247 articles scanned      │
│       │                                                                          │
│       ▼                                                                          │
│  Perplexity Discovery ────────────────────────────────▶ +53 new stories         │
│       │                                               ══════════════            │
│       ▼                                               300 total candidates      │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │ URL Deduplication                                                       │     │
│  │ ───────────────────────────────────────────────────────────────────    │     │
│  │ ✓ 284 unique URLs                     ✗ 16 duplicates removed          │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │ Smart Gatekeeper (Batch Filter)                                         │     │
│  │ ───────────────────────────────────────────────────────────────────    │     │
│  │ ✓ 156 passed                          ✗ 128 filtered                   │     │
│  │                                        ├─ 67 politics/current events   │     │
│  │                                        ├─ 41 celebrity/gossip          │     │
│  │                                        └─ 20 low-substance             │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │ Semantic Deduplication (75% similarity threshold)                       │     │
│  │ ───────────────────────────────────────────────────────────────────    │     │
│  │ ✓ 142 unique concepts                 ✗ 14 too similar to existing     │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │ Virality Scoring (threshold: ≥78)                                       │     │
│  │ ───────────────────────────────────────────────────────────────────    │     │
│  │ ✓ 89 high-viral                       ✗ 53 below threshold             │     │
│  │                                                                         │     │
│  │ Distribution: █▁▂▃▅▇██▇▅▃▂▁ (78-95 range)                             │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │ Brand Lens Scoring (threshold: ≥70)                                     │     │
│  │ ───────────────────────────────────────────────────────────────────    │     │
│  │ ✓ 52 on-brand                         ✗ 37 off-brand                   │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│       │                                                                          │
│       ▼                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────┐     │
│  │ AI Curator Selection                                                    │     │
│  │ ───────────────────────────────────────────────────────────────────    │     │
│  │ ✓ 12 SELECTED for this run            ✗ 40 saved for future            │     │
│  └────────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 1.2 Selected Leads Grid

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  SELECTED LEADS (12)                                              [Expand All]  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─ LEAD CARD ────────────────────────────────────────────────────────────────┐ │
│  │                                                                             │ │
│  │  The Phantom Time Hypothesis                                                │ │
│  │  ──────────────────────────────────────────────────────────────────────── │ │
│  │                                                                             │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │  📰 atlasobscura.com  │  HISTORY  │  RSS Feed                       │   │ │
│  │  └─────────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                             │ │
│  │  ┌──────────────────┬──────────────────┬──────────────────┐               │ │
│  │  │  Viral: 91 ████  │  Brand: 85 ████  │  Interest: 88    │               │ │
│  │  └──────────────────┴──────────────────┴──────────────────┘               │ │
│  │                                                                             │ │
│  │  Summary:                                                                   │ │
│  │  "German historian Heribert Illig claims nearly 300 years of medieval      │ │
│  │   history were fabricated, including the entire reign of Charlemagne..."  │ │
│  │                                                                             │ │
│  │  Viral Hook:                                                                │ │
│  │  "What if 300 years of history never actually happened?"                   │ │
│  │                                                                             │ │
│  │  ┌─ CURATOR REASONING ─────────────────────────────────────────────────┐   │ │
│  │  │  "Perfect TheBoldUnknown material — challenges historical consensus  │   │ │
│  │  │   with documented evidence. High shareability due to 'wait, what?'   │   │ │
│  │  │   factor. Not conspiracy — legitimate academic debate."              │   │ │
│  │  └─────────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                             │ │
│  │                                                [View Source ↗] [Expand ▼]  │ │
│  │                                                                             │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  [Lead Card 2...]                                                               │
│  [Lead Card 3...]                                                               │
│  ...                                                                            │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 1.3 Score Distribution Charts

Small inline histograms showing score distributions:
- Virality score distribution (0-100)
- Brand score distribution (0-100)
- Source origin breakdown (pie chart: RSS vs Perplexity)

### API Enhancement for Phase 1

Enhance `/api/pipeline/runs/{run_id}/phases/1/leads` to return:

```json
{
  "phase": "lead_generation",
  "status": "completed",
  "started_at": "2024-12-21T14:15:00Z",
  "completed_at": "2024-12-21T14:18:23Z",
  "duration_seconds": 203,
  
  "funnel": {
    "rss_scanned": 247,
    "perplexity_discovered": 53,
    "total_candidates": 300,
    "url_deduped": 284,
    "url_dupes_removed": 16,
    "gatekeeper_passed": 156,
    "gatekeeper_filtered": {
      "politics": 67,
      "celebrity": 41,
      "low_quality": 20
    },
    "semantic_unique": 142,
    "semantic_dupes": 14,
    "viral_passed": 89,
    "viral_failed": 53,
    "brand_passed": 52,
    "brand_failed": 37,
    "curator_selected": 12,
    "curator_saved": 40
  },
  
  "score_distributions": {
    "virality": { "min": 42, "max": 95, "mean": 76, "histogram": [...] },
    "brand": { "min": 35, "max": 92, "mean": 71, "histogram": [...] }
  },
  
  "source_breakdown": {
    "rss": 7,
    "perplexity": 5
  },
  
  "leads": [
    {
      "id": "uuid",
      "title": "The Phantom Time Hypothesis",
      "url": "https://atlasobscura.com/...",
      "summary": "German historian Heribert Illig claims...",
      "source_origin": "RSS: atlasobscura",
      "virality_score": 91,
      "brand_score": 85,
      "interestingness_score": 88,
      "viral_hook": "What if 300 years of history never actually happened?",
      "status": "approved",
      "curator_reasoning": "Perfect TheBoldUnknown material...",
      "domain_tag": "HISTORY"
    }
    // ... more leads
  ]
}
```

---

## Phase 2: Story Research — Data Display

### Data Available in Database

```sql
SELECT 
    sr.id, sr.status, sr.started_at, sr.completed_at,
    sr.research_data,        -- JSONB with ground_truth, follow_up
    sr.primary_sources,      -- TEXT[] array
    sr.primary_source_urls,  -- TEXT[] array
    sr.notes as curator_notes,
    l.title, l.url, l.summary
FROM story_research sr
JOIN leads l ON sr.lead_id = l.id
WHERE sr.pipeline_run_id = $1
ORDER BY sr.created_at;
```

### UI Components

#### 2.1 Research Progress Grid

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  STORY RESEARCH                                    5/12 complete • 1 in progress │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─── STORY RESEARCH CARD ──────────────────────────────────────────────────┐   │
│  │                                                                           │   │
│  │  ✓ The Phantom Time Hypothesis                              [COMPLETED]  │   │
│  │  ────────────────────────────────────────────────────────────────────── │   │
│  │                                                                           │   │
│  │  ┌─ GROUND TRUTH ──────────────────────────────────────────────────────┐ │   │
│  │  │                                                                      │ │   │
│  │  │  The Phantom Time Hypothesis was proposed by Heribert Illig in      │ │   │
│  │  │  1991. It suggests that 297 years (AD 614–911) were fabricated by   │ │   │
│  │  │  Holy Roman Emperor Otto III, Pope Sylvester II, and Byzantine      │ │   │
│  │  │  Emperor Constantine VII to place themselves at the millennial      │ │   │
│  │  │  year AD 1000.                                                       │ │   │
│  │  │                                                                      │ │   │
│  │  │  Key claims:                                                         │ │   │
│  │  │  • Charlemagne never existed or was a different person              │ │   │
│  │  │  • Architectural inconsistencies in Carolingian structures          │ │   │
│  │  │  • Gaps in archaeological record for this period                    │ │   │
│  │  │  • Calendar reform by Pope Gregory XIII introduced errors           │ │   │
│  │  │                                                                      │ │   │
│  │  │  Counter-evidence:                                                   │ │   │
│  │  │  • Islamic and Byzantine records align with standard timeline       │ │   │
│  │  │  • Dendrochronology confirms dates                                  │ │   │
│  │  │  • Solar eclipse records match astronomical calculations            │ │   │
│  │  │                                                                      │ │   │
│  │  │                                      [Show Full ▼] (2,341 characters) │ │   │
│  │  └──────────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                           │   │
│  │  ┌─ THE HOOK ──────────────────────────────────────────────────────────┐ │   │
│  │  │                                                                      │ │   │
│  │  │  "What if nearly 300 years of history never happened?"              │ │   │
│  │  │                                                                      │ │   │
│  │  │  Angle: A respected German historian found mathematical and         │ │   │
│  │  │  architectural evidence suggesting the Early Middle Ages were       │ │   │
│  │  │  invented. Charlemagne might be fiction.                            │ │   │
│  │  │                                                                      │ │   │
│  │  └──────────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                           │   │
│  │  ┌─ PRIMARY SOURCES ───────────────────────────────────────────────────┐ │   │
│  │  │                                                                      │ │   │
│  │  │  📚 Illig, H. "Das erfundene Mittelalter" (1996)         [Link ↗]   │ │   │
│  │  │  📚 Niemitz, H. "Did the Early Middle Ages Exist?" (1995) [Link ↗]  │ │   │
│  │  │  📚 Journal of Interdisciplinary History, Vol. 31, No. 2  [Link ↗]  │ │   │
│  │  │                                                                      │ │   │
│  │  └──────────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                           │   │
│  │  Research time: 2m 34s                                                    │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  ┌─── STORY RESEARCH CARD (IN PROGRESS) ────────────────────────────────────┐   │
│  │                                                                           │   │
│  │  ◐ The Great Emu War of 1932                               [IN PROGRESS] │   │
│  │  ────────────────────────────────────────────────────────────────────── │   │
│  │                                                                           │   │
│  │  ████████████████░░░░░░░░░░░░  Step 2/3: Hook Identification             │   │
│  │                                                                           │   │
│  │  ✓ Ground Truth gathered (1,847 chars)                                   │   │
│  │  ◐ Identifying hook angle...                                              │   │
│  │  ○ Primary sources pending                                                │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  ┌─── STORY RESEARCH CARD (QUEUED) ─────────────────────────────────────────┐   │
│  │                                                                           │   │
│  │  ○ The Taos Hum Mystery                                          [QUEUED] │   │
│  │  ────────────────────────────────────────────────────────────────────── │   │
│  │  Waiting in queue... (position 1)                                         │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### API Enhancement for Phase 2

Enhance `/api/pipeline/runs/{run_id}/phases/2/research`:

```json
{
  "phase": "story_research",
  "status": "running",
  "started_at": "2024-12-21T14:18:30Z",
  "completed_at": null,
  "duration_seconds": 720,
  
  "summary": {
    "total": 12,
    "completed": 5,
    "in_progress": 1,
    "queued": 6,
    "failed": 0
  },
  
  "average_research_time_seconds": 144,
  "total_ground_truth_chars": 12450,
  
  "research": [
    {
      "id": "uuid",
      "lead_id": "uuid",
      "title": "The Phantom Time Hypothesis",
      "url": "https://...",
      "status": "completed",
      "started_at": "2024-12-21T14:18:30Z",
      "completed_at": "2024-12-21T14:21:04Z",
      
      "ground_truth": "The Phantom Time Hypothesis was proposed...",
      "ground_truth_char_count": 2341,
      
      "hook": {
        "question": "What if nearly 300 years of history never happened?",
        "angle": "A respected German historian found mathematical and architectural evidence..."
      },
      
      "primary_sources": [
        "Illig, H. \"Das erfundene Mittelalter\" (1996)",
        "Niemitz, H. \"Did the Early Middle Ages Really Exist?\" (1995)"
      ],
      "primary_source_urls": [
        "https://...",
        "https://..."
      ],
      
      "research_time_seconds": 154
    }
    // ... more research items
  ]
}
```

---

## Phase 3: Text Generation — Data Display

### Data Available in Database

```sql
-- Story generations
SELECT 
    sg.id, sg.hook_title, sg.subtitle, sg.domain_tag,
    sg.instagram_caption, sg.hashtags,
    sg.generation_metadata,  -- Contains cover options
    sg.created_at,
    sr.id as research_id, l.title as lead_title
FROM story_generations sg
JOIN story_research sr ON sg.story_research_id = sr.id
JOIN leads l ON sr.lead_id = l.id
WHERE sg.pipeline_run_id = $1;

-- Slides for each generation
SELECT 
    ss.slide_order, ss.text_content, ss.document_type_tag, ss.paragraph_count
FROM story_slides ss
WHERE ss.story_generation_id = $1
ORDER BY ss.slide_order;
```

### UI Components

#### 3.1 Text Generation Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  TEXT GENERATION                                   8/12 complete • 1 in progress │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Summary Statistics:                                                             │
│  ┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐  │
│  │  Total Slides    │  Total Chars     │  Avg per Story   │  Cover Options   │  │
│  │  72 slides       │  18,450 chars    │  9 slides        │  48 (6 × 8)      │  │
│  └──────────────────┴──────────────────┴──────────────────┴──────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 3.2 Story Generation Card (Completed)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ✓ The Phantom Time Hypothesis                                      [COMPLETED] │
│  ──────────────────────────────────────────────────────────────────────────────│
│                                                                                  │
│  ┌─ COVER OPTIONS (6) ─────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  ● SELECTED                                                                  ││
│  │  ┌────────────────────────────────────────────────────────────────────────┐ ││
│  │  │                                                                        │ ││
│  │  │  "Nearly 300 Years of History                                          │ ││
│  │  │   May Have Never Happened"                                             │ ││
│  │  │   ─────────────────────────────────────────────────────────────────   │ ││
│  │  │   One German historian found evidence that Charlemagne might be        │ ││
│  │  │   completely fictional.                                                │ ││
│  │  │   ─────────────────────────────────────────────────────────────────   │ ││
│  │  │   │ HISTORY │                                                          │ ││
│  │  │                                                                        │ ││
│  │  └────────────────────────────────────────────────────────────────────────┘ ││
│  │                                                                              ││
│  │  ○ Option 2: "Did the Medieval Period Actually Exist?"                       ││
│  │  ○ Option 3: "The 297 Years That Never Were"                                 ││
│  │  ○ Option 4: "Charlemagne: Emperor or Invention?"                            ││
│  │  ○ Option 5: "History's Greatest Cover-Up?"                                  ││
│  │  ○ Option 6: "The Fabricated Middle Ages"                                    ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─ SLIDES (9) ────────────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  # │ Tag       │ ¶ │ Preview                                                 ││
│  │  ──┼───────────┼───┼─────────────────────────────────────────────────────── ││
│  │  1 │ HOOK      │ 1 │ In 1991, a German historian made a claim that would... ││
│  │  2 │ CONTEXT   │ 2 │ Heribert Illig proposed that 297 years of history...   ││
│  │  3 │ EVIDENCE  │ 2 │ His evidence includes architectural anomalies in...     ││
│  │  4 │ DEEP_DIVE │ 2 │ The Carolingian Renaissance supposedly flourished...   ││
│  │  5 │ TWIST     │ 1 │ But here's where it gets strange. The very pope who... ││
│  │  6 │ COUNTER   │ 2 │ Mainstream historians point to Islamic and Byzantine...││
│  │  7 │ RESOLUTION│ 2 │ While the hypothesis remains fringe, it raises...      ││
│  │  8 │ IMPLICATION│1 │ If true, it would mean every medieval textbook is...   ││
│  │  9 │ CLOSER    │ 1 │ Sometimes the strangest theories reveal the most...    ││
│  │                                                                              ││
│  │  Total: 2,341 characters                          [Preview Full Slides ▼]    ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─ CAPTION & HASHTAGS ────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  Caption (312 chars):                                                        ││
│  │  ┌────────────────────────────────────────────────────────────────────────┐ ││
│  │  │ What if nearly 300 years of history were completely made up?           │ ││
│  │  │ One German historian thinks the Early Middle Ages never happened. 🧵⬇️  │ ││
│  │  └────────────────────────────────────────────────────────────────────────┘ ││
│  │                                                                              ││
│  │  Hashtags (15):                                                              ││
│  │  ┌────────────────────────────────────────────────────────────────────────┐ ││
│  │  │ #history  #medieval  #conspiracy  #strangebutrue  #didyouknow          │ ││
│  │  │ #charlemagne  #middleages  #phantomtime  #historymystery               │ ││
│  │  │ #fascinating  #unbelievable  #mindblown  #theboldunknown               │ ││
│  │  │ #curiosity  #learnontiktok                                             │ ││
│  │  └────────────────────────────────────────────────────────────────────────┘ ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 3.3 Slide Preview Modal

When "Preview Full Slides" is clicked, show a modal with each slide's full content:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Slide Preview — The Phantom Time Hypothesis                               [×]  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ← Slide 3 of 9 →                                                               │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  EVIDENCE                                                                    ││
│  │  ──────────────────────────────────────────────────────────────────────────││
│  │                                                                              ││
│  │  His evidence includes architectural anomalies in Carolingian structures—   ││
│  │  buildings that supposedly date to the 9th century but show construction    ││
│  │  techniques not developed until the 12th century.                           ││
│  │                                                                              ││
│  │  Even more puzzling: the archaeological record for this period contains     ││
│  │  suspicious gaps and inconsistencies that mainstream historians have        ││
│  │  struggled to explain.                                                      ││
│  │                                                                              ││
│  │  ──────────────────────────────────────────────────────────────────────────││
│  │  Paragraphs: 2  •  Characters: 389                                          ││
│  │                                                                              ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  [← Previous]                                                    [Next →]       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### API Enhancement for Phase 3

Enhance `/api/pipeline/runs/{run_id}/phases/3/text`:

```json
{
  "phase": "text_generation",
  "status": "completed",
  "started_at": "2024-12-21T14:30:00Z",
  "completed_at": "2024-12-21T14:45:00Z",
  
  "summary": {
    "total": 12,
    "completed": 12,
    "total_slides": 108,
    "total_characters": 24560,
    "average_slides_per_story": 9,
    "average_chars_per_story": 2047
  },
  
  "generations": [
    {
      "id": "uuid",
      "story_research_id": "uuid",
      "lead_title": "The Phantom Time Hypothesis",
      "status": "completed",
      
      "cover": {
        "selected_option": 1,
        "options": [
          {
            "option_id": 1,
            "hook_title": "Nearly 300 Years of History May Have Never Happened",
            "subtitle": "One German historian found evidence that Charlemagne might be completely fictional.",
            "domain_tag": "HISTORY"
          },
          // ... 5 more options
        ]
      },
      
      "slides": [
        {
          "order": 1,
          "tag": "HOOK",
          "paragraph_count": 1,
          "text": "In 1991, a German historian made a claim that would shake the foundations of medieval history...",
          "char_count": 120
        }
        // ... more slides
      ],
      
      "total_slides": 9,
      "total_characters": 2341,
      
      "caption": "What if nearly 300 years of history were completely made up?...",
      "caption_char_count": 312,
      
      "hashtags": ["#history", "#medieval", "..."]
    }
    // ... more generations
  ]
}
```

---

## Phase 4: Photo Research — Data Display

### Data Available in Database

```sql
SELECT 
    sp.id, sp.image_url, sp.source_page_url, sp.search_query,
    sp.description, sp.caption, sp.source_attribution, sp.concept_tag,
    sp.relevance_score, sp.verifiability_score, sp.status,
    sp.metadata,  -- JSONB with usability_score, is_ai_generated, placement, etc.
    sp.created_at,
    l.title as story_title, sr.id as story_research_id
FROM story_photos sp
JOIN story_research sr ON sp.story_research_id = sr.id
JOIN leads l ON sr.lead_id = l.id
WHERE sp.pipeline_run_id = $1
ORDER BY sp.created_at;
```

### UI Components

#### 4.1 Photo Research Summary

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PHOTO RESEARCH                                    6/12 stories • 47 photos found│
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Summary Statistics:                                                             │
│  ┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐  │
│  │  Photos Found    │  Approved        │  Rejected        │  AI Detected     │  │
│  │  47 total        │  32 (68%)        │  15 (32%)        │  3               │  │
│  └──────────────────┴──────────────────┴──────────────────┴──────────────────┘  │
│                                                                                  │
│  Rejection Reasons:                                                              │
│  • Low relevance (< 7): 8                                                        │
│  • AI-generated detected: 3                                                      │
│  • Low usability (watermarks, resolution): 4                                     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 4.2 Story Photo Card

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ✓ The Phantom Time Hypothesis                        4 approved • 3 rejected   │
│  ──────────────────────────────────────────────────────────────────────────────│
│                                                                                  │
│  ┌─ SEARCH QUERIES USED ───────────────────────────────────────────────────────┐│
│  │  • "Heribert Illig phantom time historian photo"                             ││
│  │  • "Charlemagne medieval illustration manuscript"                            ││
│  │  • "Aachen Cathedral Carolingian architecture"                               ││
│  │  • "medieval manuscript forgery evidence"                                    ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─ APPROVED PHOTOS ───────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    ││
│  │  │  ██████████  │  │  ██████████  │  │  ██████████  │  │  ██████████  │    ││
│  │  │  ██████████  │  │  ██████████  │  │  ██████████  │  │  ██████████  │    ││
│  │  │  ██████████  │  │  ██████████  │  │  ██████████  │  │  ██████████  │    ││
│  │  │  ██████████  │  │  ██████████  │  │  ██████████  │  │  ██████████  │    ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    ││
│  │     ★ HERO            Photo 2          Photo 3          Photo 4            ││
│  │    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      ││
│  │    │ Rel: 9/10   │  │ Rel: 9/10   │  │ Rel: 8/10   │  │ Rel: 7/10   │      ││
│  │    │ Ver: 9/10   │  │ Ver: 8/10   │  │ Ver: 9/10   │  │ Ver: 7/10   │      ││
│  │    │ Use: 9/10   │  │ Use: 8/10   │  │ Use: 7/10   │  │ Use: 8/10   │      ││
│  │    └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      ││
│  │                                                                              ││
│  │  Click any photo for details...                                              ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─ REJECTED PHOTOS ───────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       ││
│  │  │  ░░░░░░░░░░  │  │  ░░░░░░░░░░  │  │  ░░░░░░░░░░  │   Rejection Reasons: ││
│  │  │  ░░░░░░░░░░  │  │  ░░░░░░░░░░  │  │  ░░░░░░░░░░  │   • Low relevance: 2  ││
│  │  │  ░░░░░░░░░░  │  │  ░░░░░░░░░░  │  │  ░░░░░░░░░░  │   • AI-generated: 1   ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘                       ││
│  │     ✗ Rel: 2/10     ✗ Rel: 1/10      ✗ AI detected                          ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─ PLACEMENT DIAGRAM ─────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  Cover → Slide 1 → Slide 2 → [PHOTO 1★] → Slide 3 → Slide 4 →              ││
│  │        → [photo 2] → Slide 5 → Slide 6 → [photo 3] → Slide 7 →              ││
│  │        → Slide 8 → [photo 4] → Slide 9 → Close                              ││
│  │                                                                              ││
│  │  ★ = Hero photo (enabled)  •  [photo] = placed but disabled (optional)      ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 4.3 Photo Detail Modal

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Photo Analysis                                                            [×]  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────┐  ┌──────────────────────────────────────┐ │
│  │                                 │  │  SCORES                              │ │
│  │     ████████████████████████    │  │  ────────────────────────────────── │ │
│  │     ████████████████████████    │  │                                      │ │
│  │     ████████████████████████    │  │  Relevance      ████████░░  9/10    │ │
│  │     ████████████████████████    │  │  Verifiability  ████████░░  8/10    │ │
│  │     ████████████████████████    │  │  Usability      █████████░  9/10    │ │
│  │     ████████████████████████    │  │                                      │ │
│  │     ████████████████████████    │  │  AI Detection   ✓ Not AI-generated  │ │
│  │                                 │  │                                      │ │
│  └─────────────────────────────────┘  │  Status: ✓ APPROVED                 │ │
│                                        │                                      │ │
│                                        └──────────────────────────────────────┘ │
│                                                                                  │
│  ┌─ SOURCE INFORMATION ────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  Source URL:  atlasobscura.com/articles/phantom-time-hypothesis             ││
│  │  Page Title:  "The Phantom Time Hypothesis: Did the Middle Ages Happen?"    ││
│  │  Image Context: "Portrait of Heribert Illig at a 2003 conference"           ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─ AI ANALYSIS ───────────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  Description:                                                                ││
│  │  "Photograph of a middle-aged man with grey hair at a podium, appearing     ││
│  │   to be giving a lecture. Academic setting visible in background.           ││
│  │   Professional quality photograph."                                         ││
│  │                                                                              ││
│  │  Relevance Reasoning:                                                        ││
│  │  "Image shows Heribert Illig, the originator of the Phantom Time            ││
│  │   Hypothesis. Directly relevant to story subject matter."                   ││
│  │                                                                              ││
│  │  Generated Caption:                                                          ││
│  │  "Heribert Illig presenting his theory at a 2003 academic conference.       ││
│  │   The German historian's work has sparked decades of debate."               ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  Search Query: "Heribert Illig phantom time historian photo"                    │
│  Concept Tag: PERSON                                                            │
│  Placement: After Slide 2 (ENABLED as Hero)                                     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### API Enhancement for Phase 4

```json
{
  "phase": "photo_research",
  "status": "completed",
  
  "summary": {
    "stories_processed": 12,
    "total_photos_found": 47,
    "approved": 32,
    "rejected": 15,
    "ai_detected": 3,
    "rejection_reasons": {
      "low_relevance": 8,
      "ai_generated": 3,
      "low_usability": 4
    }
  },
  
  "score_averages": {
    "relevance": 7.8,
    "verifiability": 7.2,
    "usability": 7.5
  },
  
  "photos_by_story": [
    {
      "story_research_id": "uuid",
      "story_title": "The Phantom Time Hypothesis",
      "queries_used": [
        "Heribert Illig phantom time historian photo",
        "Charlemagne medieval illustration manuscript"
      ],
      
      "photos": [
        {
          "id": "uuid",
          "image_url": "https://...",
          "thumbnail_url": "https://...",  // For grid display
          "status": "approved",
          
          "scores": {
            "relevance": 9,
            "verifiability": 9,
            "usability": 9
          },
          
          "is_ai_generated": false,
          "is_hero": true,
          "placement": { "after_slide": 2, "enabled": true },
          
          "source": {
            "page_url": "https://atlasobscura.com/...",
            "page_title": "The Phantom Time Hypothesis...",
            "image_context": "Portrait of Heribert Illig..."
          },
          
          "ai_analysis": {
            "description": "Photograph of a middle-aged man...",
            "relevance_reasoning": "Image shows Heribert Illig...",
            "generated_caption": "Heribert Illig presenting..."
          },
          
          "search_query": "Heribert Illig phantom time historian photo",
          "concept_tag": "PERSON"
        }
        // ... more photos
      ],
      
      "approved_count": 4,
      "rejected_count": 3
    }
    // ... more stories
  ]
}
```

---

## Phase 5: Thumbnail Generation — Data Display

### Data Available in Database

```sql
SELECT 
    st.id, st.concept_number, st.concept_type,
    st.scene_description, st.full_prompt, st.image_url,
    st.status, st.is_selected, st.generation_metadata,
    st.generated_at,
    sg.hook_title, sg.subtitle, sg.domain_tag
FROM story_thumbnails st
JOIN story_generations sg ON st.story_generation_id = sg.id
WHERE st.pipeline_run_id = $1
ORDER BY st.created_at;
```

### UI Components

#### 5.1 Thumbnail Generation Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  THUMBNAIL GENERATION                             10/12 stories • 30 generated  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Summary: 10 ✓ complete • 1 ◐ in progress • 1 ○ queued                          │
│  Total Thumbnails: 30 generated (3 per story) • 0 failed                        │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 5.2 Story Thumbnail Card

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ✓ The Phantom Time Hypothesis                                      [COMPLETED] │
│  ──────────────────────────────────────────────────────────────────────────────│
│                                                                                  │
│  ┌─ GENERATED CONCEPTS (3) ────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  ││
│  │  │                     │  │                     │  │                     │  ││
│  │  │   ██████████████    │  │   ██████████████    │  │   ██████████████    │  ││
│  │  │   ██████████████    │  │   ██████████████    │  │   ██████████████    │  ││
│  │  │   ██████████████    │  │   ██████████████    │  │   ██████████████    │  ││
│  │  │   ██████████████    │  │   ██████████████    │  │   ██████████████    │  ││
│  │  │   ██████████████    │  │   ██████████████    │  │   ██████████████    │  ││
│  │  │   ██████████████    │  │   ██████████████    │  │   ██████████████    │  ││
│  │  │                     │  │                     │  │                     │  ││
│  │  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  ││
│  │       LITERAL ●                SYMBOLIC                 ATMOSPHERIC          ││
│  │      (Selected)                                                              ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─ CONCEPT DETAILS ───────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  ● Concept 1: LITERAL (Selected)                                             ││
│  │  ┌────────────────────────────────────────────────────────────────────────┐ ││
│  │  │ "Ancient manuscript pages scattered across a stone table in a dimly   │ ││
│  │  │  lit medieval scriptorium, with a quill and inkwell. Dramatic         │ ││
│  │  │  lighting from a single candle casts long shadows. Some pages appear  │ ││
│  │  │  to be fading or erasing themselves, suggesting impermanence of       │ ││
│  │  │  historical record."                                                  │ ││
│  │  └────────────────────────────────────────────────────────────────────────┘ ││
│  │                                                                              ││
│  │  ○ Concept 2: SYMBOLIC                                                       ││
│  │  "A grand hourglass with 297 years worth of sand frozen mid-fall..."        ││
│  │                                                                              ││
│  │  ○ Concept 3: ATMOSPHERIC                                                    ││
│  │  "An empty throne room in a Carolingian palace, dust motes floating..."     ││
│  │                                                                              ││
│  │                                                              [View Full ▼]   ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  Generated in 23 seconds using gemini-2.5-flash-image                           │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 5.3 Thumbnail In Progress Card

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ◐ The Great Emu War of 1932                                       [IN PROGRESS]│
│  ──────────────────────────────────────────────────────────────────────────────│
│                                                                                  │
│  ████████████████████████████░░░░░░░░░░  Step 3/3: Image Generation             │
│                                                                                  │
│  ✓ Concepts generated (3 concepts)                                              │
│  ✓ Prompts built                                                                │
│  ◐ Generating images... (2/3 complete)                                          │
│                                                                                  │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐      │
│  │                     │  │                     │  │   ░░░░░░░░░░░░░    │      │
│  │   ██████████████    │  │   ██████████████    │  │   ░░░░░░░░░░░░░    │      │
│  │   ██████████████    │  │   ██████████████    │  │   ░░ ⏳ Gen... ░░   │      │
│  │   ██████████████    │  │   ██████████████    │  │   ░░░░░░░░░░░░░    │      │
│  │                     │  │                     │  │   ░░░░░░░░░░░░░    │      │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘      │
│       ✓ Done                  ✓ Done                  ◐ Generating              │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### API Enhancement for Phase 5

```json
{
  "phase": "thumbnail_generation",
  "status": "completed",
  
  "summary": {
    "stories_processed": 12,
    "total_thumbnails": 36,
    "generated": 36,
    "failed": 0,
    "selected": 12,
    "average_generation_time_seconds": 18
  },
  
  "concept_type_breakdown": {
    "literal": 12,
    "symbolic": 12,
    "atmospheric": 12
  },
  
  "thumbnails_by_story": [
    {
      "story_generation_id": "uuid",
      "hook_title": "Nearly 300 Years of History May Have Never Happened",
      "subtitle": "One German historian found evidence...",
      "domain_tag": "HISTORY",
      
      "thumbnails": [
        {
          "id": "uuid",
          "concept_number": 1,
          "concept_type": "literal",
          "is_selected": true,
          "status": "generated",
          
          "scene_description": "Ancient manuscript pages scattered across a stone table...",
          "full_prompt": "Create a cinematic 4:5 image...",
          
          "image_url": "https://...",
          "thumbnail_url": "https://...",
          
          "generation_metadata": {
            "model": "gemini-2.5-flash-image",
            "generation_time_seconds": 18,
            "generated_at": "2024-12-21T15:10:00Z"
          }
        },
        // ... concepts 2 and 3
      ]
    }
    // ... more stories
  ]
}
```

---

## UI Architecture

### Main Pipeline View Layout

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  HEADER: Run Status + Mode + Controls                                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─ PHASE NAVIGATION BAR ──────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          ││
│  │  │1. Leads  │ │2. Research│ │3. Text   │ │4. Photos │ │5. Thumbs │          ││
│  │  │  ✓ 12    │ │  ◐ 5/12  │ │  ○ —     │ │  ○ —     │ │  ○ —     │          ││
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘          ││
│  │       ▲                                                                      ││
│  │   [Selected]                                                                 ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ══════════════════════════════════════════════════════════════════════════════ │
│                                                                                  │
│  ┌─ PHASE CONTENT AREA ────────────────────────────────────────────────────────┐│
│  │                                                                              ││
│  │  [Dynamic content based on selected phase]                                   ││
│  │                                                                              ││
│  │  - Phase 1: Discovery funnel + Lead cards                                   ││
│  │  - Phase 2: Research cards (ground truth, hook, sources)                    ││
│  │  - Phase 3: Text generation cards (slides, cover options, captions)         ││
│  │  - Phase 4: Photo grid + placement diagrams                                 ││
│  │  - Phase 5: Thumbnail gallery with concepts                                 ││
│  │                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Component Hierarchy

```
PipelineView
├── Header
│   ├── BackButton
│   ├── RunInfo (ID, Mode badge)
│   ├── StatusBadge
│   └── ActionButtons (Pause/Resume/Cancel)
│
├── PhaseNavigationBar
│   └── PhaseTab[] (clickable, shows status + count)
│
├── PhaseContentArea
│   ├── PhaseHeader (title, description, progress bar)
│   │
│   ├── Phase1Content (Lead Generation)
│   │   ├── DiscoveryFunnel
│   │   ├── ScoreDistributionCharts
│   │   └── LeadCardGrid
│   │       └── LeadCard[]
│   │
│   ├── Phase2Content (Story Research)
│   │   └── ResearchCardGrid
│   │       └── ResearchCard[]
│   │           ├── GroundTruthBlock
│   │           ├── HookBlock
│   │           └── SourcesList
│   │
│   ├── Phase3Content (Text Generation)
│   │   └── GenerationCardGrid
│   │       └── GenerationCard[]
│   │           ├── CoverOptionsSelector
│   │           ├── SlidesTable
│   │           └── CaptionHashtagsBlock
│   │
│   ├── Phase4Content (Photo Research)
│   │   └── PhotoStoryGrid
│   │       └── PhotoStoryCard[]
│   │           ├── SearchQueriesList
│   │           ├── PhotoThumbnailGrid
│   │           └── PlacementDiagram
│   │
│   └── Phase5Content (Thumbnails)
│       └── ThumbnailStoryGrid
│           └── ThumbnailStoryCard[]
│               ├── ConceptGallery
│               └── ConceptDetailsList
│
└── Modals
    ├── LeadDetailModal
    ├── SlidePreviewModal
    ├── PhotoDetailModal
    └── ThumbnailDetailModal
```

---

## SSE Event Enhancements

### Current Events (Keep)
- `state` - Full run state on connect
- `heartbeat` - Keep-alive
- `done` - Pipeline finished

### New Events to Add

```javascript
// Phase started
{
  "event": "phase_started",
  "phase": "lead_generation",
  "timestamp": "2024-12-21T14:15:00Z"
}

// Phase progress (frequent during phase)
{
  "event": "phase_progress",
  "phase": "lead_generation",
  "step": "smart_gatekeeper",  // sub-step within phase
  "progress": 45,              // percentage
  "message": "Filtering 20/45 batches...",
  "stats": {
    "processed": 100,
    "passed": 62,
    "filtered": 38
  }
}

// Funnel update (Phase 1 specific)
{
  "event": "funnel_update",
  "phase": "lead_generation",
  "funnel": {
    "rss_scanned": 247,
    "perplexity_discovered": 53,
    "gatekeeper_passed": 156
    // ... partial funnel as it builds
  }
}

// Story processing started
{
  "event": "story_started",
  "phase": "story_research",
  "story_id": "uuid",
  "title": "The Phantom Time Hypothesis"
}

// Story processing complete with data
{
  "event": "story_complete",
  "phase": "story_research",
  "story_id": "uuid",
  "data": {
    // Full research result for this story
  }
}

// Photo found
{
  "event": "photo_found",
  "phase": "photo_research",
  "story_id": "uuid",
  "photo": {
    "id": "uuid",
    "thumbnail_url": "...",
    "status": "approved",
    "relevance_score": 9
  }
}

// Thumbnail generated
{
  "event": "thumbnail_generated",
  "phase": "thumbnail_generation",
  "story_id": "uuid",
  "thumbnail": {
    "id": "uuid",
    "concept_number": 1,
    "concept_type": "literal",
    "image_url": "..."
  }
}

// Phase completed with full data
{
  "event": "phase_complete",
  "phase": "lead_generation",
  "duration_seconds": 203,
  "summary": { ... },
  "data": { ... }  // Full phase data
}
```

---

## Database Query Additions

### Phase 1 Funnel Stats Query

```sql
-- Get funnel statistics for lead generation phase
-- This would require storing funnel data in pipeline_runs.stats or a separate table

-- Alternative: Track in pipeline_runs.phases[0].funnel_data JSONB
UPDATE pipeline_runs 
SET phases = jsonb_set(
    phases,
    '{0,funnel_data}',
    $funnel_json
)
WHERE id = $run_id;
```

### Enhanced Leads Query with All Scores

```sql
SELECT 
    l.id, l.title, l.url, l.summary,
    l.brand_score, l.virality_score, l.interestingness_score,
    l.viral_hook, l.status, l.source_origin,
    l.substance_analysis,
    sr.notes as curator_reasoning,
    -- Infer domain tag from research or generation
    COALESCE(sg.domain_tag, 'UNKNOWN') as domain_tag
FROM leads l
LEFT JOIN story_research sr ON sr.lead_id = l.id
LEFT JOIN story_generations sg ON sg.story_research_id = sr.id
WHERE l.pipeline_run_id = $1
ORDER BY l.virality_score DESC NULLS LAST;
```

### Slides with Full Content

```sql
SELECT 
    ss.id, ss.slide_order, ss.text_content, 
    ss.document_type_tag, ss.paragraph_count,
    LENGTH(ss.text_content) as char_count
FROM story_slides ss
WHERE ss.story_generation_id = $1
ORDER BY ss.slide_order;
```

### Photo Stats Aggregation

```sql
SELECT 
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE status = 'approved') as approved,
    COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
    COUNT(*) FILTER (WHERE metadata->>'is_ai_generated' = 'true') as ai_detected,
    AVG(relevance_score) as avg_relevance,
    AVG(verifiability_score) as avg_verifiability,
    AVG((metadata->>'usability_score')::int) as avg_usability
FROM story_photos
WHERE pipeline_run_id = $1;
```

---

## Implementation Plan

### Phase A: API Enhancements (3-4 hours)

1. **Enhance existing phase endpoints** to return richer data:
   - `/phases/1/leads` - Add funnel stats, score distributions
   - `/phases/2/research` - Add full research_data parsing
   - `/phases/3/text` - Add slides, cover options, captions
   - `/phases/4/photos` - Add grouped by story, scores, placements
   - `/phases/5/thumbnails` - Add concepts, generation metadata

2. **Add new SSE events** for real-time updates:
   - Implement `phase_progress`, `story_started`, `story_complete`
   - Add phase-specific events (funnel_update, photo_found, etc.)

3. **Create helper functions** in `db.py`:
   - `get_funnel_stats(run_id)`
   - `get_slides_for_generation(generation_id)`
   - `get_photos_grouped_by_story(run_id)`

### Phase B: UI Components (6-8 hours)

1. **Phase Navigation Bar** component with tabs showing status/counts

2. **Phase-specific content components**:
   - `Phase1Content` with funnel diagram + lead cards
   - `Phase2Content` with research cards
   - `Phase3Content` with generation cards + slide preview modal
   - `Phase4Content` with photo grid + detail modal
   - `Phase5Content` with thumbnail gallery

3. **Shared components**:
   - `ProgressBar` (animated)
   - `ScoreBadge` (for scores 0-10 and 0-100)
   - `StatusBadge` (pending/running/completed/failed)
   - `ExpandableCard` (for long content)
   - `ImageLightbox` (for photo/thumbnail previews)

### Phase C: Real-time Integration (2-3 hours)

1. **SSE handling** in frontend to process new events
2. **Optimistic UI updates** as data streams in
3. **Auto-scroll to latest** item being processed
4. **Phase auto-selection** when phase changes

### Phase D: Polish & Testing (2-3 hours)

1. **Loading states** for each phase
2. **Error handling** for failed stories
3. **Empty states** for phases not yet started
4. **Responsive design** for different screen sizes
5. **Data export** functionality (JSON/CSV)

---

## File Changes Required

### Backend (`pipeline_manager/`)

| File | Changes |
|------|---------|
| `db.py` | Add helper queries for funnel stats, slides, photo grouping |
| `main.py` | Enhance phase endpoints with richer data |
| `models.py` | Add response models for enriched phase data |
| `executor.py` | Emit new SSE events during execution |

### Frontend (`pipeline_manager/static/`)

| File | Changes |
|------|---------|
| `pipeline.html` | Complete rewrite with new component structure |
| `js/pipeline.js` | (new) Alpine.js data + SSE handling |
| `js/components/` | (new directory) Reusable UI components |

---

## Success Criteria

1. **All phase data visible** - Every piece of data collected at each phase can be viewed
2. **Real-time updates** - Data streams in live during execution
3. **Historical review** - Completed runs show full data at all phases
4. **Rich visualization** - Funnel diagrams, score charts, image grids
5. **Detailed drilldown** - Click any item for full details in modal
6. **Performance** - Smooth UI even with 50+ stories, 200+ photos

---

## Estimated Timeline

| Phase | Duration | Description |
|-------|----------|-------------|
| A | 3-4 hours | API enhancements |
| B | 6-8 hours | UI components |
| C | 2-3 hours | Real-time integration |
| D | 2-3 hours | Polish & testing |
| **Total** | **13-18 hours** | Full implementation |

---

## Future Enhancements

1. **Data Export** - Download phase data as JSON/CSV
2. **Compare Runs** - Side-by-side view of two runs
3. **Story Journey View** - Single story across all phases
4. **Analytics Dashboard** - Trends across multiple runs
5. **Filter/Search** - Find specific stories, filter by score
6. **Keyboard Navigation** - Arrow keys to browse items

