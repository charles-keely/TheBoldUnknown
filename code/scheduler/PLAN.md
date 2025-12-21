# Scheduler System Plan

## Overview

The scheduler system has two main components:
1. **Web UI** — A scheduling interface accessible from the pre-assembler for managing post times, reordering, and approving schedules
2. **Cloudflare Worker** — An automated cron system that publishes posts at their scheduled times

---

## Part 1: Database Schema

### New Table: `scheduled_posts`

```sql
CREATE TABLE scheduled_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_generation_id UUID NOT NULL REFERENCES story_generations(id) ON DELETE CASCADE,
    assembly_id UUID REFERENCES story_assemblies(id) ON DELETE SET NULL,
    
    -- Scheduling
    scheduled_at TIMESTAMPTZ NOT NULL,          -- When to post (MST times stored as UTC)
    position INTEGER NOT NULL DEFAULT 0,         -- Order in the schedule queue
    
    -- Status tracking
    status TEXT NOT NULL DEFAULT 'scheduled',    -- scheduled | approved | publishing | published | failed
    approved_at TIMESTAMPTZ,                     -- When schedule was approved for auto-posting
    
    -- Publishing results
    published_at TIMESTAMPTZ,                    -- When actually published
    instagram_media_id TEXT,                     -- IG media ID after successful publish
    error_message TEXT,                          -- Error details if failed
    retry_count INTEGER DEFAULT 0,               -- Number of retry attempts
    
    -- Future analytics (Phase 2)
    saves_count INTEGER,
    impressions_count INTEGER,
    profile_visits_count INTEGER,
    carousel_completion_rate DECIMAL(5,4),
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_scheduled_posts_scheduled_at ON scheduled_posts(scheduled_at);
CREATE INDEX idx_scheduled_posts_status ON scheduled_posts(status);
CREATE INDEX idx_scheduled_posts_story_generation_id ON scheduled_posts(story_generation_id);
CREATE UNIQUE INDEX idx_scheduled_posts_story_unique ON scheduled_posts(story_generation_id) 
    WHERE status NOT IN ('published', 'failed');  -- Only one active schedule per story
```

### New Table: `schedule_approvals` (Audit Log)

```sql
CREATE TABLE schedule_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    approved_at TIMESTAMPTZ DEFAULT NOW(),
    posts_approved INTEGER NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Updated Table: `ig_access_tokens` (Centralized Token Storage)

```sql
CREATE TABLE ig_access_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    access_token TEXT NOT NULL,
    token_type TEXT DEFAULT 'bearer',
    expires_at TIMESTAMPTZ NOT NULL,
    obtained_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    refresh_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Only one active token at a time
CREATE UNIQUE INDEX idx_ig_access_tokens_active ON ig_access_tokens(is_active) WHERE is_active = TRUE;
```

---

## Part 2: Backend API Design

### File Structure

```
scheduler/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app (like pre_assembler)
│   ├── routes/
│   │   ├── schedule.py      # Schedule CRUD endpoints
│   │   ├── tokens.py        # Token management endpoints
│   │   └── health.py        # Health checks
│   ├── db.py                # Database operations
│   └── models.py            # Pydantic models
├── worker/                  # Cloudflare Worker code
│   ├── src/
│   │   ├── index.ts         # Worker entry point
│   │   ├── publisher.ts     # Instagram publishing logic
│   │   ├── token-manager.ts # Token refresh logic
│   │   └── db.ts           # Supabase client
│   ├── wrangler.toml
│   └── package.json
├── static/
│   ├── schedule.html        # Schedule UI page
│   ├── css/
│   │   └── schedule.css     # Apple-style styles
│   └── js/
│       └── schedule.js      # Alpine.js logic
└── ... (existing files)
```

### API Endpoints

#### Schedule Management

```
GET  /api/schedule
     → Returns all scheduled posts ordered by scheduled_at
     → Response: { posts: [...], count: number }

POST /api/schedule/sync
     → Finds newly approved posts and adds them to the schedule
     → Assigns next available time slots (8:30 AM, 1:00 PM, 7:00 PM MST)
     → Response: { added: number, schedule: [...] }

PATCH /api/schedule/{post_id}
     → Update scheduled time or position
     → Body: { scheduled_at?: string, position?: number }
     → Response: { post: {...} }

DELETE /api/schedule/{post_id}
     → Remove post from schedule
     → Response: { success: true }

POST /api/schedule/{post_id}/move
     → Reorder post in schedule
     → Body: { new_position: number }
     → Response: { schedule: [...] }

POST /api/schedule/approve
     → Approve the current schedule for auto-posting
     → Sets status='approved' and approved_at=NOW() for all 'scheduled' posts
     → Response: { approved_count: number }
```

#### Token Management

```
GET  /api/tokens/status
     → Returns token expiry info and health
     → Response: { expires_at: string, is_healthy: boolean, days_until_expiry: number }

POST /api/tokens/refresh
     → Manually trigger token refresh
     → Response: { success: boolean, new_expires_at: string }
```

#### Post Preview

```
GET  /api/schedule/{post_id}/preview
     → Returns rendered carousel preview data
     → Response: { slides: [...], caption: string, hashtags: [...] }
```

---

## Part 3: Web UI Design

### Navigation Integration

Add a "Schedule" link to the pre_assembler dashboard header:

```html
<header class="mb-12">
  <div class="flex items-center justify-between">
    <div>
      <h1 class="text-4xl font-bold tracking-tight text-gray-900">Pre-Assembler</h1>
      <p class="mt-2 text-lg text-gray-500">Assemble and preview Instagram carousel stories</p>
    </div>
    <div class="flex items-center gap-4">
      <a href="/schedule" class="btn-secondary">
        <svg class="w-5 h-5 mr-2"><!-- calendar icon --></svg>
        View Schedule
      </a>
      <!-- existing refresh button -->
    </div>
  </div>
</header>
```

### Schedule Page Layout

```
┌──────────────────────────────────────────────────────────────┐
│  Header: "Post Schedule" + Approve Button + Token Status     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Today (Saturday, Dec 20)                                    │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ ☰  8:30 AM  │ [Thumbnail] Title of Story...  │ ✓ Posted │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ ☰  1:00 PM  │ [Thumbnail] Another Story...   │ ⏳ Pending│  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ ☰  7:00 PM  │ [Thumbnail] Third Story...     │ ⏳ Pending│  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Tomorrow (Sunday, Dec 21)                                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ ☰  8:30 AM  │ [Thumbnail] Fourth Story...    │ ⏳ Pending│  │
│  └────────────────────────────────────────────────────────┘  │
│  ...                                                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### UI Features

#### 1. Drag-and-Drop Reordering
- Use SortableJS for drag-and-drop
- Drag handle (☰) on the left of each item
- Smooth animations during drag
- API call on drop to update positions

#### 2. Time Editing
- Click on time to show inline time picker
- Validate against other scheduled times (no conflicts)
- Show timezone indicator (MST)

#### 3. Status Indicators
- ⏳ **Scheduled** — Gray, waiting for approval
- ✅ **Approved** — Blue, ready for auto-posting
- 🔄 **Publishing** — Yellow, currently being posted
- ✓ **Published** — Green, successfully posted
- ❌ **Failed** — Red, with error tooltip

#### 4. Post Card Actions
- **Delete** — Remove from schedule (with confirmation)
- **Edit Time** — Change scheduled time
- **View Preview** — See carousel preview in modal

#### 5. Approve Schedule Button
- Prominent button in header
- Shows count: "Approve 15 Posts"
- Confirmation modal with schedule summary
- Disabled if no pending posts

### Apple Aesthetic Guidelines

Following the existing pre_assembler style:

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
  --shadow: rgba(0, 0, 0, 0.08);
}

/* Schedule card style */
.schedule-item {
  background: var(--bg-primary);
  border-radius: 12px;
  box-shadow: 0 2px 8px var(--shadow);
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.schedule-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}

.schedule-item.dragging {
  transform: scale(1.02);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}
```

---

## Part 4: Cloudflare Worker Implementation

### Overview

The Cloudflare Worker runs as a cron job every minute, checking for posts that are due.

### Cron Schedule

```toml
# wrangler.toml
[triggers]
crons = ["* * * * *"]  # Every minute
```

### Worker Logic Flow

```
1. Check for posts where:
   - status = 'approved'
   - scheduled_at <= NOW()
   
2. For each due post:
   a. Set status = 'publishing'
   b. Ensure valid IG token (refresh if needed)
   c. Render carousel images
   d. Upload to Supabase Storage
   e. Create IG carousel
   f. Publish to Instagram
   g. On success: status = 'published', save instagram_media_id
   h. On failure: 
      - If retry_count < 3: increment retry, reschedule +5 min
      - Else: status = 'failed', move to back of queue

3. Token refresh check:
   - If token expires within 7 days, refresh proactively
   - Store new token in ig_access_tokens table
```

### Token Management Strategy

#### The Problem
Meta long-lived tokens expire after 60 days. If the token expires, the system fails.

#### Solution: Proactive Refresh

1. **Store tokens in database** — Not just local JSON files
2. **Proactive refresh** — Refresh when ≤7 days until expiry
3. **Health monitoring** — Expose token status in UI
4. **Alert on failure** — Log errors prominently

```typescript
// token-manager.ts
async function ensureFreshToken(): Promise<string> {
  // 1. Get current token from DB
  const token = await db.getActiveToken();
  
  if (!token) {
    throw new Error('No active IG token found');
  }
  
  // 2. Check if refresh needed (7 days window)
  const daysUntilExpiry = (token.expires_at - Date.now()) / (1000 * 60 * 60 * 24);
  
  if (daysUntilExpiry <= 7) {
    // 3. Exchange for new long-lived token
    const newToken = await exchangeToken(token.access_token);
    
    // 4. Save new token, deactivate old
    await db.saveNewToken(newToken);
    await db.deactivateToken(token.id);
    
    return newToken.access_token;
  }
  
  return token.access_token;
}
```

#### Fallback: Manual Intervention

If auto-refresh fails (e.g., Meta API changes):
1. UI shows prominent warning: "Token refresh failed"
2. Manual refresh endpoint available
3. Instructions to generate new token from Meta Business Suite

---

## Part 5: Default Posting Schedule

### Initial Times (MST)
- **Morning**: 8:30 AM MST (15:30 UTC)
- **Afternoon**: 1:00 PM MST (20:00 UTC)
- **Evening**: 7:00 PM MST (02:00 UTC next day)

### Scheduling Algorithm

```python
def get_next_available_slot(existing_schedule: list[datetime]) -> datetime:
    """
    Find the next available posting slot.
    """
    MST = timezone(timedelta(hours=-7))
    SLOTS = [
        time(8, 30),   # 8:30 AM
        time(13, 0),   # 1:00 PM
        time(19, 0),   # 7:00 PM
    ]
    
    now = datetime.now(MST)
    
    # Start from today
    current_date = now.date()
    
    while True:
        for slot_time in SLOTS:
            candidate = datetime.combine(current_date, slot_time, MST)
            
            # Skip if in the past
            if candidate <= now:
                continue
            
            # Skip if already scheduled
            if candidate in existing_schedule:
                continue
            
            return candidate
        
        # Move to next day
        current_date += timedelta(days=1)
```

---

## Part 6: Failed Post Handling

When a post fails to publish:

1. **Increment retry counter**
2. **Log error details** in `error_message` column
3. **If retry_count < 3**:
   - Reschedule for +5 minutes
   - Keep position in queue
4. **If retry_count >= 3**:
   - Set status = 'failed'
   - Move to back of schedule queue
   - Show prominently in UI with error details

### UI for Failed Posts

```html
<div class="schedule-item status-failed">
  <div class="drag-handle">☰</div>
  <div class="time">7:00 PM</div>
  <div class="thumbnail"><img src="..."></div>
  <div class="title">Story Title</div>
  <div class="status">
    <span class="badge badge-error" title="Error: Rate limit exceeded">
      ❌ Failed (3 retries)
    </span>
    <button class="btn-retry">Retry Now</button>
  </div>
  <button class="btn-delete">×</button>
</div>
```

---

## Part 7: Future Analytics (Phase 2)

After ~30 days of posting, implement:

### Data Collection
- Fetch insights from Instagram Graph API daily
- Store saves, impressions, profile visits, carousel completion

### Time Optimization
```python
def optimize_posting_times():
    """
    Analyze 30 days of data and shift times by ±30 min to find local maxima.
    """
    # 1. Group posts by approximate time slot
    # 2. Calculate engagement rate per slot
    # 3. A/B test by shifting times ±15-30 min
    # 4. Converge on optimal times after sufficient data
```

### Metrics to Track
- **Saves per impression** — Higher = more valuable content
- **Carousel completion rate** — % of users who view all slides
- **Profile visits per post** — Conversion to profile

---

## Implementation Order

### Phase 1: Core Scheduler (Week 1)
1. ☐ Create database schema (migrations)
2. ☐ Build FastAPI backend with schedule endpoints
3. ☐ Create schedule.html with Apple UI
4. ☐ Implement drag-and-drop reordering
5. ☐ Add time editing inline
6. ☐ Implement sync endpoint (add new approved posts)

### Phase 2: Cloudflare Worker (Week 2)
1. ☐ Set up Cloudflare Worker project
2. ☐ Implement token manager with DB storage
3. ☐ Port rendering logic to worker
4. ☐ Implement publishing flow
5. ☐ Add retry/failure handling
6. ☐ Test end-to-end publishing

### Phase 3: Polish (Week 3)
1. ☐ Add post preview modal
2. ☐ Add token health indicator to UI
3. ☐ Add delete confirmation
4. ☐ Add "approve schedule" flow
5. ☐ Add navigation link from pre_assembler
6. ☐ Error handling and edge cases

### Phase 4: Analytics (Month 2+)
1. ☐ Implement daily insights fetching
2. ☐ Store analytics in database
3. ☐ Build time optimization algorithm
4. ☐ Add analytics dashboard

---

## Tech Stack Summary

| Component | Technology |
|-----------|------------|
| Backend API | FastAPI (Python) |
| Frontend | HTML + Tailwind CSS + Alpine.js |
| Database | PostgreSQL (Supabase) |
| Image Storage | Supabase Storage |
| Cron Worker | Cloudflare Workers |
| Drag & Drop | SortableJS |
| Time Picker | Native HTML5 or Flatpickr |

