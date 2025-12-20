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
# Required env (typical):
# - DATABASE_URL (read access is enough)
# - SUPABASE_URL
# - SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_KEY / SUPABASE_KEY)
# - SUPABASE_STORAGE_BUCKET (optional; default "story-assets")
# - IG_USER_ID
# - IG_ACCESS_TOKEN (or IG_USER_ACCESS_TOKEN / INSTAGRAM_ACCESS_TOKEN)
#


