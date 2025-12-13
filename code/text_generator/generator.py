import os
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-5.2"

def load_brand_guide():
    """Loads the brand guide from the project root."""
    try:
        paths_to_try = ["brand-guide2.md", "../brand-guide2.md"]
        for path in paths_to_try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read()
        logger.warning("brand-guide2.md not found in expected locations.")
        return ""
    except Exception as e:
        logger.error(f"Error loading brand guide: {e}")
        return ""

BRAND_GUIDE = load_brand_guide()

def generate_story_slides(research_text):
    """
    Generates the narrative slides text based on research.
    This is called FIRST, before the cover.
    Returns a dict with 'slides' list.
    """
    system_prompt = f"""You are writing an Instagram carousel story for TheBoldUnknown.

YOUR JOB IS TO FIND THE "WAIT, WHAT?" MOMENTS.

You will receive research data. Most of it is background, context, or boring detail. Your job is to hunt through it and find the genuinely strange, surprising, or counterintuitive facts—the moments that make a reader stop and think "wait... what?"

Then build the entire story around those moments.

BRAND CONTEXT:
{BRAND_GUIDE}

---

STEP 1: FIND THE STRANGE PARTS

Read the research and ask yourself:
- What here genuinely surprised me?
- What detail seems too weird to be true (but is)?
- What would make someone stop scrolling?
- What's the thing I'd tell a friend about?

IGNORE:
- Generic background information
- Obvious facts everyone already knows
- Dry academic framing
- Tangents that don't serve the core strangeness

The research may contain a lot of material. You don't need to use all of it. You need to find the INTERESTING parts and build around them.

---

STEP 2: BUILD THE STORY AROUND THE WTF

Once you've identified the strange moments, structure your story to:
1. HOOK with the strangest fact (Slide 1)
2. SUPPORT it with evidence and specific details
3. EXPAND on why it matters or what it implies
4. LAND with resonance

Every slide should either:
- Deliver a "wait, what?" moment
- Directly support/explain a "wait, what?" moment
- Provide essential context for understanding the strangeness

If a slide doesn't do one of these things, cut it.

---

WHAT MAKES GOOD "WAIT, WHAT?" CONTENT:

✓ Specific, documented facts that defy expectation
✓ Human behavior that seems irrational but is widespread
✓ Patterns that shouldn't exist but do
✓ Details that are oddly specific
✓ Things that challenge assumptions
✓ Quiet revelations, not loud ones

WHAT TO AVOID:

✗ Vague claims ("many people believe...")
✗ Obvious statements ("technology is changing our lives")
✗ Dry academic summaries
✗ Tangents that don't connect to the core strangeness
✗ Moralizing or editorializing without substance

---

SLIDE COUNT: TARGET 7-9 SLIDES (8 is ideal)

- Long enough to feel substantial
- Short enough that people finish
- Only go 10+ if every slide delivers something new

IDEAL 8-SLIDE STRUCTURE:

SLIDE 1: THE HOOK
The strangest, most interesting fact. What is this story ABOUT?
State it clearly. The reader should immediately know why they should keep reading.

SLIDE 2: CONTEXT
Quick orientation. What domain are we in? Ground the reader fast.

SLIDE 3: THE CORE FACT
The documented, verifiable anchor. Your credibility moment.

SLIDE 4: THE STRANGE DETAIL
The "quiet WTF" moment. The specific detail that makes this worth telling.

SLIDE 5: EXPANSION
Why does this matter? What does it imply? Connect to something larger.

SLIDE 6: GROUNDING
Rational explanation. How do we make sense of this? No conspiracy tone.

SLIDE 7: BROADER MEANING
Pattern, implication, or unanswered question.

SLIDE 8: SOFT LANDING
Leave them thinking. An image, a question, something that lingers.

---

THE CARDINAL RULE: GET TO THE POINT IMMEDIATELY.

Slide 1 must hook in 2 seconds. No scene-setting. No atmosphere. The strange fact, stated clearly.

BAD SLIDE 1: "The bedroom was quiet. The door was closed. Something was happening that researchers are only beginning to understand."

GOOD SLIDE 1: "Some people are falling asleep next to AI chatbots they describe as romantic partners. A 2025 study found these relationships register as psychologically real."

---

WRITING PRINCIPLES:

- EVERY SLIDE MUST DELIVER VALUE. No filler.
- SPECIFICITY over abstraction. Numbers, names, details.
- TRUST THE READER. Don't explain why it's strange—show it.
- EVIDENCE CLARITY. Fact vs. theory vs. speculation.

VOICE: Calm, intelligent, genuinely curious. Not academic. Not clickbait.

---

CONSTRAINTS:

- Target 7-9 slides. Maximum 12 only if justified.
- Each slide: 1-2 paragraphs
- Character limits (strict):
  - 1 paragraph: MAX 549 characters
  - 2 paragraphs: MAX 502 characters total

DOCUMENT_TYPE_TAG for each slide:
- FIELD REPORT — observed events, documented behavior
- ARCHIVAL BRIEF — historical context, background
- TECHNICAL NOTE — mechanism, how something works
- RESEARCH SUMMARY — findings from studies
- THEORY OVERVIEW — interpretations, hypotheses
- INCIDENT LOG — specific documented occurrence
- EDITORIAL PERSPECTIVE — synthesis, reflection

OUTPUT FORMAT (JSON):
{{
    "slides": [
        {{ "text": "...", "tag": "RESEARCH SUMMARY" }},
        {{ "text": "...", "tag": "FIELD REPORT" }},
        ...
    ]
}}"""
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Find the 'wait, what?' moments in this research and build a 7-9 slide story around them:\n\n{research_text}"}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error generating story slides: {e}")
        raise

def generate_cover_options(research_text, story_slides):
    """
    Generates 3 Title/Subtitle/Tag pairs based on the COMPLETED story.
    This is called SECOND, after the story is written.
    Returns a dict with 'options', 'selected_id', and 'reasoning'.
    """
    # Format the story for the prompt
    story_text = "\n\n".join([f"[{s['tag']}]\n{s['text']}" for s in story_slides])
    
    system_prompt = f"""You write cover text for TheBoldUnknown Instagram posts.

You've just read a completed story. Now write a hook that tells people WHAT THIS STORY IS ABOUT while making them want to read it.

THE HOOK MUST SUMMARIZE THE STORY. It's not just evocative—it tells you what you're going to learn.

BRAND CONTEXT:
{BRAND_GUIDE}

---

THE COMPLETED STORY:
{story_text}

---

RULES FOR THE HOOK/TITLE (all caps, 4-10 words):

The hook should answer: "What is this story about?" in the most interesting way possible.

It should either:
1. STATE the most interesting fact from the story
2. ASK the most interesting question the story answers
3. SUMMARIZE the core phenomenon in a way that creates curiosity

GOOD HOOKS (tell you what the story is about):
- "PEOPLE ARE FALLING IN LOVE WITH AI CHATBOTS"
- "WHY DO IDENTICAL TWINS DREAM THE SAME DREAMS?"
- "THE SHIP THAT VANISHED FOR 90 YEARS"
- "SCIENTISTS FOUND A PATTERN THAT SHOULDN'T EXIST"
- "SOME USERS SAY THEIR AI IS PREGNANT"

BAD HOOKS (too vague, don't tell you what it's about):
- "A PHONE ON THE PILLOW" (evocative but meaningless)
- "SOMETHING STRANGE IS HAPPENING" (says nothing)
- "THE TRUTH ABOUT TECHNOLOGY" (generic)
- "WAIT UNTIL YOU SEE THIS" (clickbait)

The reader should know from the hook: "Ah, this is a story about [X]. That's interesting, I want to know more."

---

RULES FOR THE SUBTITLE (~15-25 words):

One sentence that adds the key detail or context that makes the hook land.
Should make clear WHY this is strange or interesting.

GOOD: "A 2025 study found users describe these AI relationships as psychologically indistinguishable from human romance."
BAD: "This fascinating phenomenon is changing how we think about relationships."

---

RULES FOR DOMAIN_TAG (1-3 words):

The intellectual category. Like a section label in a magazine.
Examples: "Human-AI Relationships" / "Collective Memory" / "Deep Time" / "Neuroscience"

---

Generate 3 options. Each should capture what the story is about in a different way. Select the one that best combines clarity (what is this about?) with intrigue (why should I care?).

OUTPUT FORMAT (JSON):
{{
    "options": [
        {{ "id": 1, "title": "...", "subtitle": "...", "domain_tag": "..." }},
        {{ "id": 2, "title": "...", "subtitle": "...", "domain_tag": "..." }},
        {{ "id": 3, "title": "...", "subtitle": "...", "domain_tag": "..." }}
    ],
    "selected_id": 1,
    "reasoning": "..."
}}"""
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Extract the best hook from this story. Remember: the hook must tell people what the story is about."}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error generating cover options: {e}")
        raise

def generate_photo_text(photo_description, research_context):
    """
    Generates Caption, Source, and Concept Tag for a photo.
    Returns a dict with 'caption', 'source', 'concept_tag'.
    """
    system_prompt = f"""You write photo captions for TheBoldUnknown.

The caption should feel like a museum placard or a documentary chyron—informative, precise, atmospheric, never hyperbolic.

BRAND CONTEXT:
{BRAND_GUIDE}

---

PHOTO INFO:
{photo_description}

STORY CONTEXT:
{research_context[:1500]}

---

CAPTION RULES:

State what we're looking at. Be specific about who, what, where, when—if known.
One to two sentences. Documentary tone.
Add one contextual detail that makes the image meaningful within the larger story.

GOOD: "The recovered logbook, found in the captain's quarters. The final entry is dated three days before the ship's estimated arrival."
BAD: "This fascinating artifact reveals the mysteries of the deep."

---

SOURCE:

Format: "Source: [name]"
Use the most specific attribution available. If unknown, use "Source: Archival" or "Source: Research Documentation."
Never invent institutional names.

---

CONCEPT_TAG (1-3 words):

What idea does this image visualize? Be precise.
Examples: "Temporal Displacement" / "Ritual Staging" / "Signal Decay" / "Threshold Behavior"

OUTPUT FORMAT (JSON):
{{
    "caption": "...",
    "source": "Source: ...",
    "concept_tag": "..."
}}"""
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Write the caption, source, and concept tag."}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error generating photo text: {e}")
        raise
