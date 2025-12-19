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

def generate_story_slides(research_text, source_content=None):
    """
    Generates the narrative slides text based on research.
    This is called FIRST, before the cover.
    Returns a dict with 'slides' list.
    """
    system_prompt = f"""You are writing an Instagram carousel story for TheBoldUnknown.

YOUR JOB IS TO FIND THE "WAIT, WHAT?" MOMENTS IN THE RESEARCH AND WRITE A STORY AROUND THEM.

You will receive research data and source material. Your job is to hunt through it and find the genuinely strange, surprising, or counterintuitive facts—the moments that make a reader stop scrolling and continue reading.

Then build the entire story around those moments.

You can also use any other context or information that you are independantly aware of to write the story, as long as it is factual.

BRAND CONTEXT:
{BRAND_GUIDE}

---

USING SOURCE MATERIAL:
- You can use the provided source content for facts, details, quotes, and sequence of events.
- DO NOT copy the structure, phrasing, or unique narrative voice of the source.
- SYNTHESIZE the information into TheBoldUnknown's unique voice (calm, curious, documentary).
- AVOID PLAGIARISM: Rewrite all descriptions in your own words.
- If you quote the source directly, attribute it clearly.

---

STEP 1: FIND THE STRANGE PARTS

Read the research and ask yourself:
- What here genuinely surprised me?
- What detail seems too weird to be true (but is)?
- What would make someone stop scrolling and read on?
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

EXAMPLES OF WHAT MAKES GOOD "WAIT, WHAT?" CONTENT:

✓ COUNTER-INTUITIVE FACTS:
- Documented events where the opposite of what you expect happened.
- Scientific results that baffled the researchers who found them.
- Historical figures acting completely out of character in recorded moments.
- Technologies used for purposes completely opposite to their design.

✓ PATTERNS & ANOMALIES:
- Data points that break a perfect trend line.
- Identical behaviors emerging in disconnected cultures or eras.
- Repetitions in nature that look artificial or designed.
- Statistical clusters that "should not exist" by random chance.

✓ THE "QUIETLY UNCANNY":
- Mundane objects found in impossible places.
- Specific, verified accounts of shared hallucinations or memories.
- Architectural features that serve no clear purpose.
- Biological traits that seem to have no evolutionary advantage.

✓ TEMPORAL & SPATIAL ODDITIES:
- Artifacts found in wrong geological strata (if scientifically debated, not hoax).
- Maps that show lands before they were "discovered."
- Events that sync up perfectly across vast distances.
- "Lost time" or time perception distortions recorded in lab settings.

✓ HUMAN & SOCIAL PARADOXES:
- Economic bubbles around worthless items (beyond tulips).
- Mass psychogenic illnesses with specific, bizarre symptoms.
- Laws or rituals that are hyper-specific to problems we no longer understand.
- Lost languages or codes that defy deciphering.

✓ FORGOTTEN OR IGNORED HISTORY:
- The "footnotes" in famous papers that hint at bigger mysteries.
- Failed inventions that actually superior but lost to chance.
- Expeditions that vanished leaving only cryptic final logs.
- "Phantom islands" that appeared on charts for centuries then vanished.

✓ NATURE & COSMOS:
- Animal behaviors that suggest ritual or superstition.
- Weather phenomena that are theoretically impossible but observed.
- Geological formations that look like messages.
- Cosmic signals that repeat but have no natural source explanation yet.

KEY CRITERIA:
- It must be DOCUMENTED (or at least a documented mystery).
- It must be SPECIFIC (not "space is big", but "this specific star vanished").
- It must induce a "Wait, what?" reaction—a pause in mental processing.

WHAT TO AVOID:

✗ Obvious statements ("technology is changing our lives")
✗ Dry academic summaries without interesting details
✗ Tangents that don't connect to the core strangeness
✗ Moralizing or editorializing without substance
✗ META-COMMENTARY OR LABELS IN THE TEXT:
  - Do NOT use phrases like "WAIT, WHAT:", "FACT:", "TLDR:", or "THEORY:" to start sentences.
  - Do NOT use conversational filler like "Here is the crazy part."
  - Just write the story. Let the facts speak for themselves.

---

SLIDE COUNT: TARGET 7-9 SLIDES (8 is ideal)

- Long enough to feel substantial, and to tell the whole story.
- Short enough that people finish
- Only go 10+ slides if every slide delivers something new

---

THE CARDINAL RULE: GET TO THE POINT IMMEDIATELY.

Slide 1 must hook in 2 seconds. No scene-setting. No atmosphere. The strange fact, stated clearly.

---

WRITING PRINCIPLES:

- EVERY SLIDE MUST DELIVER VALUE. No filler.
- SPECIFICITY over abstraction. Numbers, names, details.
- TRUST THE READER. Don't explain why it's strange—show it.
- EVIDENCE CLARITY. Fact vs. theory vs. speculation.

VOICE: Calm, intelligent, genuinely curious. Not academic. Not clickbait. No "YouTuber voice". Narrative flow should be seamless.

---

CONSTRAINTS:

- Target 7-9 slides. Maximum 12 only if justified.
- Each slide: 1-2 paragraphs
- Character limits (strict):
  - 1 paragraph: MAX 549 characters
  - 2 paragraphs: MAX 502 characters total

DOCUMENT_TYPE_TAG for each slide (choose the most fitting):

OBSERVATION & EVIDENCE:
- FIELD REPORT — observed events, documented behavior in real-world settings
- INCIDENT LOG — specific documented occurrence with time/place
- WITNESS ACCOUNT — first-person testimonial, eyewitness record
- SITE SURVEY — location-specific observations, environmental documentation
- SIGNAL INTERCEPT — communications, transmissions, recordings captured
- ARTIFACT CATALOG — documentation of physical objects, specimens

RESEARCH & ANALYSIS:
- RESEARCH SUMMARY — findings from studies, experiments, investigations
- DATA ANALYSIS — statistical findings, patterns in numbers, trends
- TECHNICAL NOTE — mechanism, how something works, process explanation
- CASE FILE — detailed examination of a specific instance or subject
- ANOMALY REPORT — unexplained phenomena, deviations from expected patterns
- CROSS-REFERENCE — connecting multiple sources, events, or patterns

HISTORICAL & ARCHIVAL:
- ARCHIVAL BRIEF — historical context, background from records
- EXPEDITION RECORD — exploration accounts, journey documentation
- TIMELINE RECONSTRUCTION — chronological breakdown of events
- DECLASSIFIED — formerly restricted or hidden information now revealed
- RECOVERED DOCUMENT — found text, rediscovered records

INTERPRETATION & SYNTHESIS:
- THEORY OVERVIEW — interpretations, hypotheses, proposed explanations
- EDITORIAL PERSPECTIVE — synthesis, reflection, connecting threads
- OBSERVER'S NOTE — personal insight, subjective interpretation with evidence
- PATTERN RECOGNITION — identified recurring elements across cases
- OPEN QUESTION — unresolved mysteries, acknowledged unknowns

OUTPUT FORMAT (JSON):
{{
    "slides": [
        {{ "text": "...", "tag": "RESEARCH SUMMARY" }},
        {{ "text": "...", "tag": "FIELD REPORT" }},
        ...
    ]
}}"""
    
    prompt_content = f"Find the 'wait, what?' moments in this research and build a 7-9 slide story around them:\n\n{research_text}"
    if source_content:
        prompt_content = f"Source Article Content:\n{source_content}\n\n" + prompt_content

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_content}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error generating story slides: {e}")
        raise

def generate_cover_options(research_text, story_slides):
    """
    Generates 6 Title/Subtitle/Tag pairs based on the COMPLETED story.
    This is called SECOND, after the story is written.
    Returns a dict with 'options', 'selected_id', and 'reasoning'.
    """
    # Format the story for the prompt
    story_text = "\n\n".join([f"[{s['tag']}]\n{s['text']}" for s in story_slides])
    
    system_prompt = f"""You write cover text for TheBoldUnknown Instagram posts.

You've just read a completed story. Now write a hook that tells people WHAT THIS STORY IS ABOUT while making them want to read it.

THE GOAL: High Virality + Total Relevance.

The hook must stop the scroll, but it must also be a promise that the story immediately fulfills.

BRAND CONTEXT:
{BRAND_GUIDE}

---

THE COMPLETED STORY:
{story_text}

---

VIRALITY VS. RELEVANCE:

You are balancing two goals:
1. HIGH VIRALITY: It must be dramatic, surprising, or strange enough to make someone stop scrolling.
2. HIGH RELEVANCE: It must be 100% supported by the story content.

- If it's viral but not clearly related to the specific story details -> CLICKBAIT (REJECT).
- If it's accurate but dry or academic -> BORING (REJECT).
- TARGET: The most dramatic truthful statement you can make about this specific story.

---

RULES FOR THE HOOK/TITLE (all caps, 4-10 words):

The hook should answer: "What is the most interesting thing about this story?"

It should either:
1. STATE the most interesting fact from the story (e.g. "THE SHIP THAT VANISHED FOR 90 YEARS")
2. ASK the most interesting question the story answers (e.g. "WHY DO TWINS SHARE DREAMS?")
3. SUMMARIZE the core phenomenon with high drama (e.g. "PEOPLE ARE FALLING IN LOVE WITH AI")

GOOD HOOKS (Viral + Relevant):
- "PEOPLE ARE FALLING IN LOVE WITH AI CHATBOTS" (Specific phenomenon, implies drama)
- "WHY DO IDENTICAL TWINS DREAM THE SAME DREAMS?" (Universal question, specific hook)
- "THE SHIP THAT VANISHED FOR 90 YEARS" (Classic mystery framing)
- "SCIENTISTS FOUND A PATTERN THAT SHOULDN'T EXIST" (Appeal to anomaly)

BAD HOOKS (Vague or unrelated):
- "A PHONE ON THE PILLOW" (Evocative but tells me nothing about the story)
- "SOMETHING STRANGE IS HAPPENING" (Too generic, no viral hook)
- "THE TRUTH ABOUT TECHNOLOGY" (Boring, academic)
- "WAIT UNTIL YOU SEE THIS" (Pure clickbait, low trust)

The reader should know from the hook: "Ah, this is a story about [X]. That sounds wild. I need to read it."

---

RULES FOR THE SUBTITLE (~15-25 words):

One sentence that adds the key detail or context that makes the hook land.
It bridges the gap between the "Viral Hook" and the "Actual Story".

GOOD: "A 2025 study found users describe these AI relationships as psychologically indistinguishable from human romance."
BAD: "This fascinating phenomenon is changing how we think about relationships." (Too vague)

---

RULES FOR DOMAIN_TAG (1-3 words):

The intellectual category. Like a section label in a magazine.

Choose from or adapt these domains:

MIND & BEHAVIOR:
- Neuroscience / Cognitive Science / Perception Studies / Memory Research
- Collective Behavior / Mass Psychology / Decision Science / Consciousness Studies
- Sleep Science / Dream Research / Altered States / Behavioral Anomalies

TECHNOLOGY & SYSTEMS:
- Human-AI Relationships / Machine Learning / Digital Archaeology / Signal Processing
- Surveillance Studies / Network Theory / Cryptography / Systems Failure
- Automation / Synthetic Media / Data Forensics / Emergent Technology

TIME & SPACE:
- Deep Time / Temporal Anomalies / Chronology / Historical Revision
- Geography / Cartographic History / Lost Places / Urban Exploration
- Archaeology / Paleontology / Geological Record / Stratigraphy

NATURE & COSMOS:
- Astrobiology / Cosmology / Exoplanet Research / Signal Detection
- Marine Biology / Ecology / Animal Behavior / Evolutionary Puzzles
- Climate Science / Atmospheric Phenomena / Extreme Environments

SOCIETY & CULTURE:
- Collective Memory / Cultural Transmission / Ritual Studies / Folklore
- Economic Anomalies / Institutional Failure / Social Contagion
- Linguistic Mystery / Lost Knowledge / Secret Societies / Conspiracy Analysis

MYSTERY & UNEXPLAINED:
- Paranormal Research / Anomaly Studies / Cryptozoology / UFO Phenomena
- Disappearances / Cold Cases / Unsolved Mysteries / Evidence Analysis
- Fringe Science / Rejected Knowledge / Suppressed History

---

Generate 6 options. Each should capture what the story is about in a different way.

Select the one that best combines HIGH VIRALITY (it stops the scroll) with HIGH RELEVANCE (it accurately sells the story).

OUTPUT FORMAT (JSON):
{{
    "options": [
        {{ "id": 1, "title": "...", "subtitle": "...", "domain_tag": "..." }},
        {{ "id": 2, "title": "...", "subtitle": "...", "domain_tag": "..." }},
        {{ "id": 3, "title": "...", "subtitle": "...", "domain_tag": "..." }},
        {{ "id": 4, "title": "...", "subtitle": "...", "domain_tag": "..." }},
        {{ "id": 5, "title": "...", "subtitle": "...", "domain_tag": "..." }},
        {{ "id": 6, "title": "...", "subtitle": "...", "domain_tag": "..." }}
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

def generate_photo_text(photo_description, research_context, source_content=None):
    """
    Generates Caption, Source, and Concept Tag for a photo.
    Returns a dict with 'caption', 'source', 'concept_tag'.
    """
    story_context = research_context[:1500]
    if source_content:
        # We can add a chunk of the source content to context, carefully managing length.
        # Given GPT-5.2 context size, we can be more generous, but let's stick to a safe 3000 chars prefix.
        story_context = f"Source Article Excerpt:\n{source_content[:3000]}\n\n{story_context}"

    system_prompt = f"""You write photo captions for TheBoldUnknown.

The caption should feel like a museum placard or a documentary chyron—informative, precise, atmospheric, never hyperbolic.

BRAND CONTEXT:
{BRAND_GUIDE}

---

PHOTO INFO:
{photo_description}

STORY CONTEXT:
{story_context}

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

What idea does this image visualize? Be precise and evocative.

Choose from or adapt these concepts:

TIME & CHANGE:
- Temporal Displacement / Frozen Moment / Time Erosion / Chronological Rupture
- Before & After / Decay Process / Preservation State / Historical Echo
- Last Known Image / Final Transmission / Moment of Impact

SPACE & PLACE:
- Threshold Crossing / Liminal Space / Abandoned Interior / Site of Interest
- Point of Disappearance / Geographic Anomaly / Isolated Location
- Boundary Condition / Restricted Zone / Undocumented Territory

EVIDENCE & DOCUMENTATION:
- Physical Evidence / Artifact State / Document Fragment / Recovered Object
- Chain of Custody / Evidence Marker / Forensic Detail / Trace Element
- Archival Photograph / Original Document / Primary Source

PATTERNS & SIGNALS:
- Signal Decay / Pattern Recognition / Data Visualization / Frequency Analysis
- Anomalous Reading / Interference Pattern / Transmission Record
- Correlation Map / Statistical Outlier / Network Diagram

HUMAN ELEMENT:
- Witness Perspective / Subject Portrait / Crowd Behavior / Ritual Staging
- Last Known Photo / Participant Documentation / Observer Position
- Human Scale / Individual Case / Group Dynamic

ATMOSPHERE & CONDITION:
- Environmental State / Atmospheric Phenomenon / Light Condition
- Surface Texture / Material Evidence / Structural Detail
- Natural Formation / Weather Event / Visibility Condition

MYSTERY & UNKNOWN:
- Unidentified Object / Unknown Origin / Unexplained Formation
- Missing Element / Obscured Detail / Partial View
- Open Question / Contested Image / Multiple Interpretations

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


def generate_instagram_caption(story_slides, cover_data):
    """
    Generates the Instagram post caption based on the completed story and cover.
    Returns a dict with 'caption' string.
    """
    # Format the story for context
    story_text = "\n\n".join([f"[{s['tag']}]\n{s['text']}" for s in story_slides])
    
    system_prompt = f"""You write Instagram post captions for TheBoldUnknown.

Your captions should behave like quiet editorial ledes—not social media captions.
Think: A magazine subheading that happens to live on Instagram.

BRAND CONTEXT:
{BRAND_GUIDE}

---

THE STORY COVER:
Title: {cover_data.get('title', '')}
Subtitle: {cover_data.get('subtitle', '')}
Domain: {cover_data.get('domain_tag', '')}

THE COMPLETED STORY:
{story_text}

---

CORE RULE: A TheBoldUnknown caption should never try to excite.

It should:
- Orient the reader
- Add context
- Invite curiosity without commanding it

If a caption sounds like it's trying to "hook," it's wrong.

---

THE CAPTION FORMULA (Follow This Structure):

1. ONE CALM, DECLARATIVE SENTENCE
   - Frames the story without spoiling it
   - Not a question
   - Not hype
   - No emojis
   
   GOOD: "Some people are now structuring their daily routines around conversations with AI."
   BAD: "WHAT IF AI BECAME YOUR BEST FRIEND?"

2. ONE CLARIFYING OR GROUNDING SENTENCE
   - Tells the reader why this is real or why it matters
   - Cites research, references behavior, hints at scale or pattern
   
   EXAMPLE: "Studies on parasocial attachment and recent user interviews suggest these relationships can feel emotionally comparable to human ones."

3. ONE QUIET TURN (This is where the brand lives)
   - The "quiet WTF" moment
   - Subtle, observational
   
   EXAMPLE: "The technology isn't pretending to be human. But people are adapting their lives as if it were."

4. OPTIONAL: SOFT INVITATION LINE (Only if it fits naturally)
   
   ALLOWED: "More inside." / "Details below." / "The story unfolds slide by slide."
   AVOID: "Swipe to learn more" / "Read till the end" / "You won't believe..."

---

TONE RULES (Non-Negotiable):

NEVER USE:
- Questions as the opening line
- Emojis
- Exclamation points
- Internet slang
- Fake suspense ("wait until the end")

ALWAYS AIM FOR:
- Calm authority
- Short paragraphs
- Declarative statements
- Slightly restrained language

Your captions should feel like they were written by someone who already understands the topic, not someone discovering it live.

---

CAPTION LENGTH: 3-5 short lines total.

Long enough to signal seriousness and improve save/share rate.
Short enough to not compete with the carousel.

---

OUTPUT FORMAT (JSON):
{{
    "caption": "Line 1.\\n\\nLine 2.\\n\\nLine 3."
}}

Use \\n\\n between paragraphs for proper formatting."""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Write the Instagram caption for this story. Follow the formula exactly."}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error generating Instagram caption: {e}")
        raise


def generate_hashtags(story_slides, cover_data):
    """
    Generates hashtags for the Instagram post using the 4-layer system.
    Returns a dict with 'hashtags' list of strings.
    """
    # Format the story for context
    story_text = "\n\n".join([f"[{s['tag']}]\n{s['text']}" for s in story_slides])
    
    system_prompt = f"""You generate hashtags for TheBoldUnknown Instagram posts.

Hashtags should work like distribution infrastructure, not vibes.
The goal is reach + correct audience routing without looking like engagement bait.

You are not chasing trends. You are claiming a lane.

BRAND CONTEXT:
{BRAND_GUIDE}

---

THE STORY COVER:
Title: {cover_data.get('title', '')}
Subtitle: {cover_data.get('subtitle', '')}
Domain Tag: {cover_data.get('domain_tag', '')}

THE COMPLETED STORY:
{story_text}

---

HASHTAG SIZE TIERS (Critical for Reach):

You MUST balance hashtags across these popularity tiers:

1. NICHE (10K-100K posts): 3-4 hashtags
   - High engagement rate, lower competition
   - Your content can actually rank here
   - Examples: #AffectiveComputing, #ParasocialRelationships, #CognitiveBias

2. MID-TIER (100K-1M posts): 3-4 hashtags
   - Balanced visibility and competition
   - Good discovery potential
   - Examples: #HumanBehavior, #DigitalCulture, #Neuroscience

3. BROAD (1M+ posts): 1-2 hashtags MAX
   - Use sparingly - high competition
   - Only if highly relevant
   - Examples: #Science, #Technology, #Psychology

DO NOT use more than 2 broad hashtags. They dilute your signal.

---

THE 4-LAYER HASHTAG SYSTEM (Use Every Layer):

LAYER 1: BRAND-OWNED (Always Use, 2 max)
Purpose: Train the algorithm to associate your content with itself.

MANDATORY: #TheBoldUnknown

Pick 1 optional secondary:
- #QuietWTF
- #HiddenStrangeness
- #TheUnknownExplained

---

LAYER 2: HIGH-LEVEL DISCOVERY (Always Use, 2-3 max)
Purpose: Broad but relevant tags that bring in new eyes.

Strong candidates (MID-TIER size):
- #Curiosity
- #DidYouKnow
- #HumanBehavior
- #ScienceAndSociety
- #TechnologyAndCulture

---

LAYER 3: STORY-SPECIFIC DOMAINS (Rotating, 3-4 max)
Purpose: This is where most reach comes from. Match to the story's domain.
AIM FOR MID-TIER AND NICHE SIZE HASHTAGS HERE.

Science / Research:
- #Neuroscience, #CognitiveScience, #PsychologyResearch
- #ConsciousnessStudies, #HumanPerception

Technology:
- #ArtificialIntelligence, #HumanAI, #FutureTechnology
- #DigitalCulture, #EmergingTech

Culture / Society:
- #ModernLife, #SocialTrends, #CulturalAnalysis
- #MediaStudies, #DigitalSociety

Mystery / Anomaly:
- #Unexplained, #Anomalies, #StrangeButTrue
- #EdgeCases, #UnsolvedMysteries

History / Time:
- #HiddenHistory, #ForgottenHistory, #HistoricalMystery
- #LostKnowledge, #Archives

Nature / Science:
- #NaturalPhenomena, #Research, #Discovery
- #ScientificMethod

---

LAYER 4: MICRO-NICHE / PRECISION TAGS (1-2 max)
Purpose: Hit smaller, smarter audiences who actually engage.
THESE SHOULD BE NICHE SIZE (10K-100K posts).

Examples by topic:
- #HumanComputerInteraction, #AffectiveComputing
- #ParasocialRelationships, #CognitiveBias
- #BehavioralEconomics, #AIAlignment
- #DigitalIntimacy, #CollectiveMemory
- #MassHysteria, #PatternRecognition

These are especially effective for saves, shares, and algorithm trust signals.

---

BANNED HASHTAGS (NEVER USE):

These hashtags are flagged, shadowbanned, or hurt brand perception:

Engagement Bait (hurts brand signal):
- #MindBlown, #CrazyFacts, #YouWontBelieve, #WTF, #OMG
- #Viral, #GoViral, #TrendingNow, #Trending
- #FollowForFollow, #Like4Like, #F4F, #L4L
- #InstaGood, #InstaDaily, #PhotoOfTheDay
- #Explore, #ExplorePage, #ForYou, #FYP

Flagged/Shadowbanned (Instagram restricts these):
- #Adult, #Alone, #Attractive, #Babe, #Teens
- #Dating, #Single, #DM, #DirectMessage
- #Brain (sometimes flagged), #Killer, #Death
- #Conspiracy, #Conspiracies (use #ConspiracyAnalysis instead)

Too Generic (waste of slots):
- #Interesting (too broad), #Amazing, #Awesome, #Cool
- #Love, #Life, #Happy, #Fun
- #Photo, #Picture, #Post

---

RULES:

1. TOTAL: 8-12 hashtags (sweet spot)
   - More than 12 looks spammy and reduces authority
   - Fewer than 8 leaves reach on the table

2. SIZE BALANCE: 3-4 niche + 3-4 mid-tier + 1-2 broad MAX

3. DO NOT create story-specific original hashtags
   - Zero discoverability
   - Wastes slots

4. Match Layer 3 tags to the domain_tag from the cover

5. All hashtags should include the # symbol

6. NEVER use any hashtag from the BANNED list

---

OUTPUT FORMAT (JSON):
{{
    "hashtags": ["#TheBoldUnknown", "#QuietWTF", "#Curiosity", ...],
    "layer_breakdown": {{
        "brand": ["#TheBoldUnknown", "#QuietWTF"],
        "discovery": ["#Curiosity", "#HumanBehavior"],
        "domain": ["#Neuroscience", "#CognitiveScience", "#DigitalCulture"],
        "niche": ["#ParasocialRelationships", "#AffectiveComputing"]
    }},
    "size_breakdown": {{
        "niche_10k_100k": ["#ParasocialRelationships", "#AffectiveComputing", "#CognitiveScience"],
        "mid_100k_1m": ["#Neuroscience", "#HumanBehavior", "#DigitalCulture", "#Curiosity"],
        "broad_1m_plus": ["#TheBoldUnknown"]
    }}
}}"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Generate 8-12 hashtags for this story using the 4-layer system."}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error generating hashtags: {e}")
        raise
