import typer
from logic.workflow import workflow
from database import db, get_db_connection
from utils.logger import logger

app = typer.Typer()

@app.command()
def run(source: str = typer.Option("all", help="Source to run: 'rss', 'perplexity', or 'all'")):
    """
    Runs the lead generation workflow.
    """
    workflow.run(source=source)

@app.command()
def stats():
    """
    Shows basic stats about the system.
    """
    # This is a placeholder for stats logic.
    # In a real app, you'd query the DB for counts.
    typer.echo("Stats feature coming soon.")

@app.command()
def test_connection():
    """
    Tests database connection.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                typer.echo("Database connection successful.")
    except Exception as e:
        typer.echo(f"Database connection failed: {e}")

if __name__ == "__main__":
    app()
