import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET = os.getenv('SECRET')
    EMAIL = os.getenv('EMAIL')
    AIPIPE_API_KEY = os.getenv('AIPIPE_API_KEY')
    AIPIPE_BASE_URL = os.getenv('AIPIPE_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/')
    PORT = int(os.getenv('PORT', 5000))

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
