"""
Content-Addressable Storage (CAS) for generated images.
Hashes prompts and parameters to serve cached images instantly.
"""

import hashlib
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class ImageCache:
    """Manages disk-based caching of generated images."""
    
    def __init__(self, cache_dir: str = "data/image_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _generate_hash(self, prompt: str, params: Dict[str, Any]) -> str:
        """Generate a SHA-256 hash based on prompt and generation parameters."""
        # Normalize prompt
        normalized_prompt = prompt.strip().lower()
        
        # Create a deterministic dictionary of inputs
        cache_key_data = {
            "prompt": normalized_prompt,
            "params": params
        }
        
        # Serialize with sorted keys for consistency
        key_str = json.dumps(cache_key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    def get_cached_image(self, prompt: str, params: Dict[str, Any]) -> Optional[Path]:
        """Return the path to a cached image if it exists."""
        img_hash = self._generate_hash(prompt, params)
        cached_path = self.cache_dir / f"{img_hash}.png"
        
        if cached_path.exists():
            logger.info(f"Image cache hit for prompt: '{prompt[:30]}...'")
            return cached_path
        return None

    def save_to_cache(self, source: Any, prompt: str, params: Dict[str, Any]) -> Path:
        """Save a newly generated image to the cache. Supports PIL Image or Path."""
        # Periodic cleanup check
        self._maybe_cleanup()
        
        img_hash = self._generate_hash(prompt, params)
        cached_path = self.cache_dir / f"{img_hash}.png"
        
        try:
            if hasattr(source, "save"):
                source.save(cached_path)
            else:
                shutil.copy2(source, cached_path)
            logger.debug(f"Saved image to cache: {cached_path.name}")
        except Exception as e:
            logger.error(f"Failed to cache image: {e}")
            
        return cached_path

    def _maybe_cleanup(self, max_files: int = 1000):
        """Simple cleanup to prevent unbounded growth."""
        try:
            files = sorted(self.cache_dir.glob("*.png"), key=lambda x: x.stat().st_mtime)
            if len(files) > max_files:
                to_delete = files[:len(files) - max_files]
                for f in to_delete:
                    f.unlink()
                logger.info(f"Cleaned up {len(to_delete)} old images from cache.")
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")

# Global instance
image_cache = ImageCache()
