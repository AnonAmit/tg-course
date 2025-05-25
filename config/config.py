import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the absolute path to the project directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Telegram Bot Configuration
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Admin Panel Configuration
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')  # Change in production

# Uploads folder
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database Configuration
# For Heroku Postgres, use the DATABASE_URL environment variable
DATABASE_URL = os.getenv('DATABASE_URL')
# If using Heroku Postgres, update the URL to work with SQLAlchemy
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
# Fallback to SQLite if no DATABASE_URL is provided
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"

# Bot Settings
WELCOME_MESSAGE = os.getenv('WELCOME_MESSAGE', 'Welcome to the Course Delivery Bot! Browse our courses and purchase them securely.')
AUTO_DELETE_SECONDS = int(os.getenv('AUTO_DELETE_SECONDS', '300'))  # Delete messages after 5 minutes by default
AUTO_APPROVE = os.getenv('AUTO_APPROVE', 'false').lower() == 'true'  # Auto-approve payments (False by default)
BOT_PASSWORD = ''  # No password by default

# Payment Options
PAYMENT_OPTIONS = {
    'UPI': os.getenv('UPI_ID', ''),
    'CRYPTO': os.getenv('CRYPTO_ADDRESS', ''),
    'PAYPAL': os.getenv('PAYPAL_ID', ''),
    'COD': os.getenv('COD_ENABLED', 'false').lower() == 'true',
    'GIFT_CARD': os.getenv('GIFT_CARD_ENABLED', 'false').lower() == 'true'
}

# Bot configuration
BOT_NAME = os.getenv('BOT_NAME', 'Course Delivery Bot')

# Admin configuration
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@example.com')

# Notification settings
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL', '')
ENABLE_EMAIL_NOTIFICATION = os.getenv('ENABLE_EMAIL_NOTIFICATION', 'False').lower() == 'true'

# Payment options
PAYMENT_OPTIONS = {
    'UPI': os.getenv('UPI_ID', ''),
    'CRYPTO': os.getenv('CRYPTO_ADDRESS', ''),
    'PAYPAL': os.getenv('PAYPAL_EMAIL', ''),
    'COD': os.getenv('COD_AVAILABLE', 'False').lower() == 'true',
    'GIFT_CARD': os.getenv('GIFT_CARD_AVAILABLE', 'False').lower() == 'true'
} 