import concurrent.futures
from services.rss import fetch_all_rss
from services.perplexity import perplexity_service
from logic.filters import filter_service
from database import db
from models import LeadCandidate, ProcessingStatus
from utils.logger import logger
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID

class WorkflowManager:
    def save_lead(self, lead: LeadCandidate):
        """
        Save the approved lead to the database.
        """
        query = """
        INSERT INTO leads (
            title, url, summary, embedding, brand_score, virality_score, viral_hook, source_origin, status
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id;
        """
        params = (
            lead.title,
            lead.url,
            lead.summary,
            str(lead.embedding), # Store as string for vector type
            lead.brand_score,
            lead.virality_score,
            lead.viral_hook,  # The shareable angle for content creation
            lead.source_origin,
            ProcessingStatus.NEW.value
        )
        row = db.fetch_one(query, params)
        return row['id'] if row else None

    def mark_processed(self, url: str):
        query = "INSERT INTO processed_urls (url) VALUES (%s) ON CONFLICT DO NOTHING"
        db.execute_query(query, (url,))

    def save_discovery_topics(self, topics: list[str], origin_lead_id: str):
        query = "INSERT INTO discovery_topics (topic, origin_lead_id) VALUES (%s, %s) ON CONFLICT (topic) DO NOTHING"
        for topic in topics:
            db.execute_query(query, (topic, origin_lead_id))

    def process_candidate(self, candidate: LeadCandidate) -> bool:
        """
        Run a single candidate through the funnel.
        Returns True if saved, False if filtered/failed.
        """
        try:
            # Stage 1: Dedupe
            if not filter_service.filter_stage_1_dedupe(candidate):
                # Even if rejected, we mark URL as processed to avoid reprocessing same URL
                self.mark_processed(candidate.url) 
                return False

            # Stage 2: Virality
            if not filter_service.filter_stage_2_virality(candidate):
                self.mark_processed(candidate.url)
                return False

            # Stage 3: Brand
            if not filter_service.filter_stage_3_brand(candidate):
                self.mark_processed(candidate.url)
                return False

            # Success! Save it.
            logger.info(f"APPROVED LEAD: {candidate.title} (Brand: {candidate.brand_score})")
            lead_id = self.save_lead(candidate)
            self.mark_processed(candidate.url)
            
            # Fractal Expansion
            if lead_id and candidate.new_topics:
                self.save_discovery_topics(candidate.new_topics, lead_id)
                
            return True

        except Exception as e:
            logger.error(f"Error processing candidate {candidate.url}: {e}")
            return False

    def run_rss_workflow(self, limit: int = None):
        """
        Fetch RSS feeds and process in parallel.
        """
        # If limit is explicitly provided, use it. 
        # If None (default), we'll use a safe default of 3 to prevent accidental huge bills, 
        # unless explicitly asked for '0' (all) which we'd need to handle if we wanted that support.
        # For now, let's map the CLI 'limit' directly to fetch_all_rss.
        # Note: If CLI limit is None, fetch_all_rss uses its default (3).
        # If user provides limit, we pass it.
        candidates = fetch_all_rss(limit_per_feed=limit) if limit is not None else fetch_all_rss()
            
        logger.info(f"Processing {len(candidates)} RSS candidates...")
        
        approved_count = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
        ) as progress:
            task = progress.add_task("[cyan]Filtering RSS...", total=len(candidates))
            
            # Parallel processing
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_candidate = {
                    executor.submit(self.process_candidate, candidate): candidate 
                    for candidate in candidates
                }
                
                for future in concurrent.futures.as_completed(future_to_candidate):
                    try:
                        is_approved = future.result()
                        if is_approved:
                            approved_count += 1
                    except Exception as e:
                        logger.error(f"Error in process future: {e}")
                    finally:
                        progress.advance(task)
                
        logger.info(f"RSS Workflow Complete. Approved: {approved_count}/{len(candidates)}")

    def run_perplexity_workflow(self, cycles: int = 1):
        """
        Run Perplexity discovery cycles.
        """
        logger.info(f"Starting {cycles} Perplexity cycles...")
        
        total_candidates = 0
        approved_count = 0
        
        for i in range(cycles):
            logger.info(f"Cycle {i+1}/{cycles}")
            candidates = perplexity_service.run_cycle()
            total_candidates += len(candidates)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
            ) as progress:
                task = progress.add_task(f"[magenta]Filtering Batch {i+1}...", total=len(candidates))
                
                # Parallel processing
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_candidate = {
                        executor.submit(self.process_candidate, candidate): candidate 
                        for candidate in candidates
                    }
                    
                    for future in concurrent.futures.as_completed(future_to_candidate):
                        try:
                            is_approved = future.result()
                            if is_approved:
                                approved_count += 1
                        except Exception as e:
                            logger.error(f"Error in process future: {e}")
                        finally:
                            progress.advance(task)
        
        logger.info(f"Perplexity Workflow Complete. Approved: {approved_count}/{total_candidates}")

workflow = WorkflowManager()
