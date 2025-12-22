import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import json
import re
from urllib.parse import urlparse
from .config import config

class Database:
    def __init__(self):
        # Ensure schema init / migrations don't get killed by low server defaults.
        # Other modules use POSTGRES_STATEMENT_TIMEOUT_MS; mirror that here.
        statement_timeout_ms = int(os.getenv("POSTGRES_STATEMENT_TIMEOUT_MS", "120000"))
        self.conn = psycopg2.connect(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            dbname=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
            options=f"-c statement_timeout={statement_timeout_ms}",
        )
        self.conn.autocommit = True
        self._init_tables()

    def _init_tables(self):
        with self.conn.cursor() as cur:
            # Create story_photos table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS story_photos (
                    id uuid NOT NULL DEFAULT gen_random_uuid(),
                    story_research_id uuid NOT NULL,
                    image_url text NOT NULL,
                    source_page_url text,
                    search_query text,
                    description text,
                    caption text,
                    source_attribution text,
                    concept_tag text,
                    text_generated_at timestamp with time zone,
                    pipeline_run_id uuid,
                    relevance_score integer CHECK (relevance_score >= 0 AND relevance_score <= 10),
                    verifiability_score integer CHECK (verifiability_score >= 0 AND verifiability_score <= 10),
                    status text DEFAULT 'potential' CHECK (status = ANY (ARRAY['potential', 'approved', 'rejected'])),
                    metadata jsonb DEFAULT '{}',
                    created_at timestamp with time zone DEFAULT now(),
                    CONSTRAINT story_photos_pkey PRIMARY KEY (id),
                    CONSTRAINT story_photos_story_research_id_fkey FOREIGN KEY (story_research_id) REFERENCES story_research(id)
                );
            """)

            # Ensure newer columns exist even if the table was created by an older version.
            # This is safe on Postgres and prevents silent "caption/source not persisted" issues.
            #
            # NOTE: On some hosted Postgres setups (or during concurrent access), these ALTERs can
            # briefly block on locks and hit a low statement_timeout. Since they're defensive
            # (and in production the columns should already exist), treat timeouts as warnings.
            def _safe_alter(sql: str) -> None:
                try:
                    # Fail fast on DDL lock contention; these are best-effort backfills.
                    # With autocommit=True, SET LOCAL won't apply, so we SET then RESET.
                    cur.execute("SET lock_timeout = '2s';")
                    cur.execute("SET statement_timeout = '2000ms';")
                    cur.execute(sql)
                except psycopg2.errors.QueryCanceled as e:
                    print(f"[warn] schema alter timed out; continuing: {sql} ({e})")
                except psycopg2.errors.LockNotAvailable as e:
                    print(f"[warn] schema alter lock timeout; continuing: {sql} ({e})")
                finally:
                    try:
                        cur.execute("RESET lock_timeout;")
                        cur.execute("RESET statement_timeout;")
                    except Exception:
                        pass

            _safe_alter("ALTER TABLE story_photos ADD COLUMN IF NOT EXISTS caption text;")
            _safe_alter("ALTER TABLE story_photos ADD COLUMN IF NOT EXISTS source_attribution text;")
            _safe_alter("ALTER TABLE story_photos ADD COLUMN IF NOT EXISTS concept_tag text;")
            _safe_alter("ALTER TABLE story_photos ADD COLUMN IF NOT EXISTS text_generated_at timestamp with time zone;")
            _safe_alter("ALTER TABLE story_photos ADD COLUMN IF NOT EXISTS pipeline_run_id uuid;")

    def _normalize_caption(self, text: str) -> str:
        t = re.sub(r"\s+", " ", (text or "").strip())
        if not t:
            return ""
        # Keep captions reasonably short for the photo template UI.
        if len(t) > 200:
            return t[:197].rstrip() + "..."
        return t

    def _infer_source_attribution(self, image_data: dict) -> str:
        # Prefer explicit fields when present.
        explicit = (image_data.get("source_attribution") or "").strip()
        if explicit:
            return explicit

        meta = image_data.get("metadata") if isinstance(image_data.get("metadata"), dict) else {}
        source_title = (meta.get("source_title") or "").strip()
        if source_title:
            # Avoid extremely long titles in the footer.
            return source_title[:80].rstrip()

        sp = (image_data.get("source_page_url") or "").strip()
        if sp:
            try:
                host = (urlparse(sp).netloc or "").lower()
                host = host[4:] if host.startswith("www.") else host
                return host
            except Exception:
                return ""
        return ""

    def fetch_stories_needing_photos(self, limit=5):
        """
        Finds completed stories that already have text generation (story_generations + story_slides),
        and either:
        - don't have enough approved photos yet, OR
        - don't have photo placement computed for the latest generation.
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                WITH latest_gen AS (
                    SELECT DISTINCT ON (sr.id)
                        sr.id as story_research_id,
                        sr.research_data,
                        l.title,
                        l.url as original_url,
                        sg.id as story_generation_id,
                        sg.created_at as generation_created_at
                    FROM story_research sr
                    JOIN leads l ON sr.lead_id = l.id
                    JOIN story_generations sg ON sg.story_research_id = sr.id
                    WHERE sr.status = 'completed'
                    ORDER BY sr.id, sg.created_at DESC
                ),
                gen_with_slides AS (
                    SELECT
                        lg.*,
                        json_agg(
                            json_build_object(
                                'id', ss.id,
                                'slide_order', ss.slide_order,
                                'text_content', ss.text_content
                            )
                            ORDER BY ss.slide_order
                        ) as slides
                    FROM latest_gen lg
                    JOIN story_slides ss ON ss.story_generation_id = lg.story_generation_id
                    GROUP BY
                        lg.story_research_id,
                        lg.research_data,
                        lg.title,
                        lg.original_url,
                        lg.story_generation_id,
                        lg.generation_created_at
                )
                SELECT *
                FROM gen_with_slides gws
                WHERE
                    -- Needs more approved photos (tunable threshold)
                    (
                        SELECT count(*)
                        FROM story_photos sp
                        WHERE sp.story_research_id = gws.story_research_id
                          AND sp.status = 'approved'
                    ) < 2
                    OR
                    -- OR: photos exist but placement hasn't been computed for this generation yet
                    NOT EXISTS (
                        SELECT 1
                        FROM story_photos sp
                        WHERE sp.story_research_id = gws.story_research_id
                          AND (sp.metadata->'placement'->>'generation_id') = (gws.story_generation_id::text)
                    )
                ORDER BY random()
                LIMIT %s;
            """, (limit,))
            return cur.fetchall()

    def save_photo_candidate(self, story_id, image_data):
        with self.conn.cursor() as cur:
            # Pre-assembler expects story_photos.caption + story_photos.source_attribution.
            # Older versions only stored `description`, which caused blank captions in new stories.
            caption = self._normalize_caption(
                (image_data.get("caption") or "").strip()
                or (image_data.get("description") or "").strip()
                or (image_data.get("title") or "").strip()
            )
            source_attribution = self._infer_source_attribution(image_data)
            concept_tag = (image_data.get("concept_tag") or "").strip() or None
            text_generated_at = "NOW()" if caption else "NULL"

            cur.execute("""
                INSERT INTO story_photos 
                (story_research_id, image_url, source_page_url, search_query, description, caption, source_attribution, concept_tag, relevance_score, verifiability_score, metadata, status, text_generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, """ + text_generated_at + """)
                RETURNING id;
            """, (
                story_id,
                image_data.get('image_url'),
                image_data.get('source_page_url'),
                image_data.get('search_query'),
                image_data.get('description'),
                caption,
                source_attribution,
                concept_tag,
                image_data.get('relevance_score'),
                image_data.get('verifiability_score'),
                Json(image_data.get('metadata', {})),
                image_data.get('status', 'potential')
            ))
            return cur.fetchone()[0]

    def fetch_approved_photos(self, story_research_id: str):
        """
        Fetch approved photos with enough metadata for placement.
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    image_url,
                    source_page_url,
                    search_query,
                    description,
                    caption,
                    source_attribution,
                    concept_tag,
                    relevance_score,
                    verifiability_score,
                    metadata,
                    created_at
                FROM story_photos
                WHERE story_research_id = %s
                  AND status = 'approved'
                ORDER BY created_at ASC
                """,
                (story_research_id,),
            )
            return cur.fetchall()

    def apply_photo_placements(self, *, story_generation_id: str, placements: list[dict]):
        """
        Persist placement decisions into story_photos.metadata under the "placement" key.
        """
        if not placements:
            return
        with self.conn.cursor() as cur:
            for p in placements:
                photo_id = str(p.get("photo_id") or "").strip()
                if not photo_id:
                    continue
                placement_obj = {
                    "generation_id": str(story_generation_id),
                    "after_slide_order": int(p.get("after_slide_order", 0) or 0),
                    "enabled": bool(p.get("enabled", False)),
                    "reason": (p.get("reason") or "").strip(),
                    "model": getattr(config, "PLACER_MODEL", None) or config.QUERY_GENERATOR_MODEL,
                }
                cur.execute(
                    """
                    UPDATE story_photos
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s::uuid
                    """,
                    (json.dumps({"placement": placement_obj}), photo_id),
                )

    def close(self):
        self.conn.close()
