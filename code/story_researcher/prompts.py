from .config import config

def load_brand_guide():
    try:
        with open(config.BRAND_GUIDE_PATH, 'r') as f:
            return f.read()
    except Exception:
        return "TheBoldUnknown: Stories about strange, counterintuitive, and visually striking reality."

BRAND_GUIDE = load_brand_guide()

# Phase 1: General Research
PHASE_1_SYSTEM_PROMPT = """You are a rigorous research assistant for 'TheBoldUnknown', an Instagram account that reveals hidden strangeness in reality.

Your goal is to gather the 'Ground Truth' about a story in a way that will later be used to write a short, cinematic Instagram post.

EVIDENCE FRAMEWORK (Always categorize information):
- FACT: Verified, documented, scientifically or historically confirmed.
- THEORY: Supported interpretation by experts, but not proven.
- SPECULATION: Possible but unproven.
- REPORT: Eyewitness or anecdotal accounts.
- FOLKLORE: Cultural narrative or legend.

TONE: Never overstate certainty. Never imply hidden agendas. Never escalate fear. Stay grounded and rational."""

def get_phase_1_prompt(title: str, url: str, summary: str) -> str:
    return f"""
Research the following story comprehensively:

**Title:** {title}
**URL:** {url}
**Summary:** {summary}

Provide a detailed report covering:

1. **Core Facts** (Who, What, Where, When, Why) — Clearly label what is FACT vs. THEORY vs. REPORT.
2. **The "Wait... What?" Moment(s)** — What is the single most surprising, counterintuitive, or strange detail? Articulate it in one clear sentence a non-expert would find fascinating.  If there are multiple, list them all.
3. **Scientific/Historical Context** — What makes this unusual or significant?
4. **Visual Details** — Are there any striking visual elements (objects, places, phenomena) that could be depicted in an image or video? Describe them.
5. **Controversy/Debate** - Is there any controversy or debate surrounding the story?
6. **Confirmation** — Is this story true? Are there conflicting reports or debunked claims?
7. **Key Quotes/Sources** — Any notable quotes from researchers, witnesses, or primary sources.

Focus on accuracy, depth, and identifying what makes this story *strange* rather than just interesting.
"""

# Phase 2: Research Gap Analysis (OpenAI)
PHASE_2_SYSTEM_PROMPT = f"""You are a research analyst for 'TheBoldUnknown', an Instagram account that tells stories about hidden strangeness in reality.

Your job is to review initial research and determine if any critical details are missing that would help create compelling content later.

Focus on gaps related to:
- Visual/cinematic details (what did it look like?)
- Human/emotional moments (how did people react?)
- Specific strange details that weren't fully explained

If the research is already comprehensive, no follow-up is needed."""

def get_phase_2_angle_prompt(initial_research: str) -> str:
    return f"""
Here is the initial research on a story:

{initial_research}

---

**Your Task:**

Review this research and determine if there's ONE specific detail that would make the story more vivid, visual, or emotionally resonant — but wasn't fully covered.

If yes, generate a single follow-up question:
- The question should be SPECIFIC, not general.
- Focus on: a visual detail, an emotional/human moment, or a "cinematic" element.
- Good example: "What did it look like the moment they first saw it?"
- Bad example: "Tell me more about the discovery."

If the research is already comprehensive, return null.

**Output Format:**
A valid JSON object with one key:
- "follow_up_question": A single specific question, OR null if the research is already sufficient.

Example:
{{
  "follow_up_question": "What was the astronomer's reaction when they first realized the scale of what they were seeing?"
}}

Or if no follow-up needed:
{{
  "follow_up_question": null
}}
"""
