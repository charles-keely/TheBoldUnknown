from typing import List, Dict, Any
from services.llm import llm
from utils.logger import logger
from config import config
import json
import datetime
import re

class Filters:
    def __init__(self):
        pass

    def generate_search_query(self, topic: str) -> str:
        """
        Generates a specific search query for a given topic.
        """
        current_year = datetime.datetime.now().year
        system_prompt = f"""You are an expert researcher for TheBoldUnknown — a publication that reveals the hidden strangeness woven through reality with stories that make people stop scrolling and think: "Wait. What?"

Your task: Convert the user's topic into a single, highly specific search query optimized for finding stories with strong WTF factor — recent anomalies, counterintuitive discoveries, or documented phenomena that break expectations.

Guidelines:
- Prioritize finding stories a non-expert would find instantly interesting and share-worthy.
- Look for: surprising discoveries, patterns that shouldn't exist, behaviors that defy intuition, unexpectedly preserved or revealed details, scientific results that contradict common knowledge.
- Valid sources: scientific journals, research papers, credible news, declassified documents, FOIA releases, official records, technical incident reports, archival curiosities.
- Avoid generic or surface-level queries — dig for the strange, specific details.
- The query should uncover things that make curious people pause and want to know more.

Examples:
- Topic: "Time crystals" → "time crystals experimental anomalies unexpected behavior {current_year}"
- Topic: "Animal migration" → "unexplained animal migration pattern breaks expectations documented"
- Topic: "Memory" → "false memory implantation surprising research findings human perception"
- Topic: "Ancient artifacts" → "archaeological discovery unexpectedly preserved strange details {current_year}"

Output ONLY the search query string. No explanation, no quotes, just the query."""
        
        user_prompt = f"Topic: {topic}"
        query = llm.chat_completion(system_prompt, user_prompt)

        # Normalize year in the query so we always target the current year
        if not query:
            return query

        year_str = str(current_year)
        # Replace any explicit 20xx year with the current year
        query_normalized = re.sub(r"20[0-9]{2}", year_str, query)

        # If the model didn't include any year, append the current year hint
        if year_str not in query_normalized:
            query_normalized = f"{query_normalized} {year_str}"

        return query_normalized

    def normalize_perplexity_result(self, raw_content: str, topic_origin: str) -> List[Dict[str, Any]]:
        """
        Parses raw Perplexity output into structured LeadCandidate objects.
        """
        system_prompt = """You are a precise data extraction assistant.

Your task: Parse the provided text (which may contain markdown, prose, or mixed formatting) and extract all distinct stories or research items mentioned.

For each story found, extract:
- title: A clear, concise title (create one if not explicitly stated)
- url: The source URL (use empty string if not found)
- summary: A 1-2 sentence summary of what makes this story notable

Return a JSON object with this exact structure:
{
  "stories": [
    {"title": "...", "url": "...", "summary": "..."},
    {"title": "...", "url": "...", "summary": "..."}
  ]
}

Rules:
- Extract ALL distinct stories mentioned, even if formatting is inconsistent.
- If a URL is embedded in text or markdown, extract it cleanly.
- If no valid stories are found, return {"stories": []}.
- Do not invent information. Only extract what is present."""

        user_prompt = raw_content
        
        response = llm.chat_completion_json(system_prompt, user_prompt)
        stories = response.get('stories', [])
        
        normalized = []
        for s in stories:
            normalized.append({
                "title": s.get('title'),
                "url": s.get('url'),
                "summary": s.get('summary'),
                "source_origin": f"Perplexity: {topic_origin}",
                "published_at": None
            })
        return normalized

    def smart_gatekeeper(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Batch filters 20 titles at once for initial relevance.
        Returns the list of items that passed.
        """
        if not batch:
            return []

        # Prepare prompt
        titles_text = "\n".join([f"{i}: {item['title']}" for i, item in enumerate(batch)])
        
        system_prompt = """You are the first-pass scout for TheBoldUnknown — a publication that reveals the hidden strangeness woven through reality with stories that make people stop scrolling and think: "Wait. What?"

YOUR TASK:
Review the numbered list of story titles. Identify which ones could become a viral TheBoldUnknown story.

THE THEBOLDUNKNOWN LENS (optimized for virality):
Stories that PASS have at least one of these qualities:
- A detail that makes a wide audience think "that's weird"
- Something unexpectedly preserved, discovered, or revealed
- Records or evidence with a puzzling element
- Natural or cosmic behaviors that break expectations
- Historical events with oddly specific or eerie twists
- Technology behaving in a surprising or emergent way
- Repeated human experiences that feel uncanny or too consistent
- Scientific results that contradict intuition
- A strong "Wait... what?" moment that non-experts would find instantly interesting

INCLUSION RULE:
If you can articulate the strange part in one sentence in a way a non-expert would find cool, the story qualifies.

Stories that FAIL:
- Celebrity gossip
- Partisan politics or culture war framing
- Outrage-driven content
- Low-evidence conspiracy claims presented as fact
- Standard news with no strange or counterintuitive angle
- Product launches with no WTF angle

NOTE: Unexplained mysteries and open questions are WELCOME. If something has a genuinely strange and well-documented detail, it passes — even if the broader topic seems borderline. Focus on the strange detail.

DECISION RULE:
Be generous. The goal is virality + quality. If there's ANY chance this title contains a genuinely strange, share-worthy angle, let it through. We filter more strictly later.

Ask yourself: Would a curious person stop scrolling for this? If yes, PASS.

OUTPUT FORMAT (JSON only):
{"passed_indices": [0, 3, 5, 12]}

Return ONLY the JSON object with the indices of titles that passed."""

        user_prompt = titles_text

        response = llm.chat_completion_json(system_prompt, user_prompt)
        passed_indices = response.get('passed_indices', [])
        
        survivors = []
        for idx in passed_indices:
            if 0 <= idx < len(batch):
                survivors.append(batch[idx])
        
        return survivors

    def virality_check(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stage 2 Filter: Virality Check.
        Scores a lead's viral potential (0-100).
        Returns the lead dict enriched with virality_score.
        """
        system_prompt = """You are a Virality Analyst for TheBoldUnknown.

Your ONLY job is to score how likely this story is to make someone stop scrolling and think: "Wait. What?"

The goal is WIDE AUDIENCE APPEAL — not niche intellectual interest.

VIRALITY SCORE (0-100):

90-100: Exceptional. Instant "Wait. What?" reaction. The kind of thing people screenshot and share without prompting. A non-expert would find this immediately fascinating. Rare.

80-89: Very strong. Genuinely counterintuitive or visually striking. Most people would click, many would share. Clear WTF factor.

70-79: Good hook. Interesting enough to catch attention. Would perform well with a broad curious audience.

60-69: Moderate. Mildly curious but doesn't demand attention. The strangeness requires some explanation.

50-59: Weak. Somewhat interesting but easy to scroll past. Hook isn't clear or immediate.

Below 50: Low interest. Predictable, generic, too niche, or the "strangeness" is forced. No scroll-stopping power.

---

VIRALITY FACTORS (what creates HIGH scores):
- "Wait. What?" moment: Instant, clear, requires no context to find strange
- Counterintuitive: Challenges assumptions or common knowledge
- Specificity: Concrete, unusual details (not vague claims)
- Universal appeal: Anyone can understand why it's weird
- Visual/cinematic potential: Easy to imagine or picture
- Scale contrast: Small cause → big effect, or vice versa
- Pattern breaks: "This shouldn't exist, yet it does"
- Relatable strangeness: Connects to human experience unexpectedly

VIRALITY KILLERS (what creates LOW scores):
- Academic framing: Leads with jargon instead of the WTF moment
- Too niche: Only specialists would care
- Vague: No specific hook or detail
- Requires too much context: Need to read 5 paragraphs to understand why it's interesting
- Sensationalized mundane: Trying to make boring things sound exciting
- Fear/outrage bait: Relies on negative emotions rather than curiosity
- Predictable: "Of course that happened"

---

OUTPUT FORMAT (JSON only):
{
  "virality_score": <number 0-100>,
  "hook_analysis": "<1-2 sentences. What's the 'Wait. What?' moment? Or why is there no clear hook?>"
}

Be honest and critical. Most stories score 50-75. Reserve 85+ for genuinely exceptional, wide-appeal hooks."""

        user_prompt = f"""Title: {lead['title']}

Summary: {lead['summary']}"""
        
        analysis = llm.chat_completion_json(system_prompt, user_prompt, model=config.OPENAI_MODEL_MAIN)
        
        lead['virality_score'] = analysis.get('virality_score', 0)
        lead['hook_analysis'] = analysis.get('hook_analysis', '')
        
        return lead

    def brand_lens_check(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stage 3 Filter: Brand Alignment Check.
        Scores how well the lead fits TheBoldUnknown's brand identity.
        Returns the lead dict enriched with brand_score and new_topics.
        """
        system_prompt = """You are the Editor-in-Chief of TheBoldUnknown.

This story has already passed a virality check. Your job is to determine if it fits the BRAND.

BRAND IDENTITY:
TheBoldUnknown reveals the hidden strangeness woven through reality — the moments, discoveries, and details that make people stop scrolling and think: "Wait. What?"

The stories are grounded and intelligent, but they LEAD WITH WTF FACTOR, not academic framing.

The tone is rational. The feeling is quiet wow. The hook is the strangeness, not the jargon.

CORE LENS QUALITIES:
- Grounded
- Rational
- Visually atmospheric
- Quietly strange
- Curiosity-driven
- Cinematic
- Never fear-bait
- Never conspiratorial
- Welcoming to non-experts

THE VOICE IS:
- Confident
- Simple but elegant
- Visually expressive
- Rational but imaginative
- Atmospheric, not dry
- Emotionally engaging
- Written for sharing and saving

THE VOICE IS NOT:
- Academic for its own sake
- Clickbait
- Mystical
- Conspiratorial
- Hypey
- Over-explaining
- Sensationalized

EMOTIONAL TARGET: "Quiet WTF + grounded clarity"

HARD EXCLUSIONS (automatic fail):
- Celebrity gossip
- Partisan politics
- Outrage-driven content
- Low-evidence conspiracy claims

NOTE: If something in these areas contains a genuinely strange and well-documented detail, focus only on that strange detail.

---

BRAND SCORE (0-100):

90-100: Perfect fit. Embodies "Wait. What?" — a detail that makes a wide audience think "that's weird." Unexpectedly preserved/discovered/revealed, breaks expectations, has visual or narrative potential. Can be an open question or explained — as long as it's honestly framed. Rare.

70-89: Strong fit. Contains a genuinely surprising or puzzling element. The strangeness is accessible to non-experts. Fits the cinematic, grounded tone.

50-69: Marginal fit. Has some interesting angle but may be too academic, too sensational, or missing the clear WTF moment. Could work with reframing.

Below 50: Poor fit. Generic news, falls into hard exclusions, leads with jargon instead of strangeness, fear-mongering, or lacks genuine "Wait. What?" quality.

---

OUTPUT FORMAT (JSON only):
{
  "brand_score": <number 0-100>,
  "reasoning": "<2-3 sentences. Be blunt. Does this have a clear 'Wait. What?' moment? Is it accessible to non-experts? What works or doesn't?>"
}

Be honest and critical. Most stories score 50-75. Reserve 90+ for genuinely exceptional brand fits."""

        user_prompt = f"""Title: {lead['title']}

Summary: {lead['summary']}"""
        
        analysis = llm.chat_completion_json(system_prompt, user_prompt, model=config.OPENAI_MODEL_MAIN)
        
        lead['brand_score'] = analysis.get('brand_score', 0)
        lead['reasoning'] = analysis.get('reasoning', '')
        # lead['new_topics'] removed to prevent echo chambers
        
        return lead

filters = Filters()
