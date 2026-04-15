"""
Dynamic Personality Engine for Jennifer Bot.
Loads bot personalities and system prompts from YAML/Markdown files.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PersonalityManager:
    """Manages dynamic loading of bot personas."""
    
    def __init__(self, profiles_dir: str = "data/personalities"):
        self.profiles_dir = Path(profiles_dir)
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.load_all()

    def load_all(self):
        """Load all personality profiles from disk."""
        self.profiles.clear()
        
        for file_path in self.profiles_dir.glob("*.yaml"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    
                if data and "name" in data:
                    name = data["name"].lower()
                    self.profiles[name] = data
                    logger.debug(f"Loaded personality: {name}")
            except Exception as e:
                logger.error(f"Failed to load personality {file_path.name}: {e}")
                
        logger.info(f"Loaded {len(self.profiles)} personality profiles.")

    def get_personality(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific personality profile by name."""
        return self.profiles.get(name.lower())

    def get_system_prompt(self, name: str, default: str = "") -> str:
        """Construct the full system prompt for a persona."""
        profile = self.get_personality(name)
        if not profile:
            return default
            
        prompt = profile.get("system_prompt", default)
        
        # Optionally append dynamic instructions based on traits
        traits = profile.get("traits", [])
        if traits:
            prompt += f"\n\nPersonality Traits: {', '.join(traits)}"
            
        return prompt

# Global instance
personality_manager = PersonalityManager()
