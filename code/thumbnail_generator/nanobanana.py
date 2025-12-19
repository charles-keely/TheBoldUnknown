"""
Nano Banana Client - Google Gemini Image Generation API.

Nano Banana = Gemini 2.5 Flash Image (fast)
Nano Banana Pro = Gemini 3 Pro Image Preview (advanced, 4K support)
"""

import os
import logging
import base64
from datetime import datetime
from google import genai
from google.genai import types

from config import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NanoBananaClient:
    """Client for Google Gemini Image Generation (Nano Banana)."""
    
    def __init__(self, use_pro=False):
        """
        Initialize the Nano Banana client.
        
        Args:
            use_pro: If True, use Gemini 3 Pro (advanced). Otherwise use Gemini 2.5 Flash (fast).
        """
        api_key = config.GOOGLE_API_KEY
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")
        
        self.client = genai.Client(api_key=api_key)
        self.model = config.IMAGE_MODEL_PRO if use_pro else config.IMAGE_MODEL
        self.aspect_ratio = config.IMAGE_ASPECT_RATIO
        self.image_size = config.IMAGE_SIZE if use_pro else None  # Only Pro supports image_size
        self.output_dir = config.OUTPUT_DIR
        
        logger.info(f"Initialized Nano Banana client with model: {self.model}")
    
    def generate_image(self, prompt, save_path=None):
        """
        Generate an image from a text prompt.
        
        Args:
            prompt: The text prompt for image generation
            save_path: Optional path to save the image. If None, saves to output_dir.
        
        Returns:
            dict with 'success', 'image_path', 'error' (if any)
        """
        try:
            logger.info(f"Generating image with {self.model}...")
            logger.debug(f"Prompt: {prompt[:200]}...")
            
            # Build config based on model
            if self.model == config.IMAGE_MODEL_PRO and self.image_size:
                image_config = types.ImageConfig(
                    aspect_ratio=self.aspect_ratio,
                    image_size=self.image_size
                )
            else:
                image_config = types.ImageConfig(
                    aspect_ratio=self.aspect_ratio
                )
            
            gen_config = types.GenerateContentConfig(
                response_modalities=['IMAGE'],
                image_config=image_config
            )
            
            # Generate
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt],
                config=gen_config
            )
            
            # Process response
            for part in response.parts:
                if part.inline_data is not None:
                    # Get image from response
                    image = part.as_image()
                    
                    # Generate save path if not provided
                    if not save_path:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        save_path = os.path.join(self.output_dir, f"thumbnail_{timestamp}.png")
                    
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    
                    # Save image
                    image.save(save_path)
                    logger.info(f"Image saved to {save_path}")
                    
                    return {
                        'success': True,
                        'image_path': save_path,
                        'error': None
                    }
            
            # No image in response
            logger.warning("No image found in response")
            return {
                'success': False,
                'image_path': None,
                'error': "No image generated in response"
            }
            
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return {
                'success': False,
                'image_path': None,
                'error': str(e)
            }
    
    def generate_batch(self, prompts, prefix="thumbnail"):
        """
        Generate multiple images from a list of prompts.
        
        Args:
            prompts: List of text prompts
            prefix: Filename prefix for saved images
        
        Returns:
            list of result dicts
        """
        results = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for i, prompt in enumerate(prompts, 1):
            save_path = os.path.join(
                self.output_dir, 
                f"{prefix}_{timestamp}_{i}.png"
            )
            
            logger.info(f"Generating image {i}/{len(prompts)}...")
            result = self.generate_image(prompt, save_path)
            result['concept_number'] = i
            results.append(result)
        
        successful = sum(1 for r in results if r['success'])
        logger.info(f"Batch complete: {successful}/{len(prompts)} images generated")
        
        return results
    
    def generate_with_text(self, prompt, save_path=None):
        """
        Generate an image and return any accompanying text from the model.
        
        Args:
            prompt: The text prompt for image generation
            save_path: Optional path to save the image
        
        Returns:
            dict with 'success', 'image_path', 'text', 'error'
        """
        try:
            logger.info(f"Generating image with text response using {self.model}...")
            
            if self.model == config.IMAGE_MODEL_PRO and self.image_size:
                image_config = types.ImageConfig(
                    aspect_ratio=self.aspect_ratio,
                    image_size=self.image_size
                )
            else:
                image_config = types.ImageConfig(
                    aspect_ratio=self.aspect_ratio
                )
            
            gen_config = types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE'],
                image_config=image_config
            )
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt],
                config=gen_config
            )
            
            result = {
                'success': False,
                'image_path': None,
                'text': None,
                'error': None
            }
            
            for part in response.parts:
                if part.text is not None:
                    result['text'] = part.text
                    logger.info(f"Received text: {part.text[:100]}...")
                elif part.inline_data is not None:
                    image = part.as_image()
                    
                    if not save_path:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        save_path = os.path.join(self.output_dir, f"thumbnail_{timestamp}.png")
                    
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    image.save(save_path)
                    
                    result['success'] = True
                    result['image_path'] = save_path
                    logger.info(f"Image saved to {save_path}")
            
            if not result['success']:
                result['error'] = "No image generated in response"
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return {
                'success': False,
                'image_path': None,
                'text': None,
                'error': str(e)
            }


# Convenience function
def generate_thumbnail(prompt, use_pro=False, save_path=None):
    """
    Simple function to generate a single thumbnail.
    
    Args:
        prompt: The text prompt
        use_pro: Use Nano Banana Pro (Gemini 3 Pro)
        save_path: Optional save path
    
    Returns:
        dict with 'success', 'image_path', 'error'
    """
    client = NanoBananaClient(use_pro=use_pro)
    return client.generate_image(prompt, save_path)
