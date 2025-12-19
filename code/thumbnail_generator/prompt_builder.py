"""
Prompt Builder - Assembles final Nano Banana prompts from creative concepts + constraints.
"""

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Static dimensional constraints block
DIMENSIONAL_CONSTRAINTS = """
IMAGE FORMAT AND COMPOSITION CONSTRAINTS:

• Canvas size: 1080 × 1350 pixels (vertical editorial layout, 4:5 aspect ratio).
• Subject placement: Keep all major subjects positioned in the upper half or upper-right third of the frame.
• Lower safe zone: Avoid placing faces, focal objects, or high-contrast details in the lower 45% of the image.
• Center-lower region: Maintain clean negative space for large headline typography.
• Top-left corner: Keep visually calm for a circular logo overlay (90px diameter).
• Top-right corner: Keep minimally detailed for a small metadata label.
• Background style: Cinematic, grounded, and editorial — not busy or cluttered.
• Lighting: Should guide the eye away from text-safe zones and toward the subject.
• Restrictions: NO text, NO logos, NO watermarks, NO UI elements, NO embedded typography.
"""

# Static brand aesthetic rules block
BRAND_AESTHETIC = """
VISUAL AESTHETIC (TheBoldUnknown Brand):

• Style: Interstellar × Arrival × Scientific Mystery × Calm Esoteric Intelligence
• Backgrounds: Dark or deep-toned (navy, charcoal, deep space, shadows)
• Composition: Minimalistic, poster-like clarity, wide negative space
• Atmosphere: Soft gradients, gentle glows, subtle atmosphere
• Textures: Technical elements welcome (grids, diagrams, telemetry, star maps, architectural drawings)
• Mood: Quietly strange, grounded, rational, cinematic
• Lighting: Dramatic but natural, never harsh or neon

AVOID:
• Neon cyberpunk clichés
• Chaotic occult symbolism
• Gore or shock imagery
• Meme aesthetics
• Cartoon or comic book styles
• Overly busy compositions
• Cluttered backgrounds
"""


def build_prompt(concept):
    """
    Builds a complete Nano Banana prompt from a creative concept.
    
    Args:
        concept: dict with scene_description, subject_placement, key_elements, 
                 color_palette, lighting, etc.
    
    Returns:
        str: Complete prompt ready for Nano Banana API
    """
    
    # Extract concept fields with defaults
    scene_description = concept.get('scene_description', '')
    subject_placement = concept.get('subject_placement', 'Upper half of frame')
    key_elements = concept.get('key_elements', [])
    color_palette = concept.get('color_palette', [])
    lighting = concept.get('lighting', 'Dramatic cinematic lighting')
    
    # Format lists as readable strings
    if isinstance(key_elements, list):
        key_elements_str = '\n'.join(f"• {elem}" for elem in key_elements)
    else:
        key_elements_str = str(key_elements)
    
    if isinstance(color_palette, list):
        color_palette_str = ', '.join(color_palette)
    else:
        color_palette_str = str(color_palette)
    
    # Build the prompt
    prompt = f"""{scene_description}

SUBJECT FRAMING:
{subject_placement}
Rule-of-thirds composition. Avoid dead-center placement.
Subject should feel observed, candid, or documentary in tone.

KEY VISUAL ELEMENTS:
{key_elements_str}

COLOR PALETTE:
{color_palette_str}

LIGHTING:
{lighting}

---
{DIMENSIONAL_CONSTRAINTS}
---
{BRAND_AESTHETIC}
"""
    
    logger.info(f"Built prompt ({len(prompt)} chars)")
    return prompt.strip()


def build_simple_prompt(concept):
    """
    Builds a more concise prompt for Nano Banana.
    Use this if the full prompt is too verbose for the model.
    
    Args:
        concept: dict with scene_description, subject_placement, etc.
    
    Returns:
        str: Concise prompt
    """
    
    scene_description = concept.get('scene_description', '')
    subject_placement = concept.get('subject_placement', 'Upper half of frame')
    color_palette = concept.get('color_palette', [])
    lighting = concept.get('lighting', 'Dramatic cinematic lighting')
    
    if isinstance(color_palette, list):
        color_palette_str = ', '.join(color_palette)
    else:
        color_palette_str = str(color_palette)
    
    prompt = f"""{scene_description}

Composition: {subject_placement}. Rule-of-thirds, subject in upper half of frame. Lower 45% should be visually calm (no faces or focal objects) to allow for text overlay.

Color palette: {color_palette_str}
Lighting: {lighting}

Style: Cinematic, dark, atmospheric. Interstellar × Arrival aesthetic. Minimalist composition with wide negative space. No text, logos, or watermarks. Photorealistic quality."""
    
    logger.info(f"Built simple prompt ({len(prompt)} chars)")
    return prompt.strip()


def build_prompt_batch(concepts):
    """
    Builds prompts for multiple concepts.
    
    Args:
        concepts: list of concept dicts
    
    Returns:
        list of prompt strings
    """
    return [build_prompt(concept) for concept in concepts]
