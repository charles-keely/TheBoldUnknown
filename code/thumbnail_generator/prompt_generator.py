"""
Prompt Generator - Uses GPT-5.2 to create creative concepts for thumbnails.
"""

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


def generate_thumbnail_concepts(hook_title, subtitle, domain_tag, research_data):
    """
    Generates 3 creative concepts for thumbnail images.
    
    Args:
        hook_title: The main title (e.g., "WHY DOES DÉJÀ VU FEEL REAL?")
        subtitle: Context sentence
        domain_tag: Topic category (e.g., "Consciousness Studies")
        research_data: Full research context from story_research (dict or string)
    
    Returns:
        dict with 'concepts' list containing 3 concept objects
    """
    
    # Extract research summary if it's a dict
    if isinstance(research_data, dict):
        research_summary = research_data.get('ground_truth', '')
        if not research_summary:
            research_summary = json.dumps(research_data)[:3000]
    else:
        research_summary = str(research_data)[:3000]
    
    system_prompt = f"""You are creating visual concepts for TheBoldUnknown Instagram cover images.

BRAND CONTEXT:
{BRAND_GUIDE[:2000]}

---

COMPOSITION REQUIREMENT (CRITICAL):
The generated image will have text overlaid on the LOWER 45% of the frame:
- Large title text (100px font) in center-lower area
- Subtitle below the title
- Footer with pagination

Therefore:
- ALL major subjects MUST be positioned in the UPPER HALF of the frame
- The lower portion must be visually calm (no faces, focal objects, high-contrast details)
- Think of it like a movie poster where the title goes at the bottom

SAFE ZONES:
- Top-left corner: Leave empty and visually calm (reserved for post-processing)
- Top-right corner: Keep minimal for metadata label
- Lower 45%: NO focal subjects - this is the text zone

---

AESTHETIC REQUIREMENTS:
- Style: Interstellar × Arrival × Scientific Mystery × Calm Esoteric Intelligence
- Backgrounds: Dark or deep-toned (navy, charcoal, deep space, shadows)
- Composition: Minimalistic, poster-like clarity, wide negative space
- Atmosphere: Soft gradients, gentle glows, subtle atmosphere
- Textures: Technical elements welcome (grids, diagrams, telemetry, star maps)
- Mood: Quietly strange, grounded, rational, cinematic
- Lighting: Dramatic but natural, never harsh or neon

AVOID:
- Neon cyberpunk clichés
- Chaotic occult symbolism
- Gore or shock imagery
- Meme aesthetics
- Cartoon or comic book styles
- Overly busy compositions
- ANY text, logos, watermarks, or UI elements in the image

---

YOUR TASK:
Generate 3 distinct creative concepts for a thumbnail image that:
1. Visually represents the core theme/mystery of this story
2. Creates immediate intrigue and curiosity
3. Works as a "movie poster" that makes someone want to read the story
4. Respects the composition constraints (subjects in upper half)

Each concept should take a DIFFERENT visual approach:
- Concept 1 (literal): Documentary-style - specific person, place, object, or scene from the story
- Concept 2 (symbolic): Visual metaphor - abstract representation of the concept/phenomenon
- Concept 3 (atmospheric): Mood-driven - environmental, setting-focused, evocative

OUTPUT FORMAT (JSON):
{{
    "concepts": [
        {{
            "id": 1,
            "concept_type": "literal",
            "scene_description": "Detailed description of what the image depicts",
            "subject_placement": "Where in frame (e.g., 'upper-right third, figure in profile')",
            "key_elements": ["element1", "element2", "element3"],
            "color_palette": ["color1", "color2", "color3"],
            "lighting": "Description of lighting setup and mood",
            "reasoning": "Why this visual represents the story"
        }},
        {{
            "id": 2,
            "concept_type": "symbolic",
            ...
        }},
        {{
            "id": 3,
            "concept_type": "atmospheric",
            ...
        }}
    ]
}}"""

    user_prompt = f"""STORY CONTEXT:
Title: {hook_title}
Subtitle: {subtitle}
Domain: {domain_tag}

Research Summary:
{research_summary}

---

Generate 3 distinct creative concepts for this story's cover image. Remember:
- Subjects must be in the UPPER HALF of the frame
- Lower portion must be visually calm for text overlay
- Dark, cinematic, editorial aesthetic
- No text or logos in the image itself"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        logger.info(f"Generated {len(result.get('concepts', []))} concepts for '{hook_title}'")
        return result
        
    except Exception as e:
        logger.error(f"Error generating thumbnail concepts: {e}")
        raise


def generate_single_concept(hook_title, subtitle, domain_tag, research_data, concept_type="symbolic"):
    """
    Generates a single creative concept of a specific type.
    Useful for regenerating a specific concept.
    
    Args:
        concept_type: "literal", "symbolic", or "atmospheric"
    """
    
    if isinstance(research_data, dict):
        research_summary = research_data.get('ground_truth', '')[:2000]
    else:
        research_summary = str(research_data)[:2000]
    
    concept_descriptions = {
        "literal": "Documentary-style - depict a specific person, place, object, or scene that appears in or relates to the story. Grounded and real.",
        "symbolic": "Visual metaphor - create an abstract or symbolic representation of the core concept/phenomenon. Evocative and interpretive.",
        "atmospheric": "Mood-driven - focus on environment, setting, and atmosphere. Create a space that feels like the story."
    }
    
    system_prompt = f"""You are creating a single visual concept for a TheBoldUnknown Instagram cover image.

CONCEPT TYPE: {concept_type.upper()}
{concept_descriptions.get(concept_type, concept_descriptions["symbolic"])}

COMPOSITION: Subjects in UPPER HALF. Lower 45% must be calm for text overlay.
AESTHETIC: Dark, cinematic, Interstellar × Arrival style. No text/logos in image.

OUTPUT FORMAT (JSON):
{{
    "concept_type": "{concept_type}",
    "scene_description": "Detailed description",
    "subject_placement": "Where in frame",
    "key_elements": ["element1", "element2"],
    "color_palette": ["color1", "color2"],
    "lighting": "Lighting description",
    "reasoning": "Why this works"
}}"""

    user_prompt = f"""Title: {hook_title}
Subtitle: {subtitle}
Domain: {domain_tag}
Research: {research_summary}

Generate a {concept_type} concept for this story's cover image."""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
        
    except Exception as e:
        logger.error(f"Error generating single concept: {e}")
        raise
