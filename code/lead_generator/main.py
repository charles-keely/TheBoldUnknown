import typer
from logic.workflow import workflow
from database import db
from utils.logger import logger
from config import config
from services.llm import llm

app = typer.Typer()

@app.command()
def run(source: str = typer.Option("all", help="Source to run: 'rss', 'perplexity', or 'all'")):
    """
    Runs the lead generation workflow.
    """
    try:
        config.validate()
        logger.info(f"Configuration valid. Starting workflow with source={source}")
        workflow.run(source=source)
    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        # raise # Uncomment to see full traceback in dev

@app.command()
def stats():
    """
    Shows basic stats about the system.
    """
    typer.echo("Stats feature coming soon.")

@app.command()
def test_connection():
    """
    Tests database connection.
    """
    try:
        with db.get_cursor() as cur:
            cur.execute("SELECT 1")
            typer.echo("Database connection successful.")
    except Exception as e:
        typer.echo(f"Database connection failed: {e}")


@app.command()
def sync_story_memory(
    limit: int = typer.Option(200, help="Max rows per source to embed+upsert this run."),
    include_leads: bool = typer.Option(True, help="Index raw leads (source_type='lead')."),
    include_story_generations: bool = typer.Option(True, help="Index story_generations (source_type='story_generation')."),
    include_finalized_assemblies: bool = typer.Option(True, help="Index finalized assemblies (source_type='story_assembly')."),
    include_published_posts: bool = typer.Option(True, help="Index published scheduled_posts (source_type='scheduled_post')."),
):
    """
    Backfill/sync the durable semantic dedupe index (`story_memory`) from:
    - leads
    - pre-assembled stories (finalized story_assemblies)
    - posted stories (published scheduled_posts)

    This requires OpenAI embeddings (network) and a working DB connection.
    """
    try:
        config.validate()
    except Exception as e:
        typer.echo(f"Config invalid: {e}")
        raise typer.Exit(code=2)

    limit = int(limit)
    if limit <= 0:
        typer.echo("limit must be > 0")
        raise typer.Exit(code=2)

    total = 0

    def _embed_and_upsert(*, source_type: str, source_id: str, lead_id: str | None, title: str | None, summary: str | None, url: str | None):
        nonlocal total
        text = db._build_dedupe_text(title=title, summary=summary, url=url)
        if not text.strip():
            return
        emb = llm.get_embedding(text)
        if not emb:
            return
        db.upsert_story_memory_item(
            source_type=source_type,
            source_id=source_id,
            lead_id=lead_id,
            title=title,
            summary=summary,
            url=url,
            embedding=emb,
        )
        total += 1

    if include_leads:
        rows = db.fetch_leads_missing_story_memory(limit=limit)
        typer.echo(f"Leads missing story_memory: {len(rows)}")
        for r in rows:
            _embed_and_upsert(
                source_type="lead",
                source_id=str(r["lead_id"]),
                lead_id=str(r["lead_id"]),
                title=r.get("title"),
                summary=r.get("summary"),
                url=r.get("url"),
            )

    if include_story_generations:
        rows = db.fetch_story_generations_missing_story_memory(limit=limit)
        typer.echo(f"Story generations missing story_memory: {len(rows)}")
        for r in rows:
            _embed_and_upsert(
                source_type="story_generation",
                source_id=str(r["story_generation_id"]),
                lead_id=str(r.get("lead_id")) if r.get("lead_id") else None,
                title=r.get("title"),
                summary=r.get("summary"),
                url=r.get("url"),
            )

    if include_finalized_assemblies:
        rows = db.fetch_finalized_assemblies_missing_story_memory(limit=limit)
        typer.echo(f"Finalized assemblies missing story_memory: {len(rows)}")
        for r in rows:
            _embed_and_upsert(
                source_type="story_assembly",
                source_id=str(r["assembly_id"]),
                lead_id=str(r.get("lead_id")) if r.get("lead_id") else None,
                title=r.get("title"),
                summary=r.get("summary"),
                url=r.get("url"),
            )

    if include_published_posts:
        rows = db.fetch_published_posts_missing_story_memory(limit=limit)
        typer.echo(f"Published posts missing story_memory: {len(rows)}")
        for r in rows:
            _embed_and_upsert(
                source_type="scheduled_post",
                source_id=str(r["post_id"]),
                lead_id=str(r.get("lead_id")) if r.get("lead_id") else None,
                title=r.get("title"),
                summary=r.get("summary"),
                url=r.get("url"),
            )

    typer.echo(f"Done. Upserted {total} story_memory rows.")

if __name__ == "__main__":
    app()
