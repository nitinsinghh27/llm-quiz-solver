import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET = os.getenv('SECRET')
    EMAIL = os.getenv('EMAIL')
    AIPIPE_API_KEY = os.getenv('AIPIPE_API_KEY')
    AIPIPE_API_KEY_2 = os.getenv('AIPIPE_API_KEY_2')  # Optional second API key
    AIPIPE_BASE_URL = os.getenv('AIPIPE_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/')
    PORT = int(os.getenv('PORT', 5000))

    @classmethod
    def get_api_keys(cls):
        """Get list of available API keys"""
        keys = []
        if cls.AIPIPE_API_KEY:
            keys.append(cls.AIPIPE_API_KEY)
        if cls.AIPIPE_API_KEY_2:
            keys.append(cls.AIPIPE_API_KEY_2)
        return keys

    @classmethod
    def validate(cls):
        """Validate that all required config values are set"""
        if not cls.SECRET:
            raise ValueError("SECRET not set in .env file")
        if not cls.EMAIL:
            raise ValueError("EMAIL not set in .env file")
        if not cls.AIPIPE_API_KEY:
            raise ValueError("AIPIPE_API_KEY not set in .env file")
        return True
