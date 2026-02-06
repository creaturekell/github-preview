"""Configuration management for GitHub App."""
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class Config:
    """Application configuration."""
    
    GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
    GITHUB_APP_PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY")
    GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
    PORT = int(os.getenv("PORT", "8000"))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present."""
        required = [cls.GITHUB_APP_ID, cls.GITHUB_APP_PRIVATE_KEY, cls.GITHUB_WEBHOOK_SECRET]
        if not all(required):
            logger.warning("Missing required environment variables. Some features may not work.")
            return False
        return True
