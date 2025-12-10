from typing import List, Dict, Any
from services.llm import llm
from utils.logger import logger
from config import config
import json

class Filters:
    def __init__(self):
        pass

    def generate_search_query(self, topic: str) -> str:
        """
        Generates a specific search query for a given topic.
        """
        system_prompt = """You are an expert researcher for TheBoldUnknown, a publication that explores the hidden strangeness woven through reality.

Your task: Convert the user's topic into a single, highly specific search query optimized for finding recent anomalies, counterintuitive research, or documented phenomena.

Guidelines:
- Focus on finding documented, evidence-based stories with a "quietly strange" angle.
- Valid sources include: scientific journals, research papers, credible news, declassified government documents, FOIA releases, official records, technical incident reports, and documented technological anomalies.
- Avoid generic or surface-level queries.
- The query should uncover surprising details, unexplained patterns, counterintuitive findings, or strange bureaucratic/institutional oddities.

Examples:
- Topic: "Time crystals" → "time crystals non-equilibrium matter recent experimental anomalies 2024"
- Topic: "Animal migration" → "unexplained animal migration pattern deviations documented studies"
- Topic: "Memory" → "false memory implantation research counterintuitive findings neuroscience"

Output ONLY the search query string. No explanation, no quotes, just the query."""
        
        user_prompt = f"Topic: {topic}"
        return llm.chat_completion(system_prompt, user_prompt)

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
                "source_origin": f"Perplexity: {topic_origin}"
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
        
        system_prompt = """You are the first-pass scout for TheBoldUnknown, a publication that explores the hidden strangeness woven through reality with calm, cinematic intelligence.

YOUR TASK:
Review the numbered list of story titles. Identify which ones have potential to become a TheBoldUnknown story.

THE THEBOLDUNKNOWN LENS:
Stories that PASS have at least one of these qualities:
- A surprising, counterintuitive, or unexplained detail
- A pattern or behavior that defies intuition or expectation
- A scientific, historical, or psychological twist
- A documented event with puzzling or unusually specific elements
- Technology behaving unexpectedly or revealing hidden complexity
- Research suggesting something unexpected, unresolved, or counter-narrative
- Declassified government documents, FOIA releases, or official records with strange details
- Technological anomalies, glitches, or unexpected system behaviors
- Institutional or bureaucratic oddities hidden in public records
- A "quiet WTF" moment — something that makes you pause and think "wait... that's actually strange"

Stories that FAIL:
- Celebrity gossip, relationships, or drama
- Partisan politics, elections, culture war framing
- Standard product launches or corporate announcements
- Sports scores or routine updates
- Pure outrage bait or fear-mongering
- Generic news with no strange or counterintuitive angle
- False claims or misinformation presented as fact
- Low-evidence conspiracy theories presented as fact

NOTE: Unexplained mysteries and open questions are WELCOME. The brand embraces curiosity about the unknown. What we reject is dishonesty — presenting unverified claims as established truth.

DECISION RULE:
Be generous at this stage. If there's ANY chance a title contains a genuinely strange, documented, or counterintuitive angle, let it through. We filter more strictly later.

When in doubt: Does this title make a curious, intelligent person pause and want to know more? If yes, PASS.

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

Your ONLY job is to score how likely this story is to make someone stop scrolling and want to learn more.

VIRALITY SCORE (0-100):

90-100: Exceptional hook. Creates an immediate "wait... what?" reaction. High curiosity gap. The kind of thing people screenshot and share. Rare.

80-89: Very strong hook. Genuinely counterintuitive or surprising. Most people would click and many would share.

70-79: Good hook. Interesting enough to catch attention. Would perform well with the right audience.

60-69: Moderate interest. Mildly curious but doesn't demand attention. Might get engagement from niche audiences.

50-59: Weak hook. Somewhat interesting but easy to scroll past.

Below 50: Low interest. Predictable, generic, or the "strangeness" is forced. No scroll-stopping power.

---

VIRALITY FACTORS (what creates HIGH scores):
- Curiosity gap: "Wait, how is that possible?"
- Counterintuitive: Challenges assumptions or common knowledge
- Specificity: Concrete, unusual details are more compelling than vague claims
- Scale contrast: Small cause → big effect, or vice versa
- Pattern breaks: "This shouldn't happen, but it does"
- Relatable mystery: Connects to human experience in unexpected ways
- Universal appeal: Anyone can understand why it's strange

VIRALITY KILLERS (what creates LOW scores):
- Predictable: "Of course that happened"
- Vague: No specific hook or detail
- Niche without bridge: Too specialized with no universal appeal
- Sensationalized mundane: Trying to make boring things sound exciting
- Fear/outrage bait: Relies on negative emotions rather than curiosity
- Requires too much context: Need to read 5 paragraphs to understand why it's interesting

---

OUTPUT FORMAT (JSON only):
{
  "virality_score": <number 0-100>,
  "hook_analysis": "<1-2 sentences explaining why this score. What's the hook? Or why is there no hook?>"
}

Be honest and critical. Most stories should score 50-75. Reserve 85+ for genuinely exceptional hooks."""

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
        system_prompt = """You are the ruthlessly discerning Editor-in-Chief of TheBoldUnknown.

This story has already passed a virality check. Your job is to determine if it fits the BRAND.

BRAND IDENTITY:
TheBoldUnknown is a cinematic, intelligent exploration of the hidden strangeness woven through reality. It examines the surprising, counterintuitive, quietly uncanny, and intriguing — turning them into grounded, atmospheric stories.

The brand is defined by its lens: calm, rational, curious, visually expressive, and committed to clarity.

CORE LENS QUALITIES:
- Grounded and evidence-minded
- Rational but imaginative  
- Quietly strange (not sensational)
- Cinematic and atmospheric
- "Smart storyteller" energy
- Calm, confident, and precise
- Comfortable with the unexplained — mysteries and open questions are welcome

THE VOICE IS NOT:
- Clickbait or hype-driven
- Reactive or alarmist
- Presenting unverified claims as established fact
- Conspiratorial
- Fear-bait or all-caps drama
- Sensationalizing ordinary facts
- Making things up or spreading misinformation

CRITICAL DISTINCTION:
- Unexplained phenomena and open questions = GOOD ("Scientists observed X but don't yet know why")
- False claims or misinformation presented as truth = BAD ("X is definitely caused by Y" without evidence)
- The brand embraces mystery and curiosity. It rejects dishonesty and unfounded certainty.

---

BRAND SCORE (0-100):

90-100: Perfect fit. A scientific anomaly, counterintuitive pattern, historical twist, documented mystery, unexplained phenomenon, technological glitch, or strange detail from declassified/government documents that embodies "quiet WTF." Can be explained OR remain an open question — as long as it's honestly framed. Rare.

70-89: Strong fit. Contains a genuinely surprising or puzzling element. The strangeness is real — whether explained, unexplained, or still debated. Honest about what is known vs unknown.

50-69: Marginal fit. Has some interesting angle but may be too generic, too sensational, or missing the "quietly strange" quality. Could work with heavy reframing.

Below 50: Poor fit. Generic news, celebrity/political content, pure hype, fear-mongering, lacks genuine strangeness, OR presents false/unverified claims as established fact. Misinformation is an automatic fail.

---

OUTPUT FORMAT (JSON only):
{
  "brand_score": <number 0-100>,
  "reasoning": "<2-3 sentences. Be blunt. What works? What doesn't? Why this score?>"
}

Be honest and critical. Most stories should score 50-75. Reserve 90+ for genuinely exceptional brand fits."""

        user_prompt = f"""Title: {lead['title']}

Summary: {lead['summary']}"""
        
        analysis = llm.chat_completion_json(system_prompt, user_prompt, model=config.OPENAI_MODEL_MAIN)
        
        lead['brand_score'] = analysis.get('brand_score', 0)
        lead['reasoning'] = analysis.get('reasoning', '')
        # lead['new_topics'] removed to prevent echo chambers
        
        return lead

filters = Filters()
