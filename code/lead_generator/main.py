import typer
from logic.workflow import workflow
from database import db
from utils.logger import logger
from config import config

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

if __name__ == "__main__":
    app()
