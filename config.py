import os
from dotenv import load_dotenv

# Anthropic API client configuration
ANTHROPIC_API_KEY = "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"
ANTHROPIC_MODEL = "claude-3-7-sonnet-20250219"


load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    ALLOWED_EXTENSIONS = {'json', 'xml', 'html', 'jtl'}

    @staticmethod
    def init_app(app):
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)