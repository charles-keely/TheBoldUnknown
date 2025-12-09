from database import db
from services.llm import llm
from models import LeadCandidate, ProcessingStatus
from utils.logger import logger

class FilterService:
    def is_url_processed(self, url: str) -> bool:
        """
        Check if URL exists in processed_urls table.
        """
        query = "SELECT 1 FROM processed_urls WHERE url = %s"
        result = db.fetch_one(query, (url,))
        return result is not None

    def is_semantically_similar(self, embedding: list[float], threshold: float = 0.90) -> bool:
        """
        Check if embedding is too similar to existing leads.
        """
        # Postgres pgvector syntax for cosine distance is <=>
        # Similarity = 1 - distance
        # We want to find if there is ANY record with similarity > threshold
        # i.e. distance < (1 - threshold)
        
        distance_threshold = 1 - threshold
        query = """
        SELECT 1 FROM leads 
        WHERE embedding <=> %s < %s
        LIMIT 1;
        """
        # pgvector expects string representation of vector in SQL usually, or list with psycopg2 adapter
        # psycopg2 + pgvector usually handles list -> vector auto-casting if registered, 
        # but explicit casting is safer: %s::vector
        
        # NOTE: We assume pgvector extension is loaded and driver handles it, 
        # or we format it as string. Let's try passing list first.
        result = db.fetch_one(query, (str(embedding), distance_threshold))
        return result is not None

    def filter_stage_1_dedupe(self, candidate: LeadCandidate) -> bool:
        """
        Stage 1: Deduplication (URL & Semantic).
        Returns True if candidate passes (is unique), False otherwise.
        """
        # 1. URL Check
        if self.is_url_processed(candidate.url):
            logger.debug(f"Duplicate URL: {candidate.url}")
            return False
            
        # 2. Embedding Generation
        try:
            # Combine title and summary for embedding
            text = f"{candidate.title}\n{candidate.summary}"
            candidate.embedding = llm.generate_embedding(text)
        except Exception as e:
            logger.error(f"Embedding failed for {candidate.url}: {e}")
            return False
            
        # 3. Semantic Check
        if self.is_semantically_similar(candidate.embedding):
            logger.debug(f"Semantically similar content found for: {candidate.title}")
            return False
            
        return True

    def filter_stage_2_virality(self, candidate: LeadCandidate, threshold: int = 55) -> bool:
        """
        Stage 2: Virality/Engagement Potential Check.
        Filters for stories with social media shareability potential.
        Uses a lower threshold (55) since this is a broad filter - 
        the brand check does the deep analysis.
        """
        try:
            result = llm.check_virality(candidate.title, candidate.summary)
            candidate.virality_score = result.get('virality_score', 0)
            candidate.viral_hook = result.get('hook', '')
            reasoning = result.get('reasoning', '')
            
            if candidate.virality_score < threshold:
                logger.debug(f"Low virality ({candidate.virality_score}): {candidate.title} | {reasoning}")
                return False
            
            logger.debug(f"Virality passed ({candidate.virality_score}): {candidate.title} | Hook: {candidate.viral_hook}")
            return True
        except Exception as e:
            logger.error(f"Virality check failed: {e}")
            return False

    def filter_stage_3_brand(self, candidate: LeadCandidate) -> bool:
        """
        Stage 3: Brand Alignment.
        """
        try:
            result = llm.check_brand_alignment(candidate.title, candidate.summary)
            candidate.brand_score = result.get('brand_score', 0)
            candidate.brand_reasoning = result.get('reasoning', '')
            candidate.new_topics = result.get('new_topics', [])
            
            if candidate.brand_score < 70:
                logger.info(f"Brand reject ({candidate.brand_score}): {candidate.title}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Brand check failed: {e}")
            return False

filter_service = FilterService()
