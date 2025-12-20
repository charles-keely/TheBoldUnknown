# Scheduler (Publisher)
#
# This folder contains a small "publisher" runner meant to:
# - select ONE assembled story from Postgres (read-only)
# - render it to PNG slides (using the existing assembler renderer)
# - upload the PNGs to Supabase Storage (so Instagram can fetch them via public URLs)
# - optionally publish an Instagram carousel via the Graph API
#
# IMPORTANT: This runner is intentionally designed to do **NO database writes**.
# It never marks anything as posted/published.
#
# Usage (from repo root):
#
#   python scheduler/main.py test-post --help
#
# Token management (recommended for unattended posting):
#
# - Put your app creds in env (repo root `.env` is supported):
#     META_APP_ID=...
#     META_APP_SECRET=...
#
# - One-time (or when needed): exchange whatever token you currently have into a long-lived token
#   and store it locally (gitignored):
#     python -m scheduler.main refresh-token
#
# - Then publish using the stored token (no more manual pasting):
#     python -m scheduler.main test-post --approved-only
#
# Notes:
# - You still *cannot* make OAuth tokens literally "never expire", but refreshing a long-lived token
#   periodically (e.g., daily/weekly cron) makes this effectively maintenance-free.
#
# Required env (typical):
# - DATABASE_URL (read access is enough)
# - SUPABASE_URL
# - SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_KEY / SUPABASE_KEY)
# - SUPABASE_STORAGE_BUCKET (optional; default "story-assets")
# - IG_USER_ID
# - IG_ACCESS_TOKEN (or IG_USER_ACCESS_TOKEN / INSTAGRAM_ACCESS_TOKEN) OR use `scheduler/ig_token.json` via refresh-token
#


