# TheBoldUnknown Scheduler Worker

A Cloudflare Worker that automatically publishes Instagram posts at scheduled times.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Scheduler UI   │────▶│  Supabase DB     │◀────│  CF Worker      │
│  (Python/FastAPI)│     │  (scheduled_posts)│     │  (cron: 1min)   │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  Instagram API  │
                                                 └─────────────────┘
```

## Features

- **Cron-triggered**: Runs every minute to check for due posts
- **Auto token refresh**: Refreshes Instagram tokens before they expire
- **Retry logic**: Failed posts are retried up to 3 times
- **Graceful failures**: Posts move to "failed" status after max retries

## Setup

### 1. Install Dependencies

```bash
cd scheduler/worker
npm install
```

### 2. Install Wrangler CLI

```bash
npm install -g wrangler
```

### 3. Login to Cloudflare

```bash
wrangler login
```

This will open a browser for OAuth authentication.

### 4. Set Secrets

Set your environment secrets (these are encrypted and not stored in code):

```bash
# Supabase credentials
wrangler secret put SUPABASE_URL
# Enter your Supabase project URL when prompted

wrangler secret put SUPABASE_SERVICE_ROLE_KEY
# Enter your Supabase service role key when prompted

# Instagram credentials
wrangler secret put IG_USER_ID
# Enter your Instagram Business Account ID

# Meta App credentials (for token refresh)
wrangler secret put META_APP_ID
# Enter your Meta App ID

wrangler secret put META_APP_SECRET
# Enter your Meta App Secret
```

### 5. Deploy

```bash
npm run deploy
```

## Development

### Local Development

```bash
npm run dev
```

This starts a local server at `http://localhost:8787`.

### Test Endpoints

- `GET /health` - Health check
- `POST /trigger` - Manually trigger processing (requires auth header)
- `GET /token/check` - Check token validity

### View Logs

```bash
npm run tail
```

This streams real-time logs from the deployed worker.

## Configuration

Edit `wrangler.toml` to change:

- `GRAPH_API_VERSION` - Instagram Graph API version (default: v19.0)
- `TOKEN_REFRESH_WINDOW_DAYS` - Days before expiry to refresh token (default: 7)
- `MAX_RETRY_COUNT` - Max retries before marking as failed (default: 3)
- `TIMEZONE` - Timezone for logging (default: America/Denver)

## Important Notes

### Rendering Limitation

Cloudflare Workers cannot render HTML to images (no browser/Playwright).

**Current behavior**: The worker looks for pre-rendered slide URLs in the assembly data.

**Recommended workflow**:
1. When a schedule is approved, trigger rendering in the Python API
2. Store rendered slide URLs in `assembly_data.rendered_slides`
3. Worker reads these URLs and publishes to Instagram

### Token Management

Instagram tokens expire after 60 days. The worker:
1. Checks token expiry before each publish
2. Auto-refreshes if within 7 days of expiry
3. Saves new token to `ig_access_tokens` table

If auto-refresh fails:
1. Check Meta App credentials
2. Generate a new token manually
3. Insert into `ig_access_tokens` table

## Troubleshooting

### "No pre-rendered slides found"

Slides need to be rendered before the worker can publish. Either:
1. Add a render step to the approval flow
2. Manually render via the Python API

### "Token validation failed"

The Instagram token is invalid. Try:
1. Check token in `ig_access_tokens` table
2. Generate a new token from Meta Business Suite
3. Insert new token into database

### "Carousel requires at least 2 slides"

Instagram carousels need 2-10 images. Check:
1. The assembly has visible slides
2. Slide URLs are public and accessible

## Database Tables Used

- `scheduled_posts` - Queue of posts with status tracking
- `ig_access_tokens` - Instagram access tokens
- `story_assemblies` - Assembly data with rendered slide URLs
- `story_generations` - Caption and hashtag data


