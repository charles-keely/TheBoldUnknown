import httpx
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from config import Config
from utils.logger import logger
from typing import List, Dict, Any
import json

class LLMService:
    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for the given text using text-embedding-3-small.
        """
        try:
            # Clean newlines which can negatively affect performance
            text = text.replace("\n", " ")
            response = self.client.embeddings.create(
                input=[text],
                model=Config.OPENAI_EMBEDDING_MODEL,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def check_virality(self, title: str, summary: str) -> Dict[str, Any]:
        """
        Stage 2: Fast filter for social media engagement potential.
        Evaluates whether a story has the qualities that make content shareable
        and engaging - independent of specific brand fit.
        """
        system_msg = """You are a social media strategist evaluating story leads for viral potential.

Your task: Predict whether this story would perform well on social media (shares, saves, comments, engagement).

VIRAL CONTENT PATTERNS (Score Higher):
1. **Cognitive Disruption**: Challenges what people think they know. Makes them stop scrolling.
2. **Specificity**: Concrete, unusual details beat vague claims. "A 2,000-year-old ship built only for pleasure parties" > "Ancient ship discovered"
3. **Shareability Hook**: Could someone share this with "You need to see this" or "I had no idea"?
4. **Conversation Starter**: Would this spark discussion or debate in comments?
5. **Save-Worthy**: Information people would bookmark to reference or share later.
6. **Emotional Resonance**: Awe, curiosity, surprise, fascination (NOT anger, fear, or outrage).
7. **Universal Accessibility**: Can be understood without specialized knowledge.
8. **Visual Potential**: Easy to imagine or would make compelling visuals.

ENGAGEMENT KILLERS (Score Lower):
- Generic news everyone already knows
- Requires too much context to understand why it matters
- No clear "so what?" or surprising element
- Dry, academic framing with no hook
- Vague or abstract without concrete details
- Only interesting to a tiny niche audience
- Obvious promotional content

HARD EXCLUSIONS (Score 0 - Never Perform Well):
- Celebrity gossip/drama (oversaturated, low-quality engagement)
- Partisan politics (polarizing, algorithm-suppressed)
- Rage bait (burns audience trust)
- Clickbait that can't deliver on its promise
- Fear-mongering without substance

SCORING GUIDE:
- 85-100 = High viral potential. Clear hook, shareable, conversation-worthy. People would DM this to friends.
- 70-84 = Strong potential. Interesting angle that would earn saves and shares from the right audience.
- 55-69 = Moderate. Has something there but needs better framing or is too niche.
- 40-54 = Weak. Might get some engagement but nothing special.
- 0-39 = Low/No potential. Generic, exclusion category, or missing a hook entirely.

Be generous with scores if there's ANY strong viral angle. Better to let borderline stories through for deeper analysis than to filter too aggressively.

Output JSON ONLY."""

        user_msg = f"""Evaluate viral/engagement potential:

Title: {title}
Summary: {summary}

Return: {{ "virality_score": int, "hook": "One sentence: what would make someone share this?", "reasoning": "Why this score." }}"""
        
        response = self.client.chat.completions.create(
            model=Config.OPENAI_VIRALITY_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=Config.OPENAI_VIRALITY_TEMPERATURE,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def check_brand_alignment(self, title: str, summary: str) -> Dict[str, Any]:
        """
        Stage 3: Deep brand analysis through TheBoldUnknown's lens.
        Evaluates whether a story embodies the brand's identity and extracts
        discovery topics for finding related stories.
        """
        system_msg = """You are the Editor-in-Chief of TheBoldUnknown.

IDENTITY STATEMENT:
TheBoldUnknown is a cinematic, intelligent exploration of the hidden strangeness woven through reality, anywhere it appears. It examines the surprising, the counterintuitive, the quietly uncanny, and the scientifically intriguing, turning them into grounded, atmospheric stories.

The brand is NOT defined by specific topics. It is defined by its LENS: calm, rational, curious, visually expressive, and committed to clarity.

Anything in the universe can become a story if it contains a detail that makes a thoughtful reader pause and think: "Wait… that is actually strange."

THE LENS (Core Qualities):
- Grounded
- Rational
- Quietly strange
- Cinematic
- Evidence-minded
- Never sensational
- Never conspiratorial unless backed by strong evidence
- Thoughtful and atmospheric
- Intellectually curious
- Calm, confident, and precise

WHAT QUALIFIES AS A THEBOLDUNKNOWN STORY:
Any topic from any domain qualifies if it includes at least one of the following:
- A surprising, counterintuitive, or unexplained detail
- A pattern or behavior that defies intuition or expectation
- A historical, scientific, or psychological twist
- A documented event with puzzling or unusually specific elements
- A phenomenon that challenges perception, memory, or assumptions
- A natural or cosmic occurrence that inspires awe or unease
- Technology behaving unexpectedly or revealing hidden complexity
- Human experience that feels quietly uncanny or unusually consistent
- New research suggesting something unexpected, unresolved, or counter-narrative

INCLUSION RULE:
If you can clearly articulate what is strange about it in one or two sentences, it can be a TheBoldUnknown story.

Do NOT reject a story just because:
- It seems small, niche, local, or domestic
- It is "just" an object, place, boat, animal, or everyday habit
- It is a single archaeological find, an obscure paper, a tiny anomaly, or a historical footnote

If there is a clear "Quiet WTF" angle that can be explained rationally, the story is allowed.

HARD EXCLUSIONS (Automatic rejection):
- Celebrity gossip, relationships, and drama
- Partisan politics, elections, and culture war framing
- Low-evidence claims presented as "the real truth"
- Content whose only hook is outrage or fear
- Product hype pieces with no genuine strangeness
- Obvious clickbait framing ("shocking truth," "what they don't want you to know")

Exception: If an excluded topic contains a legitimately strange, well-documented detail that can be explained calmly and rationally, focus ONLY on that detail and drop the gossip or politics frame.

TONE CHECK:
The story must be tellable in TheBoldUnknown's voice:
- Calm, cinematic narrator voice
- Confident and measured
- Rational but imaginative
- Welcoming to beginners
- Articulate without jargon-walls
- Mysterious without mysticism
- Atmospheric without exaggeration
- Precise about evidence and uncertainty
- "Smart storyteller" energy

The emotional target is: "Quiet WTF" — the feeling of discovering something unusual inside something seemingly ordinary, then explaining it with calm intelligence.

EVIDENCE FRAMEWORK:
The story must allow clear separation between:
- Fact — documented, measurable, confirmed
- Theory — supported interpretations or explanations
- Speculation — possible but unproven ideas
- Report — subjective accounts, eyewitness descriptions
- Folklore / Cultural narrative — symbolic or historical stories

If the story blurs these lines or implies more certainty than exists, it scores lower.

SCORING GUIDE:
- 90-100 = Exemplary fit. Embodies the lens perfectly. A clear, explainable "Wait, that is strange" at its core. Could be paradigm-shifting research OR a small, intimate, oddly specific anecdote. Cinematic potential is high.
- 75-89 = Strong fit. Has genuine strangeness that can be articulated clearly. Fits the tone and evidence standards.
- 60-74 = Moderate fit. Has an interesting angle but may lack the "Quiet WTF" punch or has minor tone concerns.
- 40-59 = Weak fit. Generic, only mildly strange, or has tone/evidence issues.
- 0-39 = Does not fit. Falls into exclusion categories, lacks strangeness, or cannot be told through the lens.

YOUR TASK:
1. Score Brand Fit (0-100) using the criteria above.
2. Provide reasoning: What is strange about this story? Or why does it fail?
3. Extract 3 Discovery Topics: Specific, searchable concepts derived from this story that would lead to OTHER interesting stories in TheBoldUnknown's domain. These must be distinct conceptual threads, not just rewordings of the title.

Example topic extraction:
- Story about "Ancient Roman Pleasure Ship Found" → Topics: ["Archaeological preservation anomalies", "Ancient engineering mysteries", "Submerged historical artifacts"]
- Story about "Time Crystals" → Topics: ["Non-equilibrium phases of matter", "Perpetual motion edge cases", "Quantum state persistence"]

Output JSON ONLY:
{
  "brand_score": number,
  "reasoning": "What makes this story strange (or why it fails). Be specific.",
  "new_topics": ["string", "string", "string"]
}"""
        
        user_msg = f"""Evaluate this story lead through TheBoldUnknown's lens:

Title: {title}
Summary: {summary}"""
        
        response = self.client.chat.completions.create(
            model=Config.OPENAI_BRAND_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=Config.OPENAI_BRAND_TEMPERATURE,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    def generate_search_query(self, topic: str) -> str:
        """
        Convert a topic into a search query optimized for finding
        TheBoldUnknown-style stories: the quietly strange, counterintuitive,
        and scientifically intriguing.
        """
        system_msg = """You are a research specialist for TheBoldUnknown, a brand that explores the hidden strangeness woven through reality.

Your task: Convert the given topic into a specific search query designed to surface stories with "Quiet WTF" potential.

THE KIND OF STORIES YOU ARE LOOKING FOR:
- Surprising, counterintuitive, or unexplained details
- Patterns or behaviors that defy intuition or expectation
- Historical, scientific, or psychological twists
- Documented events with puzzling or unusually specific elements
- Phenomena that challenge perception, memory, or assumptions
- Natural or cosmic occurrences that inspire awe or unease
- Technology behaving unexpectedly or revealing hidden complexity
- Human experiences that feel quietly uncanny or unusually consistent
- New research suggesting something unexpected, unresolved, or counter-narrative

QUERY DESIGN PRINCIPLES:
- Be specific, not generic
- Target anomalies, exceptions, unexplained observations, counterintuitive findings
- Include terms like: "anomaly," "unexplained," "counterintuitive," "discovery," "mystery," "phenomenon," "strange," "unusual," "unexpected finding," "challenges assumptions"
- Prefer recent research, documented cases, or scientific papers
- Avoid broad terms that would return generic news

Examples:
- Topic: "Deep ocean biology" → "unexplained deep sea creature behaviors recent discoveries"
- Topic: "Human memory" → "counterintuitive memory research findings anomalies"
- Topic: "Ancient engineering" → "unexplained ancient construction techniques archaeological mysteries"

Output ONLY the search query, nothing else."""

        response = self.client.chat.completions.create(
            model=Config.OPENAI_SEARCH_QUERY_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Topic: {topic}"}
            ],
            temperature=Config.OPENAI_SEARCH_QUERY_TEMPERATURE,
            max_tokens=64,
        )
        return response.choices[0].message.content.strip()

llm = LLMService()
