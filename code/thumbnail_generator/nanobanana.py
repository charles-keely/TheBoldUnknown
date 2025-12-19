"""
Nano Banana Client - Google Gemini Image Generation API.

Nano Banana = Gemini 2.5 Flash Image (fast)
Nano Banana Pro = Gemini 3 Pro Image Preview (advanced, 4K support)
"""

import os
import logging
import base64
import urllib.request
import urllib.parse
import urllib.error
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

    def _iter_response_parts(self, response):
        """
        Best-effort extraction of parts from google-genai responses.

        The SDK may expose parts at response.parts, or nested under
        response.candidates[i].content.parts depending on modality/model/version.
        """
        parts = getattr(response, "parts", None)
        if parts:
            return parts

        candidates = getattr(response, "candidates", None)
        if not candidates:
            return []

        for cand in candidates:
            content = getattr(cand, "content", None)
            cand_parts = getattr(content, "parts", None) if content else None
            if cand_parts:
                return cand_parts

        return []

    def _upload_bytes_to_supabase(self, *, data: bytes, content_type: str, object_path: str) -> str:
        """
        Upload bytes to Supabase Storage and return a public URL.
        Requires SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to be set.
        """
        if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
            raise ValueError("Supabase storage not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing)")
        if not config.SUPABASE_STORAGE_PUBLIC:
            raise ValueError("SUPABASE_STORAGE_PUBLIC=false is not supported yet (would require signed URLs)")

        bucket = config.SUPABASE_STORAGE_BUCKET
        # Encode object path but keep slashes.
        encoded_path = urllib.parse.quote(object_path.lstrip("/"), safe="/-_.~")

        put_url = f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{encoded_path}"
        public_url = f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{bucket}/{encoded_path}"

        req = urllib.request.Request(
            put_url,
            data=data,
            method="PUT",
            headers={
                "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
                "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
                "Content-Type": content_type or "application/octet-stream",
                "x-upsert": "true",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                # Body is usually json; we don't need it.
                _ = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            raise RuntimeError(f"Supabase upload failed: HTTP {e.code} {e.reason} - {body[:300]}") from e

        return public_url
    
    def generate_image(self, prompt, *, object_path: str):
        """
        Generate an image from a text prompt.
        
        Args:
            prompt: The text prompt for image generation
            object_path: Storage object path (e.g. "<generation_id>/c1.png")
        
        Returns:
            dict with:
              - success: bool
              - image_url: str|None (public URL or data URL)
              - image_base64: str|None (only for db_base64 mode; raw base64 without data: prefix)
              - error: str|None
              - storage_mode: str
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
            parts = self._iter_response_parts(response)
            for part in parts:
                if part.inline_data is not None:
                    # Prefer raw bytes from inline_data (avoids filesystem entirely)
                    mime_type = getattr(part.inline_data, "mime_type", None) or "image/png"
                    raw = getattr(part.inline_data, "data", None)
                    if raw is None:
                        raise ValueError("Model returned inline_data without bytes")
                    if isinstance(raw, str):
                        image_bytes = base64.b64decode(raw)
                    else:
                        image_bytes = bytes(raw)

                    storage_mode = config.resolved_storage_mode()
                    if storage_mode == "supabase":
                        image_url = self._upload_bytes_to_supabase(
                            data=image_bytes,
                            content_type=mime_type,
                            object_path=object_path,
                        )
                        logger.info(f"Image uploaded: {image_url}")
                        return {
                            "success": True,
                            "image_url": image_url,
                            "image_base64": None,  # stored remotely
                            "mime_type": mime_type,
                            "storage_mode": "supabase",
                            "error": None,
                        }

                    if storage_mode == "db_base64":
                        b64 = base64.b64encode(image_bytes).decode("ascii")
                        # NOTE: We deliberately do NOT create any local files.
                        return {
                            "success": True,
                            "image_url": None,
                            "image_base64": b64,
                            "mime_type": mime_type,
                            "storage_mode": "db_base64",
                            "error": None,
                        }

                    return {
                        "success": False,
                        "image_url": None,
                        "image_base64": None,
                        "mime_type": mime_type,
                        "storage_mode": storage_mode,
                        "error": f"Unsupported storage mode: {storage_mode}",
                    }
            
            # No image in response
            logger.warning("No image found in response")
            return {
                'success': False,
                'image_url': None,
                'image_base64': None,
                'mime_type': None,
                'storage_mode': config.resolved_storage_mode(),
                'error': "No image generated in response"
            }
            
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return {
                'success': False,
                'image_url': None,
                'image_base64': None,
                'mime_type': None,
                'storage_mode': config.resolved_storage_mode(),
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
            logger.info(f"Generating image {i}/{len(prompts)}...")
            result = self.generate_image(prompt, object_path=f"{prefix}/{timestamp}/c{i}.png")
            result['concept_number'] = i
            results.append(result)
        
        successful = sum(1 for r in results if r['success'])
        logger.info(f"Batch complete: {successful}/{len(prompts)} images generated")
        
        return results
    
    def generate_with_text(self, prompt, *, object_path: str):
        """
        Generate an image and return any accompanying text from the model.
        
        Args:
            prompt: The text prompt for image generation
            object_path: Storage object path (e.g. "<generation_id>/c1.png")
        
        Returns:
            dict with 'success', 'image_url', 'image_base64', 'text', 'error'
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
                'image_url': None,
                'image_base64': None,
                'text': None,
                'error': None
            }
            
            parts = self._iter_response_parts(response)
            for part in parts:
                if part.text is not None:
                    result['text'] = part.text
                    logger.info(f"Received text: {part.text[:100]}...")
                elif part.inline_data is not None:
                    mime_type = getattr(part.inline_data, "mime_type", None) or "image/png"
                    raw = getattr(part.inline_data, "data", None)
                    if raw is None:
                        raise ValueError("Model returned inline_data without bytes")
                    if isinstance(raw, str):
                        image_bytes = base64.b64decode(raw)
                    else:
                        image_bytes = bytes(raw)

                    storage_mode = config.resolved_storage_mode()
                    if storage_mode == "supabase":
                        image_url = self._upload_bytes_to_supabase(
                            data=image_bytes,
                            content_type=mime_type,
                            object_path=object_path,
                        )
                        result["success"] = True
                        result["image_url"] = image_url
                        result["mime_type"] = mime_type
                    elif storage_mode == "db_base64":
                        result["success"] = True
                        result["image_base64"] = base64.b64encode(image_bytes).decode("ascii")
                        result["mime_type"] = mime_type
                    else:
                        result["error"] = f"Unsupported storage mode: {storage_mode}"
            
            if not result['success']:
                result['error'] = "No image generated in response"
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return {
                'success': False,
                'image_url': None,
                'image_base64': None,
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
        save_path: Ignored (kept for backwards compatibility)
    
    Returns:
        dict with 'success', 'image_url'/'image_base64', 'error'
    """
    client = NanoBananaClient(use_pro=use_pro)
    # Backwards-compatible convenience: store under a timestamped object path.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return client.generate_image(prompt, object_path=f"adhoc/{timestamp}.png")
