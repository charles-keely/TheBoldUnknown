from typing import List
from services.rss import rss_service
from services.perplexity import perplexity_service
from services.llm import llm
from database import db
from logic.filters import filters
from logic.discovery import discovery_engine
from config import config
from utils.logger import logger
import time

class Workflow:
    def __init__(self):
        pass

    def run(self, source: str = "all"):
        logger.info(f"Starting workflow run. Source: {source}")
        
        candidates = []

        # ============================================
        # PHASE 1: INGESTION
        # ============================================
        if source in ["all", "rss"]:
            logger.info("Fetching RSS feeds...")
            rss_items = rss_service.fetch_all()
            candidates.extend(rss_items)
            logger.info(f"Fetched {len(rss_items)} items from RSS.")

        if source in ["all", "perplexity"]:
            logger.info("Fetching from Perplexity...")
            topic_record = db.get_active_discovery_topics()
            if topic_record:
                topic_data = topic_record[0]
                topic = topic_data['topic']
                topic_id = topic_data['id']
                logger.info(f"Selected topic: {topic}")
                
                query = filters.generate_search_query(topic)
                logger.info(f"Generated query: {query}")
                
                raw_result = perplexity_service.search(query)
                if raw_result:
                    normalized = filters.normalize_perplexity_result(raw_result, topic)
                    candidates.extend(normalized)
                    logger.info(f"Fetched {len(normalized)} items from Perplexity.")
                    
                    db.update_topic_last_searched(topic_id)
            else:
                logger.info("No active discovery topics found.")

        # Apply candidate limit if set (for testing)
        if config.MAX_CANDIDATES and len(candidates) > config.MAX_CANDIDATES:
            logger.info(f"Limiting candidates from {len(candidates)} to {config.MAX_CANDIDATES} (MAX_CANDIDATES)")
            candidates = candidates[:config.MAX_CANDIDATES]
        
        logger.info(f"Total candidates: {len(candidates)}")

        # ============================================
        # PHASE 2: URL DEDUPLICATION (First - Free & Instant)
        # ============================================
        url_checked = []
        url_dupes = 0
        
        for lead in candidates:
            url = lead.get('url')
            if not url:
                continue
            if db.check_url_exists(url):
                url_dupes += 1
                continue
            url_checked.append(lead)
        
        logger.info(f"After URL dedup: {len(url_checked)} candidates ({url_dupes} duplicates removed)")

        # ============================================
        # PHASE 3: BATCH GATEKEEPER (Quick Relevance Filter)
        # ============================================
        batch_size = config.FILTER_BATCH_SIZE
        gatekeeper_survivors = []

        for i in range(0, len(url_checked), batch_size):
            batch = url_checked[i : i + batch_size]
            logger.info(f"Gatekeeper batch {i//batch_size + 1}/{(len(url_checked)+batch_size-1)//batch_size}")
            
            batch_survivors = filters.smart_gatekeeper(batch)
            gatekeeper_survivors.extend(batch_survivors)
            logger.info(f"Batch survivor rate: {len(batch_survivors)}/{len(batch)}")

        logger.info(f"After Gatekeeper: {len(gatekeeper_survivors)} candidates")

        # ============================================
        # PHASE 4: SEMANTIC DEDUPLICATION (Embedding Similarity)
        # ============================================
        embedding_survivors = []
        semantic_dupes = 0
        
        for lead in gatekeeper_survivors:
            title = lead.get('title', 'Unknown')
            
            # Generate embedding
            embedding = llm.get_embedding(f"{lead['title']}\n{lead['summary']}")
            if not embedding:
                logger.warning(f"[EMBED] Failed to generate embedding for: {title}")
                continue
            
            lead['embedding'] = embedding
            
            # Strict similarity check (0.85 threshold = 85% similar is a dupe)
            if db.check_similarity(embedding, threshold=config.SIMILARITY_THRESHOLD):
                logger.info(f"[DEDUP] Semantically similar, skipping: {title}")
                db.mark_url_processed(lead.get('url'))
                semantic_dupes += 1
                continue
            
            embedding_survivors.append(lead)
        
        logger.info(f"After Semantic dedup: {len(embedding_survivors)} candidates ({semantic_dupes} similar stories removed)")

        # ============================================
        # PHASE 5: VIRALITY CHECK (Threshold: 80+)
        # ============================================
        virality_survivors = []
        
        for lead in embedding_survivors:
            title = lead.get('title', 'Unknown')
            url = lead.get('url')
            
            lead = filters.virality_check(lead)
            
            if lead['virality_score'] < config.VIRALITY_THRESHOLD:
                logger.info(f"[VIRALITY] Rejected ({lead['virality_score']}/100): {title}")
                db.mark_url_processed(url)
                continue
            
            logger.info(f"[VIRALITY] Passed ({lead['virality_score']}/100): {title}")
            virality_survivors.append(lead)

        logger.info(f"After Virality check: {len(virality_survivors)} candidates")

        # ============================================
        # PHASE 6: BRAND CHECK (Threshold: 70+)
        # ============================================
        saved_count = 0
        
        for lead in virality_survivors:
            title = lead.get('title', 'Unknown')
            url = lead.get('url')
            
            lead = filters.brand_lens_check(lead)
            
            if lead['brand_score'] < config.BRAND_THRESHOLD:
                logger.info(f"[BRAND] Rejected ({lead['brand_score']}/100): {title}")
                db.mark_url_processed(url)
                continue

            # ============================================
            # PHASE 7: SAVE
            # ============================================
            lead_id = db.insert_lead(lead)
            saved_count += 1
            logger.info(f"[SAVED] {title} (Virality: {lead['virality_score']}, Brand: {lead['brand_score']})")
            
            # Mark URL as processed
            db.mark_url_processed(url)
            
        # ============================================
        # PHASE 8: REFUEL (Discovery Engine)
        # ============================================
        # Check active topics count (rough estimate or just add fresh ones)
        # For now, we simply inject fresh entropy every run
        logger.info("Refueling Discovery Engine...")
        new_topics_list = discovery_engine.generate_fresh_topics(count=3)
        
        # Format for DB insert: [{"topic": "...", "origin_lead_id": None}]
        # origin_lead_id is None because these come from the Void (Entropy), not a specific story
        discovery_payload = [{"topic": t, "origin_lead_id": None} for t in new_topics_list]
        
        if discovery_payload:
            db.insert_discovery_topics(discovery_payload)
            logger.info(f"[DISCOVERY] Injected {len(discovery_payload)} fresh entropy topics: {new_topics_list}")

        # ============================================
        # SUMMARY
        # ============================================
        logger.info("=" * 50)
        logger.info("WORKFLOW COMPLETE")
        logger.info(f"  Total ingested:        {len(candidates)}")
        logger.info(f"  After URL dedup:       {len(url_checked)}")
        logger.info(f"  After Gatekeeper:      {len(gatekeeper_survivors)}")
        logger.info(f"  After Semantic dedup:  {len(embedding_survivors)}")
        logger.info(f"  After Virality:        {len(virality_survivors)}")
        logger.info(f"  Saved to DB:           {saved_count}")
        logger.info(f"  Entropy Injected:      {len(new_topics_list)} topics")
        logger.info("=" * 50)

workflow = Workflow()
