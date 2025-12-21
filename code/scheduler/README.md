# Scheduler

Manages and publishes approved story assemblies to Instagram as carousel posts.

## Components

### 1. Web UI (FastAPI)

A scheduling interface for managing the posting queue:
- View all scheduled posts
- Drag-and-drop reordering
- Edit posting times
- Approve schedule for auto-posting
- Monitor token health

**Run the web UI:**
```bash
cd code
source venv/bin/activate
uvicorn scheduler.api:app --host 0.0.0.0 --port 8001 --reload
```

Then visit: http://localhost:8001

### 2. CLI Publisher

The original CLI tool for manual posting and testing.

**Usage (from repo root):**
```bash
python -m scheduler.main test-post --help
```

## Token Management

### Recommended Setup (for unattended posting):

1. Put your app creds in env (repo root `.env` is supported):
   ```
   META_APP_ID=...
   META_APP_SECRET=...
   ```

2. One-time (or when needed): exchange whatever token you currently have into a long-lived token:
   ```bash
   python -m scheduler.main refresh-token
   ```

3. Publish using the stored token (no more manual pasting):
   ```bash
   python -m scheduler.main test-post --approved-only
   ```

**Notes:**
- OAuth tokens cannot literally "never expire", but refreshing a long-lived token periodically makes this effectively maintenance-free
- The Cloudflare worker will auto-refresh tokens within 7 days of expiry

## Required Environment Variables

```
DATABASE_URL (read/write access for scheduler)
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_KEY / SUPABASE_KEY)
SUPABASE_STORAGE_BUCKET (optional; default "story-assets")
IG_USER_ID
IG_ACCESS_TOKEN (or use ig_token.json via refresh-token)
```

## Database Schema

The scheduler uses these tables:
- `scheduled_posts` - Queue of posts with scheduled times and status
- `schedule_approvals` - Audit log of schedule approvals
- `ig_access_tokens` - Centralized token storage

## Workflow

1. **Pre-Assembler**: Mark stories as "approved for assembly"
2. **Scheduler UI**: Click "Sync New Posts" to add approved stories to schedule
3. **Scheduler UI**: Drag-and-drop to reorder, edit times as needed
4. **Scheduler UI**: Click "Approve Schedule" to enable auto-posting
5. **Cloudflare Worker**: Automatically publishes at scheduled times
