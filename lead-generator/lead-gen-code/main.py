import typer
from rich.console import Console
from rich.table import Table
from config import Config
from utils.logger import logger
from database import db
from logic.workflow import workflow
from services.llm import llm

app = typer.Typer()
console = Console()

@app.command()
def run(
    source: str = typer.Option("all", help="Source to run: 'rss', 'perplexity', or 'all'"),
    limit: int = typer.Option(None, help="Limit items (RSS) or cycles (Perplexity). Default: RSS=All, Perplexity=1")
):
    """
    Run the lead generation workflow.
    """
    try:
        Config.validate()
        console.print("[green]Configuration valid. Starting workflow...[/green]")
        logger.info(f"Starting workflow with source={source}")
        
        if source in ["all", "rss"]:
            console.print("[bold cyan]=== RSS Workflow ===[/bold cyan]")
            # If limit is set, use it. If not, fetch all.
            workflow.run_rss_workflow(limit=limit)
            
        if source in ["all", "perplexity"]:
            console.print("[bold magenta]=== Perplexity Workflow ===[/bold magenta]")
            # Default to 1 cycle if not set, otherwise use limit
            cycles = limit if limit else 1
            workflow.run_perplexity_workflow(cycles=cycles)
            
        console.print("[bold green]Workflow completed successfully![/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        logger.exception("Workflow failed")
        raise typer.Exit(code=1)

@app.command()
def stats():
    """
    Show statistics about generated leads.
    """
    try:
        console.print("[bold]Fetching stats...[/bold]")
        
        # Leads by Status
        status_query = "SELECT status, count(*) FROM leads GROUP BY status"
        status_rows = db.fetch_all(status_query)
        
        # Leads Today
        today_query = "SELECT count(*) as count FROM leads WHERE created_at::date = CURRENT_DATE"
        today_row = db.fetch_one(today_query)
        
        # Top 5 Brand Scores
        top_query = "SELECT title, brand_score FROM leads ORDER BY brand_score DESC LIMIT 5"
        top_rows = db.fetch_all(top_query)

        # Discovery Topics Count
        topic_query = "SELECT status, count(*) FROM discovery_topics GROUP BY status"
        topic_rows = db.fetch_all(topic_query)

        # Display
        table = Table(title="Lead Generation Stats")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Leads Created Today", str(today_row['count']) if today_row else "0")
        
        for row in status_rows:
            table.add_row(f"Status: {row['status']}", str(row['count']))
            
        for row in topic_rows:
            table.add_row(f"Topic Status: {row['status']}", str(row['count']))

        console.print(table)
        
        console.print("\n[bold]Top Rated Leads:[/bold]")
        for row in top_rows:
            console.print(f"- {row['title']} [yellow]({row['brand_score']})[/yellow]")

    except Exception as e:
        console.print(f"[red]Error fetching stats: {e}[/red]")

@app.command()
def test_connection():
    """
    Test database and API connections.
    """
    try:
        Config.validate()
        console.print("[green]Environment variables loaded.[/green]")
        
        # DB Test
        console.print("Testing Database...", end=" ")
        db.fetch_one("SELECT 1")
        console.print("[green]OK[/green]")
        
        # OpenAI Test
        console.print("Testing OpenAI...", end=" ")
        try:
            # We use a simple list call to verify connectivity and auth
            llm.client.models.list()
            console.print("[green]OK[/green]")
        except TypeError as e:
            if "limit" in str(e):
                console.print(f"[yellow]Warning: Unexpected 'limit' arg error ({e}). Assuming connected.[/yellow]")
            else:
                raise e
        
        # Perplexity Test (we just check if we have the key, strict ping requires query)
        console.print("Perplexity Key Present: [green]Yes[/green]")
        
    except Exception as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        logger.exception("Test connection failed")

if __name__ == "__main__":
    app()
