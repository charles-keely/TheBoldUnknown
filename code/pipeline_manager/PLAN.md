# Pipeline Manager — Unified Content Pipeline UI

## Overview

A unified web UI to orchestrate the entire content pipeline from lead generation through thumbnail generation, seamlessly connecting with the existing Pre-Assembler and Scheduler web apps.

The Pipeline Manager provides visibility and control over the full content journey:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Pipeline Manager Scope                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐        │
│   │  LEAD GENERATION │ ──▶ │     CURATION     │ ──▶ │  STORY RESEARCH  │        │
│   │   (Discovery)    │     │   (Selection)    │     │    (Research)    │        │
│   └──────────────────┘     └──────────────────┘     └──────────────────┘        │
│                                                              │                   │
│            ┌─────────────────────────────────────────────────┘                   │
│            │                                                                     │
│            ▼                                                                     │
│   ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐        │
│   │  TEXT GENERATOR  │ ──▶ │ PHOTO RESEARCHER │ ──▶ │THUMBNAIL GENERATOR│       │
│   │    (Writing)     │     │    (Visuals)     │     │   (Cover Art)    │        │
│   └──────────────────┘     └──────────────────┘     └──────────────────┘        │
│                                                              │                   │
└──────────────────────────────────────────────────────────────┼───────────────────┘
                                                               │
                                                               ▼
                            ┌──────────────────────────────────────────────────────┐
                            │              Existing Web Apps                        │
                            │  ┌──────────────────┐     ┌──────────────────┐       │
                            │  │  PRE-ASSEMBLER   │ ──▶ │    SCHEDULER     │       │
                            │  │    (Layout)      │     │   (Publisher)    │       │
                            │  └──────────────────┘     └──────────────────┘       │
                            └──────────────────────────────────────────────────────┘
```

---

## Two Operating Modes

### 1. Auto Mode (Full Pipeline)

Runs the entire pipeline automatically from lead generation through thumbnail generation with minimal user intervention.

**Behavior:**
- User clicks "Start Pipeline" → all phases run sequentially
- Real-time progress display for each phase
- User can monitor but doesn't need to approve each step
- Errors pause the pipeline and highlight the failing phase
- User can retry failed phases or skip and continue
- Final output: Stories ready for Pre-Assembler

**Use Case:** Weekly content batch generation, running overnight, or when confident in the pipeline quality.

### 2. Step Mode (Phase-by-Phase)

Runs each phase individually with user confirmation required between phases.

**Behavior:**
- User clicks "Start Phase" → runs current phase only
- Phase results displayed with rich preview
- User reviews results and either:
  - ✅ Approves → unlocks "Continue to Next Phase"
  - 🔄 Reruns → re-executes the current phase
  - ⏭️ Skips → marks phase as skipped, moves forward
- Clear status indicators for each story in the batch
- Final output: Stories ready for Pre-Assembler

**Use Case:** Quality control, debugging, testing new prompts, first-time setup.

---

## State Persistence & Session Recovery

The Pipeline Manager maintains full state in the database, enabling seamless recovery if the user closes the browser, navigates away, or the server restarts.

### How It Works

1. **All state is server-side**: Pipeline progress, current phase, per-story status, and errors are stored in PostgreSQL, not in browser memory or localStorage.

2. **Automatic resume on return**: When a user visits the Pipeline Manager:
   - Check for any `pipeline_runs` with status `running` or `paused`
   - If found, automatically redirect to `/pipeline/{run_id}`
   - Show a prominent "Active Run" banner on the dashboard

3. **Background execution continues**: The pipeline executor runs as an async background task. Closing the browser does NOT stop execution—it continues server-side.

4. **Reconnect via SSE**: When the user returns, the UI reconnects to the SSE stream and immediately receives the current state.

### Dashboard Behavior

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ⚡ Active Pipeline Run                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Run #48 is currently running                                            │    │
│  │  Phase: Text Generation (3/5)  •  5 of 8 stories complete               │    │
│  │                                                                          │    │
│  │                               [ Resume Viewing ]  [ Cancel Run ]         │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ─── OR start a new pipeline (will cancel the active one) ───                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### API for Session Recovery

```python
@app.get("/api/pipeline/active")
async def get_active_run():
    """
    Check for any active (running/paused) pipeline run.
    Returns the run details if one exists, or null if none.
    Used by the dashboard to auto-redirect users.
    """
    run = get_active_pipeline_run()  # status IN ('running', 'paused')
    if run:
        return {
            "has_active_run": True,
            "run": run,
            "redirect_url": f"/pipeline/{run['id']}"
        }
    return {"has_active_run": False, "run": None}
```

### Frontend Auto-Redirect

```javascript
// On dashboard load
async function checkActiveRun() {
    const resp = await fetch('/api/pipeline/active');
    const data = await resp.json();
    
    if (data.has_active_run) {
        // Show banner with option to resume or cancel
        showActiveRunBanner(data.run);
        
        // Optional: auto-redirect after brief delay
        // setTimeout(() => window.location.href = data.redirect_url, 2000);
    }
}
```

---

## Cancellation & Data Cleanup

When a pipeline run is cancelled, ALL data created during that run must be deleted to maintain database integrity and avoid orphaned/partial records.

### Cancellation Flow

1. **User clicks "Cancel Run"** → Confirmation modal appears
2. **Confirmation modal warns**: "This will delete all stories, photos, and thumbnails created in this run. This cannot be undone."
3. **User confirms** → Cancel + cleanup begins
4. **Cleanup runs in transaction** → All-or-nothing deletion
5. **Run marked as `cancelled`** → Kept for history (but no story data)

### Data Tracking Strategy

Every record created during a pipeline run is tagged with the `pipeline_run_id` for easy cleanup:

```sql
-- When creating leads during lead generation
INSERT INTO leads (title, url, ..., pipeline_run_id)
VALUES (..., 'run-uuid-here');

-- When creating story_research
INSERT INTO story_research (lead_id, ..., pipeline_run_id)
VALUES (..., 'run-uuid-here');

-- Same pattern for:
-- story_generations, story_slides, story_photos, story_thumbnails
```

### Database Schema Updates

```sql
-- Add pipeline_run_id to track origin of each record
ALTER TABLE leads ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_research ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_generations ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_slides ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_photos ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_thumbnails ADD COLUMN pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;

-- Index for fast cleanup queries
CREATE INDEX idx_leads_pipeline_run ON leads(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX idx_story_research_pipeline_run ON story_research(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX idx_story_generations_pipeline_run ON story_generations(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
```

### Cleanup Function

```python
async def cancel_and_cleanup_run(run_id: str) -> dict:
    """
    Cancel a pipeline run and delete all data created during it.
    
    Returns summary of deleted records.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Start transaction
            cur.execute("BEGIN")
            
            # 1. Stop any running workers (signal cancellation)
            signal_cancellation(run_id)
            
            # 2. Delete in reverse dependency order (children first)
            
            # Thumbnails
            cur.execute("""
                DELETE FROM story_thumbnails 
                WHERE pipeline_run_id = %s
                RETURNING id
            """, (run_id,))
            thumbnails_deleted = len(cur.fetchall())
            
            # Slides
            cur.execute("""
                DELETE FROM story_slides 
                WHERE story_generation_id IN (
                    SELECT id FROM story_generations WHERE pipeline_run_id = %s
                )
                RETURNING id
            """, (run_id,))
            slides_deleted = len(cur.fetchall())
            
            # Photos
            cur.execute("""
                DELETE FROM story_photos 
                WHERE pipeline_run_id = %s
                RETURNING id
            """, (run_id,))
            photos_deleted = len(cur.fetchall())
            
            # Story generations
            cur.execute("""
                DELETE FROM story_generations 
                WHERE pipeline_run_id = %s
                RETURNING id
            """, (run_id,))
            generations_deleted = len(cur.fetchall())
            
            # Story research
            cur.execute("""
                DELETE FROM story_research 
                WHERE pipeline_run_id = %s
                RETURNING id
            """, (run_id,))
            research_deleted = len(cur.fetchall())
            
            # Leads (only if created by this run, not pre-existing)
            cur.execute("""
                DELETE FROM leads 
                WHERE pipeline_run_id = %s
                RETURNING id
            """, (run_id,))
            leads_deleted = len(cur.fetchall())
            
            # 3. Update run status
            cur.execute("""
                UPDATE pipeline_runs 
                SET status = 'cancelled',
                    completed_at = now(),
                    updated_at = now()
                WHERE id = %s
            """, (run_id,))
            
            # Commit transaction
            conn.commit()
            
            return {
                "success": True,
                "deleted": {
                    "leads": leads_deleted,
                    "research": research_deleted,
                    "generations": generations_deleted,
                    "slides": slides_deleted,
                    "photos": photos_deleted,
                    "thumbnails": thumbnails_deleted
                }
            }
            
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()
```

### Cancellation UI

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ⚠️ Cancel Pipeline Run?                                                   [×]  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  This will permanently delete all data created during this run:                 │
│                                                                                  │
│  • 12 leads discovered                                                          │
│  • 8 story research packages                                                    │
│  • 8 story generations (with slides)                                            │
│  • 23 photos found                                                              │
│  • 24 thumbnails generated                                                      │
│                                                                                  │
│  ⚠️ This action cannot be undone.                                               │
│                                                                                  │
│  The pipeline run history will be kept for reference, but all story data        │
│  will be permanently removed.                                                   │
│                                                                                  │
│                                          [ Keep Running ]  [ Cancel & Delete ]  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Graceful Worker Shutdown

Workers check for cancellation signals between processing steps:

```python
class PipelineExecutor:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self._cancelled = False
    
    async def check_cancelled(self):
        """Check if this run has been cancelled."""
        if self._cancelled:
            return True
        # Also check database in case signal came from another process
        status = await get_run_status(self.run_id)
        if status == 'cancelled':
            self._cancelled = True
        return self._cancelled
    
    async def process_story(self, story):
        # Before each major step, check cancellation
        if await self.check_cancelled():
            raise CancellationError("Pipeline run was cancelled")
        
        # Do work...
        await self.research_story(story)
        
        if await self.check_cancelled():
            raise CancellationError("Pipeline run was cancelled")
        
        # Continue to next step...
```

### Keep vs Delete Options

In some cases, users may want to keep partial results. Offer both options:

- **"Cancel & Delete All"** — Full cleanup (default, safest)
- **"Cancel & Keep Data"** — Stop execution but preserve created records

```python
@app.post("/api/pipeline/runs/{run_id}/cancel")
async def cancel_run(run_id: str, delete_data: bool = True):
    """
    Cancel a running pipeline.
    
    Args:
        delete_data: If True, delete all data created during this run.
                     If False, just stop execution and keep data.
    """
    if delete_data:
        return await cancel_and_cleanup_run(run_id)
    else:
        return await cancel_run_keep_data(run_id)
```

---

## Run History & Phase Review

Users should be able to view the results of any phase at any time — during execution, after completion, or days later when reviewing past runs.

### Core Principle: Phase Results Are Always Accessible

The Pipeline Manager is not just an execution tool — it's also a **review interface** for pipeline results. The UI supports:

1. **During execution**: Click any completed phase tab to review its results
2. **After completion**: Open any historical run and browse all phases
3. **Days/weeks later**: All run data is preserved for reference

### Pipeline View with Phase Tabs

The pipeline view (`/pipeline/{run_id}`) has a persistent phase navigation bar that lets users jump between phases at any time:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ← Dashboard    Run #48 — Auto Mode                      Dec 21, 2:15 PM        │
│                 Status: ✓ Completed (47 min)                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  PHASE NAVIGATION                                                        │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │    │
│  │  │1. Leads  │ │2. Research│ │3. Text   │ │4. Photos │ │5. Thumbs │      │    │
│  │  │  ✓ 12    │ │  ✓ 12    │ │  ✓ 12    │ │  ✓ 32    │ │  ✓ 36    │      │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘      │    │
│  │       ▲                                                                  │    │
│  │   [Active]                                                               │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ═══════════════════════════════════════════════════════════════════════════    │
│                                                                                  │
│  (Phase 1 content displayed below - user clicked "1. Leads" tab)                │
│                                                                                  │
│  Phase 1: Lead Generation & Curation                               ✓ Complete  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  [Full phase content as shown in Phase 1 wireframe...]                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Phase Tab States

Each tab shows its status with visual indicators:

| State | Tab Appearance | Clickable? |
|-------|----------------|------------|
| Completed | `✓ 12` (green checkmark + count) | ✅ Yes — view results |
| In Progress | `◐ 5/12` (spinner + progress) | ✅ Yes — view partial results |
| Pending | `○ —` (grey, no count) | ⚠️ Limited — shows "Waiting for previous phase" |
| Skipped | `⏭ Skip` (grey) | ✅ Yes — shows skip reason |
| Failed | `✗ Error` (red) | ✅ Yes — shows error details |

### Run Detail View (`/pipeline/{run_id}`)

This is the main review interface. It works the same whether the run is active or completed:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Run #48 Details                                                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─ RUN SUMMARY ───────────────────────────────────────────────────────────┐    │
│  │                                                                          │    │
│  │  Mode:        Auto                                                       │    │
│  │  Status:      ✓ Completed                                                │    │
│  │  Started:     Dec 21, 2:15 PM                                            │    │
│  │  Completed:   Dec 21, 3:02 PM                                            │    │
│  │  Duration:    47 minutes                                                 │    │
│  │                                                                          │    │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │    │
│  │  │  Phase 1    Phase 2    Phase 3    Phase 4    Phase 5               │ │    │
│  │  │  ✓ Leads    ✓ Research ✓ Text     ✓ Photos   ✓ Thumbs              │ │    │
│  │  │  12 found   12 done    12 done    32 found   36 gen'd              │ │    │
│  │  │  (3 min)    (12 min)   (15 min)   (10 min)   (7 min)               │ │    │
│  │  └────────────────────────────────────────────────────────────────────┘ │    │
│  │                                                                          │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  PHASE TABS: [1. Leads ✓] [2. Research ✓] [3. Text ✓] [4. Photos ✓] [5. Thumbs ✓]
│                                                                                  │
│  ═════════════════════════════════════════════════════════════════════════════  │
│                                                                                  │
│  (Selected phase content renders here)                                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Recent Runs List (Dashboard)

The dashboard shows recent runs with quick access to review:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Recent Runs                                                      [View All →]  │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ✓ Run #48 — Auto Mode                               Dec 21, 3:02 PM    │    │
│  │    12 stories • 47 min • All phases complete                            │    │
│  │                                                                          │    │
│  │    Quick View: [Leads] [Research] [Text] [Photos] [Thumbs] [Details →]  │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ✗ Run #47 — Step Mode                               Dec 20, 4:15 PM    │    │
│  │    8 stories • Failed at Photo Research                                  │    │
│  │                                                                          │    │
│  │    Quick View: [Leads] [Research] [Text] [Photos ✗] [—] [Details →]     │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ✓ Run #46 — Auto Mode                               Dec 18, 10:30 AM   │    │
│  │    15 stories • 52 min • All phases complete                            │    │
│  │                                                                          │    │
│  │    Quick View: [Leads] [Research] [Text] [Photos] [Thumbs] [Details →]  │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### API Endpoints for Historical Review

```
# Run history
GET  /api/pipeline/runs                       # List all runs (paginated)
     Query: ?status=completed&limit=20&offset=0

GET  /api/pipeline/runs/{id}                  # Full run details with summary stats

# Phase-specific results (works for any run, active or completed)
GET  /api/pipeline/runs/{id}/phases           # Summary of all phases for this run
GET  /api/pipeline/runs/{id}/phases/1/leads   # Phase 1 detailed results
GET  /api/pipeline/runs/{id}/phases/2/research # Phase 2 detailed results
GET  /api/pipeline/runs/{id}/phases/3/text    # Phase 3 detailed results
GET  /api/pipeline/runs/{id}/phases/4/photos  # Phase 4 detailed results
GET  /api/pipeline/runs/{id}/phases/5/thumbnails # Phase 5 detailed results

# Individual story detail within a run
GET  /api/pipeline/runs/{id}/stories/{story_id}  # Full story data across all phases
```

### URL Structure for Direct Links

Users can bookmark or share links to specific views:

```
/pipeline/{run_id}                    # Run overview (default to current/latest phase)
/pipeline/{run_id}?phase=1            # Jump to Phase 1 results
/pipeline/{run_id}?phase=3            # Jump to Phase 3 results
/pipeline/{run_id}?phase=4&story={id} # Jump to specific story in Phase 4
```

### Data Retention

- **Completed runs**: Kept indefinitely (or until manually deleted)
- **Failed/cancelled runs**: Kept for 30 days by default
- **Run metadata**: Always preserved even if story data is deleted

### Comparison View (Future Enhancement)

For advanced users, allow comparing results between runs:

```
/pipeline/compare?run1={id1}&run2={id2}&phase=1
```

This would show side-by-side lead counts, filter funnel differences, etc.

---

## Pipeline Phases — Detailed UI Specifications

Each phase has a consistent layout with:
- **Header**: Phase name, progress indicator, action buttons
- **Summary Stats**: Key metrics for the phase
- **Story List**: Per-story cards with phase-specific data
- **Detail Panel**: Expandable/modal view for full data

---

### Phase 1: Lead Generation & Curation

**Input:** None (discovers from RSS + Perplexity)
**Output:** Approved leads ready for research

**Sub-steps:**
1. RSS Feed Scan (35+ sources)
2. Perplexity Active Discovery
3. URL Deduplication
4. Smart Gatekeeper (batch filter)
5. Semantic Deduplication
6. Virality Scoring (≥78)
7. Brand Lens Scoring (≥70)
8. Curator Selection

#### Phase 1 UI Wireframe

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Phase 1: Lead Generation & Curation                                            │
│  ████████████████████████████████████████████░░░░░░░░░  Sub-step 7/8           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  DISCOVERY FUNNEL                                                        │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  RSS Feeds ───────────────────────────────▶ 247 articles scanned         │    │
│  │       │                                                                  │    │
│  │       ▼                                                                  │    │
│  │  Perplexity Discovery ─────────────────────▶ 53 new leads found          │    │
│  │       │                                                                  │    │
│  │       ▼                                                                  │    │
│  │  URL Dedup ────────────────────────────────▶ 284 unique (16 dupes)       │    │
│  │       │                                                                  │    │
│  │       ▼                                                                  │    │
│  │  Smart Gatekeeper ─────────────────────────▶ 156 passed (128 filtered)   │    │
│  │       │                        ├─ 67 politics/news                       │    │
│  │       │                        ├─ 41 celebrity/gossip                    │    │
│  │       │                        └─ 20 low-quality                         │    │
│  │       ▼                                                                  │    │
│  │  Semantic Dedup ───────────────────────────▶ 142 unique (14 similar)     │    │
│  │       │                                                                  │    │
│  │       ▼                                                                  │    │
│  │  Virality Score (≥78) ─────────────────────▶ 89 high-viral               │    │
│  │       │                                                                  │    │
│  │       ▼                                                                  │    │
│  │  Brand Lens (≥70) ─────────────────────────▶ 52 on-brand                 │    │
│  │       │                                                                  │    │
│  │       ▼                                                                  │    │
│  │  Curator Selection ────────────────────────▶ 12 SELECTED ✓               │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  SELECTED LEADS (12)                                          [Expand All ▼]    │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                          │    │
│  │  ┌───────────────────────────────────────────────────────────────────┐  │    │
│  │  │  1. The Phantom Time Hypothesis                                    │  │    │
│  │  │     ─────────────────────────────────────────────────────────────  │  │    │
│  │  │     📰 Source: atlasobscura.com                                    │  │    │
│  │  │     ────────────────────────────────────────────────────────────   │  │    │
│  │  │     │ HISTORY │  Viral: 91  │  Brand: 85  │  Interesting: 88      │  │    │
│  │  │     ────────────────────────────────────────────────────────────   │  │    │
│  │  │                                                                    │  │    │
│  │  │     "German historian Heribert Illig claims nearly 300 years      │  │    │
│  │  │     of medieval history were fabricated, including the entire     │  │    │
│  │  │     reign of Charlemagne..."                                      │  │    │
│  │  │                                                                    │  │    │
│  │  │     Curator Reasoning:                                             │  │    │
│  │  │     "Perfect TheBoldUnknown material — challenges historical      │  │    │
│  │  │     consensus with documented evidence. High shareability due     │  │    │
│  │  │     to 'wait, what?' factor. Not conspiracy — legitimate          │  │    │
│  │  │     academic debate."                                              │  │    │
│  │  │                                                                    │  │    │
│  │  │                                      [View Source ↗] [Expand ▼]   │  │    │
│  │  └───────────────────────────────────────────────────────────────────┘  │    │
│  │                                                                          │    │
│  │  ┌───────────────────────────────────────────────────────────────────┐  │    │
│  │  │  2. The Great Emu War of 1932                                      │  │    │
│  │  │     ─────────────────────────────────────────────────────────────  │  │    │
│  │  │     📰 Source: wikipedia.org                                       │  │    │
│  │  │     │ NATURE │  Viral: 94  │  Brand: 82  │  Interesting: 90       │  │    │
│  │  │     ...                                                            │  │    │
│  │  └───────────────────────────────────────────────────────────────────┘  │    │
│  │  ... (10 more)                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  (Step Mode)                              [← Back] [Approve & Continue →]       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Phase 1 Data Fields

| Field | Source | Display |
|-------|--------|---------|
| Title | `leads.title` | Primary heading |
| URL | `leads.url` | Link with domain badge |
| Summary | `leads.summary` | Truncated excerpt (expand for full) |
| Viral Score | `leads.virality_score` | Score badge (green ≥85, yellow ≥78) |
| Brand Score | `leads.brand_score` | Score badge (green ≥80, yellow ≥70) |
| Interestingness | `leads.interestingness_score` | Score badge |
| Viral Hook | `leads.viral_hook` | "Wait, what?" angle identified |
| Domain Tag | Inferred from URL/content | Category badge (HISTORY, SCIENCE, etc.) |
| Curator Reasoning | `story_research.notes` | Italic quote block |
| Source Origin | `leads.source_origin` | "RSS: atlasobscura" or "Perplexity Discovery" |

---

### Phase 2: Story Research

**Input:** Approved leads from Phase 1
**Output:** Research packages with ground truth + hook identification

**Sub-steps:**
1. Ground Truth Research (Perplexity)
2. Hook Identification (GPT-4o)
3. Optional Deep Dive

#### Phase 2 UI Wireframe

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Phase 2: Story Research                                                        │
│  ████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  5/12 stories complete   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Summary: 5 ✓ complete • 1 ◐ in progress • 6 ○ queued                           │
│                                                                                  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ✓ The Phantom Time Hypothesis                              COMPLETED   │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  ┌─ GROUND TRUTH ──────────────────────────────────────────────────┐    │    │
│  │  │  The Phantom Time Hypothesis was proposed by Heribert Illig     │    │    │
│  │  │  in 1991. It suggests that 297 years (AD 614–911) were          │    │    │
│  │  │  fabricated by Holy Roman Emperor Otto III, Pope Sylvester II,  │    │    │
│  │  │  and Byzantine Emperor Constantine VII to place themselves at   │    │    │
│  │  │  the millennial year AD 1000.                                   │    │    │
│  │  │                                                                  │    │    │
│  │  │  Key claims:                                                     │    │    │
│  │  │  • Charlemagne never existed or was a different person          │    │    │
│  │  │  • Architectural inconsistencies in Carolingian structures      │    │    │
│  │  │  • Gaps in archaeological record for this period                │    │    │
│  │  │  • Calendar reform by Pope Gregory XIII introduced errors       │    │    │
│  │  │                                                                  │    │    │
│  │  │  Counter-evidence:                                               │    │    │
│  │  │  • Islamic and Byzantine records align with standard timeline   │    │    │
│  │  │  • Dendrochronology confirms dates                              │    │    │
│  │  │  • Solar eclipse records match astronomical calculations        │    │    │
│  │  │                                             [Show Full ▼] (2,341 chars) │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  │                                                                          │    │
│  │  ┌─ THE HOOK ──────────────────────────────────────────────────────┐    │    │
│  │  │  "What if nearly 300 years of history never happened?"          │    │    │
│  │  │                                                                  │    │    │
│  │  │  Angle: A respected German historian found mathematical and     │    │    │
│  │  │  architectural evidence suggesting the Early Middle Ages were   │    │    │
│  │  │  invented. Charlemagne might be fiction.                        │    │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  │                                                                          │    │
│  │  ┌─ PRIMARY SOURCES ───────────────────────────────────────────────┐    │    │
│  │  │  • Illig, H. "Das erfundene Mittelalter" (1996)                 │    │    │
│  │  │  • Niemitz, H. "Did the Early Middle Ages Really Exist?" (1995) │    │    │
│  │  │  • Journal of Interdisciplinary History, Vol. 31, No. 2         │    │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ◐ The Great Emu War of 1932                               IN PROGRESS  │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  ████████████████░░░░░░░░░░░░  Step 2/3: Hook Identification            │    │
│  │                                                                          │    │
│  │  ┌─ GROUND TRUTH ──────────────────────────────────────────────────┐    │    │
│  │  │  The Great Emu War was a 1932 wildlife management operation     │    │    │
│  │  │  in Australia. Soldiers armed with Lewis guns attempted to      │    │    │
│  │  │  cull emus that were destroying crops in Western Australia...   │    │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  │                                                                          │    │
│  │  ┌─ THE HOOK ──────────────────────────────────────────────────────┐    │    │
│  │  │  ⏳ Generating...                                                │    │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ○ The Taos Hum Mystery                                         QUEUED  │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │  Waiting in queue... (position 1)                                        │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ... (9 more stories)                                                           │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Phase 2 Data Fields

| Field | Source | Display |
|-------|--------|---------|
| Story Title | `leads.title` | Card heading |
| Status | `story_research.status` | Badge: queued/in_progress/completed/skipped |
| Ground Truth | `story_research.research_data.ground_truth` | Expandable text block |
| Hook/Angle | `story_research.research_data.follow_up.answer` | Highlighted quote block |
| Primary Sources | `story_research.primary_sources[]` | Bulleted list |
| Source URLs | `story_research.primary_source_urls[]` | Clickable links |
| Progress Step | Computed from research_data presence | "Step 1/3", "Step 2/3", etc. |
| Character Count | `len(ground_truth)` | Small badge |

---

### Phase 3: Text Generation

**Input:** Completed research from Phase 2
**Output:** Story slides, cover options, captions, hashtags

**Sub-steps:**
1. Story Slides Generation (7-9 slides)
2. Cover Options Generation (6 variations)
3. Instagram Caption Generation
4. Hashtags Generation

#### Phase 3 UI Wireframe

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Phase 3: Text Generation                                                       │
│  ████████████████████████████████████████░░░░░░░░░░░░  8/12 stories complete   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Summary: 8 ✓ complete • 1 ◐ in progress • 3 ○ queued                           │
│                                                                                  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ✓ The Phantom Time Hypothesis                              COMPLETED   │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  ┌─ COVER OPTIONS (6) ────────────────────────────────────────────┐     │    │
│  │  │                                                                 │     │    │
│  │  │  ● Option 1 (SELECTED)                                         │     │    │
│  │  │  ┌──────────────────────────────────────────────────────────┐  │     │    │
│  │  │  │  "Nearly 300 Years of History                            │  │     │    │
│  │  │  │   May Have Never Happened"                               │  │     │    │
│  │  │  │   ───────────────────────────────────────────────────    │  │     │    │
│  │  │  │   One German historian found evidence that Charlemagne   │  │     │    │
│  │  │  │   might be completely fictional.                         │  │     │    │
│  │  │  │   ───────────────────────────────────────────────────    │  │     │    │
│  │  │  │   │ HISTORY │                                            │  │     │    │
│  │  │  └──────────────────────────────────────────────────────────┘  │     │    │
│  │  │                                                                 │     │    │
│  │  │  ○ Option 2: "Did the Medieval Period Actually Exist?"         │     │    │
│  │  │  ○ Option 3: "The 297 Years That Never Were"                   │     │    │
│  │  │  ○ Option 4: "Charlemagne: Emperor or Invention?"              │     │    │
│  │  │  ○ Option 5: "History's Greatest Cover-Up?"                    │     │    │
│  │  │  ○ Option 6: "The Fabricated Middle Ages"                      │     │    │
│  │  │                                                   [Browse All] │     │    │
│  │  └─────────────────────────────────────────────────────────────────┘     │    │
│  │                                                                          │    │
│  │  ┌─ SLIDES (9) ───────────────────────────────────────────────────┐     │    │
│  │  │                                                                 │     │    │
│  │  │  1 │ HOOK        │ In 1991, a German historian made a claim... │     │    │
│  │  │  2 │ CONTEXT     │ Heribert Illig proposed that 297 years...   │     │    │
│  │  │  3 │ EVIDENCE    │ His evidence includes architectural...       │     │    │
│  │  │  4 │ DEEP DIVE   │ The Carolingian Renaissance supposedly...   │     │    │
│  │  │  5 │ TWIST       │ But here's where it gets strange...         │     │    │
│  │  │  6 │ COUNTER     │ Mainstream historians point to Islamic...   │     │    │
│  │  │  7 │ RESOLUTION  │ While the hypothesis remains fringe...      │     │    │
│  │  │  8 │ IMPLICATION │ If true, it would mean every medieval...    │     │    │
│  │  │  9 │ CLOSER      │ Sometimes the strangest theories reveal...  │     │    │
│  │  │                                                                 │     │    │
│  │  │  Total: 2,341 characters                      [Preview Slides] │     │    │
│  │  └─────────────────────────────────────────────────────────────────┘     │    │
│  │                                                                          │    │
│  │  ┌─ CAPTION & HASHTAGS ───────────────────────────────────────────┐     │    │
│  │  │                                                                 │     │    │
│  │  │  Caption (312 chars):                                          │     │    │
│  │  │  "What if nearly 300 years of history were completely made up? │     │    │
│  │  │   One German historian thinks the Early Middle Ages never      │     │    │
│  │  │   happened. 🧵⬇️"                                               │     │    │
│  │  │                                                                 │     │    │
│  │  │  Hashtags (15):                                                 │     │    │
│  │  │  #history #medieval #conspiracy #strangebutrue #didyouknow     │     │    │
│  │  │  #charlemagne #middleages #phantomtime #historymystery         │     │    │
│  │  │  #fascinating #unbelievable #mindblown #theboldunknown         │     │    │
│  │  │  #curiosity #learnontiktok                                     │     │    │
│  │  │                                                                 │     │    │
│  │  └─────────────────────────────────────────────────────────────────┘     │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ◐ The Great Emu War of 1932                               IN PROGRESS  │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  ████████████████████░░░░░░░░░░░░░░░░  Step 2/4: Cover Options          │    │
│  │                                                                          │    │
│  │  ✓ Slides generated (8 slides, 2,156 chars)                             │    │
│  │  ◐ Generating cover options...                                           │    │
│  │  ○ Caption pending                                                       │    │
│  │  ○ Hashtags pending                                                      │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Phase 3 Data Fields

| Field | Source | Display |
|-------|--------|---------|
| Hook Title | `story_generations.hook_title` | Large heading |
| Subtitle | `story_generations.subtitle` | Secondary text |
| Domain Tag | `story_generations.domain_tag` | Category badge |
| All Options | `story_generations.generation_metadata.options[]` | Radio list |
| Selected Option ID | `story_generations.generation_metadata.selected_id` | Highlighted |
| Slides | `story_slides[]` | Numbered list with tags |
| Slide Text | `story_slides.text_content` | Truncated, expandable |
| Slide Tag | `story_slides.document_type_tag` | HOOK, CONTEXT, etc. |
| Paragraph Count | `story_slides.paragraph_count` | Small indicator |
| Total Chars | Computed sum | Stats badge |
| Caption | `story_generations.instagram_caption` | Text block |
| Hashtags | `story_generations.hashtags[]` | Tag pills |

---

### Phase 4: Photo Research

**Input:** Story generations from Phase 3
**Output:** Curated, verified photos with placements

**Sub-steps:**
1. Query Generation (slide-aware)
2. Google Image Search
3. URL Validation
4. Page Scraping (context)
5. Vision Analysis (scoring)
6. Photo Placement

#### Phase 4 UI Wireframe

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Phase 4: Photo Research                                                        │
│  ████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░  6/12 stories complete   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Summary: 6 ✓ complete • 2 ◐ in progress • 4 ○ queued                           │
│  Photos: 47 found • 32 approved • 15 rejected                                   │
│                                                                                  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ✓ The Phantom Time Hypothesis                              COMPLETED   │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  ┌─ SEARCH QUERIES USED ──────────────────────────────────────────┐     │    │
│  │  │  • "Heribert Illig phantom time historian photo"               │     │    │
│  │  │  • "Charlemagne medieval illustration manuscript"              │     │    │
│  │  │  • "Aachen Cathedral Carolingian architecture"                 │     │    │
│  │  │  • "medieval manuscript forgery evidence"                      │     │    │
│  │  └─────────────────────────────────────────────────────────────────┘     │    │
│  │                                                                          │    │
│  │  ┌─ PHOTOS (4 approved, 3 rejected) ──────────────────────────────┐     │    │
│  │  │                                                                 │     │    │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐               │     │    │
│  │  │  │ ██████  │ │ ██████  │ │ ██████  │ │ ██████  │               │     │    │
│  │  │  │ ██████  │ │ ██████  │ │ ██████  │ │ ██████  │               │     │    │
│  │  │  │ ██████  │ │ ██████  │ │ ██████  │ │ ██████  │               │     │    │
│  │  │  │ ██████  │ │ ██████  │ │ ██████  │ │ ██████  │               │     │    │
│  │  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘               │     │    │
│  │  │   ✓ APPROVED  ✓ APPROVED  ✓ APPROVED  ✓ APPROVED               │     │    │
│  │  │   ★ HERO      Rel: 9/10   Rel: 8/10   Rel: 7/10                │     │    │
│  │  │   Rel: 9/10   Ver: 8/10   Ver: 9/10   Ver: 7/10                │     │    │
│  │  │   Ver: 9/10   Use: 8/10   Use: 7/10   Use: 8/10                │     │    │
│  │  │   Use: 9/10                                                     │     │    │
│  │  │                                                                 │     │    │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐                           │     │    │
│  │  │  │ ░░░░░░  │ │ ░░░░░░  │ │ ░░░░░░  │   Rejected:               │     │    │
│  │  │  │ ░░░░░░  │ │ ░░░░░░  │ │ ░░░░░░  │   • Low relevance (2)     │     │    │
│  │  │  │ ░░░░░░  │ │ ░░░░░░  │ │ ░░░░░░  │   • AI-generated (1)      │     │    │
│  │  │  │ ░░░░░░  │ │ ░░░░░░  │ │ ░░░░░░  │                           │     │    │
│  │  │  └─────────┘ └─────────┘ └─────────┘                           │     │    │
│  │  │   ✗ REJECTED  ✗ REJECTED  ✗ REJECTED                           │     │    │
│  │  │                                                                 │     │    │
│  │  └─────────────────────────────────────────────────────────────────┘     │    │
│  │                                                                          │    │
│  │  ┌─ PLACEMENT ASSIGNMENTS ────────────────────────────────────────┐     │    │
│  │  │                                                                 │     │    │
│  │  │  Cover ─ Slide 1 ─ Slide 2 ─ [PHOTO 1★] ─ Slide 3 ─ Slide 4   │     │    │
│  │  │         ─ [photo 2] ─ Slide 5 ─ Slide 6 ─ [photo 3] ─         │     │    │
│  │  │         ─ Slide 7 ─ Slide 8 ─ [photo 4] ─ Slide 9 ─ Close     │     │    │
│  │  │                                                                 │     │    │
│  │  │  ★ = Hero photo (enabled by default)                           │     │    │
│  │  │  Photos 2-4 are placed but disabled (user can enable in editor)│     │    │
│  │  │                                                                 │     │    │
│  │  └─────────────────────────────────────────────────────────────────┘     │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ◐ The Great Emu War of 1932                               IN PROGRESS  │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  ████████████████░░░░░░░░░░░░░░░░  Step 4/6: Page Scraping              │    │
│  │                                                                          │    │
│  │  ✓ Queries generated (4 queries)                                        │    │
│  │  ✓ Images found (12 candidates)                                         │    │
│  │  ✓ URLs validated (10 accessible)                                       │    │
│  │  ◐ Scraping source context... (7/10)                                    │    │
│  │  ○ Vision analysis pending                                              │    │
│  │  ○ Placement pending                                                    │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Photo Detail Modal (click on any photo)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Photo Analysis                                                           [×]   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌───────────────────────────────┐  ┌──────────────────────────────────────┐    │
│  │                               │  │  SCORES                              │    │
│  │     ████████████████████     │  │  ────────────────────────────────    │    │
│  │     ████████████████████     │  │                                      │    │
│  │     ████████████████████     │  │  Relevance      ████████░░  9/10     │    │
│  │     ████████████████████     │  │  Verifiability  ████████░░  8/10     │    │
│  │     ████████████████████     │  │  Usability      █████████░  9/10     │    │
│  │     ████████████████████     │  │                                      │    │
│  │     ████████████████████     │  │  AI Detection   ✓ Not AI-generated   │    │
│  │                               │  │                                      │    │
│  └───────────────────────────────┘  │  Status: ✓ APPROVED                 │    │
│                                      │                                      │    │
│                                      └──────────────────────────────────────┘    │
│                                                                                  │
│  ┌─ SOURCE INFORMATION ─────────────────────────────────────────────────────┐   │
│  │                                                                           │   │
│  │  Source URL:  atlasobscura.com/articles/phantom-time-hypothesis          │   │
│  │  Page Title:  "The Phantom Time Hypothesis: Did the Middle Ages Happen?" │   │
│  │  Image Context: "Portrait of Heribert Illig at a 2003 conference"        │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  ┌─ AI ANALYSIS ────────────────────────────────────────────────────────────┐   │
│  │                                                                           │   │
│  │  Description:                                                             │   │
│  │  "Photograph of a middle-aged man with grey hair at a podium,            │   │
│  │   appearing to be giving a lecture. Academic setting visible in          │   │
│  │   background. Professional quality photograph."                          │   │
│  │                                                                           │   │
│  │  Relevance Reasoning:                                                     │   │
│  │  "Image shows Heribert Illig, the originator of the Phantom Time         │   │
│  │   Hypothesis. Directly relevant to story subject matter."                │   │
│  │                                                                           │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  Search Query Used: "Heribert Illig phantom time historian photo"               │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Phase 4 Data Fields

| Field | Source | Display |
|-------|--------|---------|
| Search Queries | Generated by QueryGenerator | Bullet list |
| Photo Thumbnail | `story_photos.image_url` | Thumbnail grid |
| Relevance Score | `story_photos.relevance_score` | Score bar 0-10 |
| Verifiability Score | `story_photos.verifiability_score` | Score bar 0-10 |
| Usability Score | `story_photos.metadata.usability_score` | Score bar 0-10 |
| AI Detection | `story_photos.metadata.is_ai_generated` | Badge ✓/✗ |
| Status | `story_photos.status` | approved/rejected badge |
| Description | `story_photos.description` | AI-generated description |
| Caption | `story_photos.caption` | Generated caption text |
| Source Attribution | `story_photos.source_attribution` | Source credit |
| Source Page URL | `story_photos.source_page_url` | Clickable link |
| Placement | `story_photos.metadata.placement` | Diagram position |
| Hero Indicator | `story_photos.metadata.placement.enabled` | Star badge |

---

### Phase 5: Thumbnail Generation

**Input:** Story generations from Phase 3
**Output:** 3 AI-generated cover concepts per story

**Sub-steps:**
1. Concept Generation (GPT-5.2)
2. Prompt Building
3. Image Generation (Gemini)

#### Phase 5 UI Wireframe

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Phase 5: Thumbnail Generation                                                  │
│  ████████████████████████████████████████████████░░░░  10/12 stories complete  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Summary: 10 ✓ complete • 1 ◐ in progress • 1 ○ queued                          │
│  Thumbnails: 30 generated • 0 failed                                            │
│                                                                                  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ✓ The Phantom Time Hypothesis                              COMPLETED   │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  ┌─ GENERATED CONCEPTS (3) ───────────────────────────────────────┐     │    │
│  │  │                                                                 │     │    │
│  │  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │     │    │
│  │  │  │               │  │               │  │               │       │     │    │
│  │  │  │   ████████    │  │   ████████    │  │   ████████    │       │     │    │
│  │  │  │   ████████    │  │   ████████    │  │   ████████    │       │     │    │
│  │  │  │   ████████    │  │   ████████    │  │   ████████    │       │     │    │
│  │  │  │   ████████    │  │   ████████    │  │   ████████    │       │     │    │
│  │  │  │   ████████    │  │   ████████    │  │   ████████    │       │     │    │
│  │  │  │   ████████    │  │   ████████    │  │   ████████    │       │     │    │
│  │  │  │               │  │               │  │               │       │     │    │
│  │  │  └───────────────┘  └───────────────┘  └───────────────┘       │     │    │
│  │  │       LITERAL           SYMBOLIC         ATMOSPHERIC           │     │    │
│  │  │      ● Selected        ○ Option 2        ○ Option 3            │     │    │
│  │  │                                                                 │     │    │
│  │  └─────────────────────────────────────────────────────────────────┘     │    │
│  │                                                                          │    │
│  │  ┌─ CONCEPT DETAILS ──────────────────────────────────────────────┐     │    │
│  │  │                                                                 │     │    │
│  │  │  ● Concept 1: LITERAL                                          │     │    │
│  │  │    "Ancient manuscript pages scattered across a stone table    │     │    │
│  │  │     in a dimly lit medieval scriptorium, with a quill and     │     │    │
│  │  │     inkwell. Dramatic lighting from a single candle casts     │     │    │
│  │  │     long shadows. Some pages appear to be fading or erasing   │     │    │
│  │  │     themselves, suggesting impermanence of historical record." │     │    │
│  │  │                                                                 │     │    │
│  │  │  ○ Concept 2: SYMBOLIC                                         │     │    │
│  │  │    "A grand hourglass with 297 years worth of sand frozen     │     │    │
│  │  │     mid-fall, suspended in impossible stillness. Behind it,   │     │    │
│  │  │     a medieval tapestry slowly unravels into threads of       │     │    │
│  │  │     light. Dark, contemplative mood."                         │     │    │
│  │  │                                                                 │     │    │
│  │  │  ○ Concept 3: ATMOSPHERIC                                      │     │    │
│  │  │    "An empty throne room in a Carolingian palace, dust motes  │     │    │
│  │  │     floating in shafts of light from high windows. The        │     │    │
│  │  │     throne sits empty, crown resting on the seat. Mood of     │     │    │
│  │  │     absence and mystery."                                      │     │    │
│  │  │                                                                 │     │    │
│  │  └─────────────────────────────────────────────────────────────────┘     │    │
│  │                                                                          │    │
│  │  Note: Selection can be changed in the Pre-Assembler editor              │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ◐ The Great Emu War of 1932                               IN PROGRESS  │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  ████████████████████████████░░░░░░░░░░  Step 3/3: Image Generation     │    │
│  │                                                                          │    │
│  │  ✓ Concepts generated (3 concepts)                                      │    │
│  │  ✓ Prompts built                                                        │    │
│  │  ◐ Generating images... (2/3 complete)                                  │    │
│  │                                                                          │    │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐               │    │
│  │  │               │  │               │  │               │               │    │
│  │  │   ████████    │  │   ████████    │  │   ░░░░░░░░    │               │    │
│  │  │   ████████    │  │   ████████    │  │   ░░░░░░░░    │               │    │
│  │  │   ████████    │  │   ████████    │  │   ⏳ Gen...   │               │    │
│  │  │   ████████    │  │   ████████    │  │   ░░░░░░░░    │               │    │
│  │  │               │  │               │  │               │               │    │
│  │  └───────────────┘  └───────────────┘  └───────────────┘               │    │
│  │       ✓ Done          ✓ Done          ◐ Generating                     │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  ✅ All thumbnails generated!                                                   │
│                                                                                  │
│  Stories are now ready for the Pre-Assembler.                                   │
│                                                                                  │
│                                      [ Open Pre-Assembler → ]                   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Phase 5 Data Fields

| Field | Source | Display |
|-------|--------|---------|
| Story Title | `story_generations.hook_title` | Card heading |
| Thumbnail Image | `story_thumbnails.image_url` or DB base64 | 4:5 aspect ratio preview |
| Concept Number | `story_thumbnails.concept_number` | 1, 2, 3 |
| Concept Type | `story_thumbnails.concept_type` | LITERAL/SYMBOLIC/ATMOSPHERIC badge |
| Scene Description | `story_thumbnails.scene_description` | Expandable text |
| Full Prompt | `story_thumbnails.full_prompt` | Hidden, show on hover/click |
| Status | `story_thumbnails.status` | pending/generating/generated/failed |
| Is Selected | `story_thumbnails.is_selected` | Radio indicator |
| Generation Metadata | `story_thumbnails.generation_metadata` | Model used, timing |

---

## Completed Pipeline Summary View

When all phases complete, show a summary before handoff to Pre-Assembler:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ✅ Pipeline Complete!                                                          │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  Run #48 completed in 47 minutes                                                │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  SUMMARY                                                                 │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  Phase 1: Lead Generation    ✓  247 scanned → 12 selected              │    │
│  │  Phase 2: Story Research     ✓  12/12 researched                       │    │
│  │  Phase 3: Text Generation    ✓  12/12 stories + 108 slides             │    │
│  │  Phase 4: Photo Research     ✓  47 found → 32 approved                 │    │
│  │  Phase 5: Thumbnails         ✓  36 generated (3 per story)             │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  STORIES READY FOR ASSEMBLY                                              │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  1. The Phantom Time Hypothesis       │ HISTORY │  9 slides  4 photos  │    │
│  │  2. The Great Emu War of 1932         │ NATURE  │  8 slides  3 photos  │    │
│  │  3. The Taos Hum Mystery              │ SCIENCE │  8 slides  2 photos  │    │
│  │  4. The Dancing Plague of 1518        │ HISTORY │  9 slides  4 photos  │    │
│  │  5. Dyatlov Pass Incident             │ MYSTERY │  9 slides  5 photos  │    │
│  │  ... (7 more)                                                            │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│                            [ View Run Details ]  [ Open Pre-Assembler → ]       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Technical Architecture

### Module Structure

```
pipeline_manager/
├── __init__.py
├── main.py                 # FastAPI application
├── config.py               # Configuration
├── models.py               # Pydantic models
├── db.py                   # Database operations
├── executor.py             # Pipeline execution logic
├── workers/
│   ├── __init__.py
│   ├── lead_generator.py   # Lead gen adapter
│   ├── curator.py          # Curation adapter
│   ├── story_researcher.py # Research adapter
│   ├── text_generator.py   # Text gen adapter
│   ├── photo_researcher.py # Photo research adapter
│   └── thumbnail_generator.py # Thumbnail adapter
├── static/
│   ├── index.html          # Dashboard
│   ├── pipeline.html       # Pipeline view
│   └── js/
│       ├── pipeline.js     # Pipeline logic
│       └── components.js   # UI components
└── requirements.txt
```

### Integration Approach

**Adapter Pattern:** Each worker module wraps the existing CLI-based modules, calling their core functions directly rather than spawning subprocesses. This provides:
- Better error capture
- Progress callbacks
- Database transaction control
- Graceful cancellation

```python
# Example: workers/story_researcher.py
from story_researcher.db import Database
from story_researcher.researcher import Researcher

class StoryResearcherWorker:
    def __init__(self, progress_callback=None):
        self.db = Database()
        self.researcher = Researcher()
        self.progress_callback = progress_callback
    
    async def process_story(self, research_id: str) -> dict:
        """Process a single story with progress updates."""
        self.db.update_status(research_id, 'in_progress')
        self._emit_progress("started", research_id)
        
        try:
            result = self.researcher.research_story(story)
            self.db.update_research_results(research_id, result)
            self._emit_progress("completed", research_id)
            return {"success": True, "result": result}
        except Exception as e:
            self._emit_progress("failed", research_id, error=str(e))
            return {"success": False, "error": str(e)}
```

### Database Schema Additions

```sql
-- =============================================================================
-- NEW TABLES
-- =============================================================================

-- Pipeline run tracking
CREATE TABLE public.pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mode TEXT NOT NULL CHECK (mode IN ('auto', 'step')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
    current_phase TEXT,
    current_phase_index INTEGER DEFAULT 0,
    total_phases INTEGER DEFAULT 5,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    config JSONB DEFAULT '{}',
    -- Summary stats for quick display
    stats JSONB DEFAULT '{"leads_created": 0, "research_completed": 0, "generations_completed": 0, "photos_found": 0, "thumbnails_generated": 0}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Per-story progress within a pipeline run
CREATE TABLE public.pipeline_story_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    story_research_id UUID REFERENCES story_research(id) ON DELETE SET NULL,
    story_generation_id UUID REFERENCES story_generations(id) ON DELETE SET NULL,
    phase_statuses JSONB DEFAULT '{}',
    error_log JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Index for finding active runs quickly
CREATE INDEX idx_pipeline_runs_status ON pipeline_runs(status) WHERE status IN ('running', 'paused');

-- =============================================================================
-- MODIFICATIONS TO EXISTING TABLES (for data cleanup tracking)
-- =============================================================================

-- Track which pipeline run created each record (for cleanup on cancellation)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_research ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_generations ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_photos ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;
ALTER TABLE story_thumbnails ADD COLUMN IF NOT EXISTS pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;

-- Indexes for efficient cleanup queries
CREATE INDEX IF NOT EXISTS idx_leads_pipeline_run ON leads(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_story_research_pipeline_run ON story_research(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_story_generations_pipeline_run ON story_generations(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_story_photos_pipeline_run ON story_photos(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_story_thumbnails_pipeline_run ON story_thumbnails(pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;

-- =============================================================================
-- EXAMPLE DATA STRUCTURES
-- =============================================================================

-- Example phase_statuses JSON:
-- {
--   "lead_generation": {"status": "completed", "started_at": "...", "completed_at": "...", "count": 15},
--   "curation": {"status": "completed", "result": {"approved": true, "reasoning": "..."}},
--   "story_research": {"status": "in_progress", "started_at": "..."},
--   "text_generation": {"status": "pending"},
--   "photo_research": {"status": "pending"},
--   "thumbnail_generation": {"status": "pending"}
-- }

-- Example stats JSON:
-- {
--   "leads_created": 15,
--   "leads_approved": 8,
--   "research_completed": 8,
--   "generations_completed": 8,
--   "photos_found": 24,
--   "thumbnails_generated": 24
-- }
```

### API Endpoints

```
# Session & Active Run
GET    /api/pipeline/active             # Check for active (running/paused) run → auto-redirect

# Pipeline Management
POST   /api/pipeline/start              # Start new pipeline run
       Body: { "mode": "auto" | "step", "config": {...} }
GET    /api/pipeline/runs               # List pipeline runs (paginated, most recent first)
GET    /api/pipeline/runs/{id}          # Get run details including all story statuses
POST   /api/pipeline/runs/{id}/pause    # Pause running pipeline (workers finish current story)
POST   /api/pipeline/runs/{id}/resume   # Resume paused pipeline
POST   /api/pipeline/runs/{id}/cancel   # Cancel pipeline
       Query: ?delete_data=true         # true = delete all created data, false = keep data
DELETE /api/pipeline/runs/{id}          # Delete run history (only for completed/cancelled runs)

# Phase Control (Step Mode)
POST   /api/pipeline/runs/{id}/phase/{phase}/start   # Start specific phase
POST   /api/pipeline/runs/{id}/phase/{phase}/retry   # Retry failed phase  
POST   /api/pipeline/runs/{id}/phase/{phase}/skip    # Skip phase (mark as skipped, continue)
POST   /api/pipeline/runs/{id}/phase/{phase}/approve # Approve phase results (Step Mode)

# Real-time Updates (Server-Sent Events)
GET    /api/pipeline/runs/{id}/stream   # SSE stream for progress updates
       Events: progress, phase_complete, story_update, error, done

# Phase Results
GET    /api/pipeline/runs/{id}/leads            # Get lead gen results
GET    /api/pipeline/runs/{id}/curation         # Get curation results  
GET    /api/pipeline/runs/{id}/research         # Get research results
GET    /api/pipeline/runs/{id}/text             # Get text gen results
GET    /api/pipeline/runs/{id}/photos           # Get photo research results
GET    /api/pipeline/runs/{id}/thumbnails       # Get thumbnail results

# Cleanup Preview (before cancel)
GET    /api/pipeline/runs/{id}/cleanup-preview  # Get counts of records that would be deleted
```

### Real-time Progress Updates

Use Server-Sent Events (SSE) for efficient real-time updates:

```python
@app.get("/api/pipeline/runs/{run_id}/stream")
async def stream_progress(run_id: str, request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            
            status = get_pipeline_status(run_id)
            yield {
                "event": "progress",
                "data": json.dumps(status)
            }
            
            if status["status"] in ("completed", "failed", "cancelled"):
                yield {"event": "done", "data": "{}"}
                break
            
            await asyncio.sleep(1)
    
    return EventSourceResponse(event_generator())
```

---

## UI Design

### Design Principles (Apple-Inspired)

**Color Palette:**
```css
:root {
    --bg-primary: #FFFFFF;
    --bg-secondary: #F5F5F7;
    --bg-tertiary: #E8E8ED;
    --text-primary: #1D1D1F;
    --text-secondary: #6E6E73;
    --text-tertiary: #86868B;
    --accent: #007AFF;
    --success: #34C759;
    --warning: #FF9500;
    --danger: #FF3B30;
    --border: rgba(0, 0, 0, 0.1);
}
```

**Typography:**
- System fonts: `-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter'`
- Clean, minimal, high contrast
- Generous whitespace

**Components:**
- Rounded corners (12-20px)
- Subtle shadows
- Glassmorphism for overlays
- Smooth transitions (200-300ms)

### Main Dashboard (`/`)

**With NO active run:**
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Pipeline Manager                                              [Pre-Assembler ▶]│
│  Orchestrate your content pipeline                                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Start New Pipeline                                                      │    │
│  │  ┌─────────────────────┐  ┌─────────────────────┐                       │    │
│  │  │  ⚡ Auto Mode       │  │  🎛️ Step Mode       │                       │    │
│  │  │  Run full pipeline  │  │  Phase by phase     │                       │    │
│  │  │  automatically      │  │  with approval      │                       │    │
│  │  │                     │  │                     │                       │    │
│  │  │  [ Start Auto ]     │  │  [ Start Step ]     │                       │    │
│  │  └─────────────────────┘  └─────────────────────┘                       │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  Recent Runs                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ● Run #47 — Auto Mode                          Dec 21, 10:30 AM        │    │
│  │    Status: Completed ✓  |  12 stories  |  Duration: 45 min              │    │
│  │                                                          [View Details] │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**With an ACTIVE run (running or paused) — shown at top:**
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Pipeline Manager                                              [Pre-Assembler ▶]│
│  Orchestrate your content pipeline                                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ⚡ ACTIVE PIPELINE RUN                                                  │    │
│  │  ─────────────────────────────────────────────────────────────────────  │    │
│  │                                                                          │    │
│  │  Run #48 — Auto Mode                                                    │    │
│  │  ████████████████████░░░░░░░░░░░░  Phase 3/5: Text Generation           │    │
│  │                                                                          │    │
│  │  • 8 stories in progress                                                │    │
│  │  • 5/8 text generations complete                                        │    │
│  │  • Started: Dec 21, 2:15 PM (running 23 min)                            │    │
│  │                                                                          │    │
│  │              [ 👁️ View Progress ]         [ ⏹️ Cancel Run ]              │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  Start New Pipeline (will cancel the active run above)                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  ┌─────────────────────┐  ┌─────────────────────┐                       │    │
│  │  │  ⚡ Auto Mode       │  │  🎛️ Step Mode       │                       │    │
│  │  │  (disabled)         │  │  (disabled)         │                       │    │
│  │  └─────────────────────┘  └─────────────────────┘                       │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Frontend behavior on page load:**
```javascript
// dashboard.js
document.addEventListener('alpine:init', () => {
    Alpine.data('dashboard', () => ({
        activeRun: null,
        recentRuns: [],
        loading: true,

        async init() {
            // Check for active run first
            const activeResp = await fetch('/api/pipeline/active');
            const activeData = await activeResp.json();
            
            if (activeData.has_active_run) {
                this.activeRun = activeData.run;
                // Start polling for updates while on dashboard
                this.startPolling();
            }
            
            // Load recent runs
            const runsResp = await fetch('/api/pipeline/runs?limit=10');
            const runsData = await runsResp.json();
            this.recentRuns = runsData.runs;
            
            this.loading = false;
        },

        async viewActiveRun() {
            if (this.activeRun) {
                window.location.href = `/pipeline/${this.activeRun.id}`;
            }
        },

        async cancelActiveRun() {
            if (!this.activeRun) return;
            // Show confirmation modal first
            this.showCancelModal = true;
        },

        startPolling() {
            // Poll every 3 seconds to update active run progress
            this.pollInterval = setInterval(async () => {
                if (!this.activeRun) {
                    clearInterval(this.pollInterval);
                    return;
                }
                const resp = await fetch(`/api/pipeline/runs/${this.activeRun.id}`);
                const data = await resp.json();
                this.activeRun = data;
                
                // If run completed/failed/cancelled, stop polling
                if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                    this.activeRun = null;
                    clearInterval(this.pollInterval);
                    // Refresh recent runs list
                    this.init();
                }
            }, 3000);
        }
    }));
});
```

### Pipeline View (`/pipeline/{run_id}`)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ← Back    Pipeline Run #48                                   [Pause] [Cancel] │
│            Step Mode — Phase 3 of 5                                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Phase Progress                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                          │    │
│  │  [1. Lead Gen] ──✓──► [2. Research] ──✓──► [3. Text Gen] ──●──►         │    │
│  │      ✓ Done           ✓ Done              ● In Progress                  │    │
│  │                                                                          │    │
│  │       ──► [4. Photos] ──○──► [5. Thumbnails] ──○──►                      │    │
│  │            ○ Pending        ○ Pending                                    │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ───────────────────────────────────────────────────────────────────────────    │
│                                                                                  │
│  Current Phase: Text Generation                         [Retry] [Skip Phase]    │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Processing 8 stories...                                                 │    │
│  │  ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  5/8 completed       │    │
│  │                                                                          │    │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │    │
│  │  │  ✓ The Phantom Time Hypothesis                                  │    │    │
│  │  │    9 slides • 2,341 chars • Caption ready                       │    │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │    │
│  │  │  ✓ The Great Emu War of 1932                                    │    │    │
│  │  │    8 slides • 2,156 chars • Caption ready                       │    │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │    │
│  │  │  ◐ The Taos Hum Mystery                            In Progress  │    │    │
│  │  │    Generating slides... (step 1/4)                              │    │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │    │
│  │  │  ○ The Dancing Plague of 1518                       Pending     │    │    │
│  │  └─────────────────────────────────────────────────────────────────┘    │    │
│  │  ...                                                                    │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  When complete:                                [Approve & Continue to Photos]   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Story Detail Modal

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  The Phantom Time Hypothesis                                              [×]   │
│  HISTORY • Brand: 82 • Viral: 91                                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Tabs: [Lead] [Research] [Text] [Photos] [Thumbnails]                           │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  Research Data                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  Ground Truth:                                                           │    │
│  │  The Phantom Time Hypothesis, proposed by Heribert Illig in 1991,       │    │
│  │  suggests that 297 years of early medieval history (AD 614-911)         │    │
│  │  were fabricated by the Holy Roman Emperor Otto III...                  │    │
│  │                                                                          │    │
│  │  Hook Identified:                                                        │    │
│  │  "What if nearly 300 years of history never happened? One German        │    │
│  │  historian found evidence that Charlemagne might be fictional..."       │    │
│  │                                                                          │    │
│  │  Primary Sources:                                                        │    │
│  │  • Illig, Heribert. "Das erfundene Mittelalter" (1996)                  │    │
│  │  • Niemitz, Hans-Ulrich. "Did the Early Middle Ages Really Exist?"      │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Error State Display

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ⚠️ Phase Failed: Photo Research                                                │
│                                                                                  │
│  Error: Google Custom Search API rate limit exceeded                            │
│                                                                                  │
│  Failed Stories (3):                                                            │
│  • The Taos Hum Mystery — API timeout                                          │
│  • The Dancing Plague — Rate limit                                             │
│  • The Dyatlov Pass — Rate limit                                               │
│                                                                                  │
│  Options:                                                                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐              │
│  │  Retry Failed    │  │  Skip These      │  │  Cancel Pipeline │              │
│  │  (3 stories)     │  │  Stories         │  │                  │              │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘              │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Error Handling Strategy

### Error Categories

1. **Recoverable Errors** (auto-retry with backoff)
   - Network timeouts
   - API rate limits
   - Temporary service unavailability

2. **Story-Level Errors** (isolate and continue)
   - Individual story processing failure
   - Invalid research data
   - No photos found

3. **Phase-Level Errors** (pause pipeline)
   - API key invalid
   - Database connection lost
   - Critical dependency failure

4. **System Errors** (halt and alert)
   - Out of memory
   - Disk full
   - Catastrophic failure

### Error Display

Each error is logged with:
- Timestamp
- Phase and sub-step
- Story ID (if applicable)
- Error message
- Stack trace (collapsible)
- Retry count

### Retry Logic

```python
@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0
    exponential_base: float = 2.0

async def with_retry(func, config: RetryConfig):
    for attempt in range(config.max_retries):
        try:
            return await func()
        except RecoverableError as e:
            if attempt == config.max_retries - 1:
                raise
            delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay
            )
            await asyncio.sleep(delay)
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

- [ ] Create `pipeline_manager/` module structure
- [ ] Set up FastAPI app with CORS and static files
- [ ] Implement database schema additions
- [ ] Create Pydantic models for all entities
- [ ] Build basic API endpoints (CRUD for pipeline runs)
- [ ] Implement SSE streaming infrastructure

### Phase 2: Worker Adapters (Week 2)

- [ ] Lead Generator adapter (wrap `lead_generator/logic/workflow.py`)
- [ ] Curator adapter (wrap `curator/logic.py`)
- [ ] Story Researcher adapter (wrap `story_researcher/researcher.py`)
- [ ] Text Generator adapter (wrap `text_generator/generator.py`)
- [ ] Photo Researcher adapter (wrap `photo_researcher/` modules)
- [ ] Thumbnail Generator adapter (wrap `thumbnail_generator/` modules)

### Phase 3: Pipeline Executor (Week 3)

- [ ] Pipeline orchestration logic (auto mode)
- [ ] Phase execution with progress callbacks
- [ ] Error handling and retry logic
- [ ] Pause/resume/cancel functionality
- [ ] Step mode with approval gates

### Phase 4: Dashboard UI (Week 4)

- [ ] Main dashboard (`index.html`)
- [ ] Mode selection cards
- [ ] Recent runs list
- [ ] Navigation to Pre-Assembler

### Phase 5: Pipeline UI (Week 5)

- [ ] Pipeline view (`pipeline.html`)
- [ ] Phase progress stepper
- [ ] Story cards with status
- [ ] Real-time progress updates via SSE
- [ ] Error state displays

### Phase 6: Detail Views & Polish (Week 6)

- [ ] Story detail modal with tabbed content
- [ ] Phase-specific result previews
- [ ] Thumbnail preview grid
- [ ] Photo gallery preview
- [ ] Final testing and bug fixes

---

## Integration with Pre-Assembler

### Navigation

Add link from Pipeline Manager → Pre-Assembler:
```html
<a href="http://localhost:8000" class="btn-secondary">
    Open Pre-Assembler →
</a>
```

Add link from Pre-Assembler → Pipeline Manager:
```html
<a href="http://localhost:8001" class="btn-secondary">
    ← Pipeline Manager
</a>
```

### Shared Styling

Import the same CSS variables and component styles to ensure visual consistency:

```html
<!-- Both apps use the same base styles -->
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    :root {
        --bg-primary: #FFFFFF;
        --bg-secondary: #F5F5F7;
        /* ... identical to pre_assembler ... */
    }
</style>
```

### Status Handoff

When a pipeline run completes, stories are ready in the database for Pre-Assembler:
- `story_generations` with slides
- `story_photos` with placements
- `story_thumbnails` with generated images

The Pre-Assembler's `/api/stories` endpoint automatically picks up these new stories.

---

## Configuration

### Environment Variables

```env
# Pipeline Manager
PIPELINE_MANAGER_PORT=8001
PIPELINE_MANAGER_HOST=0.0.0.0

# Execution Limits
MAX_STORIES_PER_RUN=20
CONCURRENT_WORKERS=3
PHASE_TIMEOUT_SECONDS=1800

# Retry Configuration
MAX_RETRIES=3
RETRY_BASE_DELAY=2.0
RETRY_MAX_DELAY=60.0

# Pre-Assembler URL (for navigation)
PRE_ASSEMBLER_URL=http://localhost:8000
```

### Runtime Configuration

```python
# config.py
from pydantic_settings import BaseSettings

class PipelineConfig(BaseSettings):
    port: int = 8001
    host: str = "0.0.0.0"
    max_stories_per_run: int = 20
    concurrent_workers: int = 3
    phase_timeout: int = 1800
    
    # Phase-specific settings
    lead_gen_rss_enabled: bool = True
    lead_gen_perplexity_enabled: bool = True
    curation_min_candidates: int = 5
    
    class Config:
        env_prefix = "PIPELINE_"
```

---

## Testing Strategy

### Unit Tests

- Worker adapter isolation tests
- Error handling tests
- Retry logic tests
- Database operation tests

### Integration Tests

- Full pipeline run (mock external APIs)
- Phase transition tests
- Error recovery tests
- SSE streaming tests

### E2E Tests

- Dashboard navigation
- Start pipeline flow
- Real-time progress updates
- Error display and retry

---

## Future Enhancements

1. **Scheduling:** Cron-based automatic pipeline runs
2. **Notifications:** Slack/Discord alerts on completion/failure
3. **Analytics:** Processing time trends, error rates
4. **Batch Config:** Custom filters and limits per run
5. **History Comparison:** Compare results across runs
6. **Parallel Execution:** Run multiple phases in parallel where possible
7. **Custom Prompts:** Override prompts for specific stories
8. **A/B Testing:** Compare different prompt variations

---

## File Locations

```
code/
├── pipeline_manager/           # NEW - This module
│   ├── PLAN.md                # This file
│   ├── main.py                # FastAPI app
│   ├── config.py
│   ├── models.py
│   ├── db.py
│   ├── executor.py
│   ├── workers/
│   ├── static/
│   └── requirements.txt
│
├── pre_assembler/             # EXISTING - Add navigation link
│   └── static/
│       └── index.html         # Add "← Pipeline Manager" link
│
├── lead_generator/            # EXISTING - Wrap in adapter
├── curator/                   # EXISTING - Wrap in adapter
├── story_researcher/          # EXISTING - Wrap in adapter
├── text_generator/            # EXISTING - Wrap in adapter
├── photo_researcher/          # EXISTING - Wrap in adapter
└── thumbnail_generator/       # EXISTING - Wrap in adapter
```

---

## Running the Pipeline Manager

```bash
# Development
cd code/pipeline_manager
uvicorn main:app --reload --port 8001

# Production (alongside Pre-Assembler)
# Terminal 1: Pre-Assembler
cd code/pre_assembler
uvicorn main:app --port 8000

# Terminal 2: Pipeline Manager
cd code/pipeline_manager
uvicorn main:app --port 8001
```

Access:
- Pipeline Manager: http://localhost:8001
- Pre-Assembler: http://localhost:8000

