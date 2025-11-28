import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET = os.getenv('SECRET')
    EMAIL = os.getenv('EMAIL')

    # Primary API configuration (AIPIPE)
    AIPIPE_API_KEY = os.getenv('AIPIPE_API_KEY')
    AIPIPE_BASE_URL = os.getenv('AIPIPE_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/')

    # Secondary API configuration (Direct Gemini or another provider)
    AIPIPE_API_KEY_2 = os.getenv('AIPIPE_API_KEY_2')
    AIPIPE_BASE_URL_2 = os.getenv('AIPIPE_BASE_URL_2', 'https://generativelanguage.googleapis.com/v1beta/openai/')

    PORT = int(os.getenv('PORT', 5000))

    @classmethod
    def get_api_configs(cls):
        """Get list of available API configurations (key + base_url pairs)"""
        configs = []
        if cls.AIPIPE_API_KEY:
            configs.append({
                'api_key': cls.AIPIPE_API_KEY,
                'base_url': cls.AIPIPE_BASE_URL,
                'name': 'Primary'
            })
        if cls.AIPIPE_API_KEY_2:
            configs.append({
                'api_key': cls.AIPIPE_API_KEY_2,
                'base_url': cls.AIPIPE_BASE_URL_2,
                'name': 'Secondary'
            })
        return configs

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
