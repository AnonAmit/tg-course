import os
import sys
import hashlib
import datetime
import requests
import pyshorteners
import random
import string
from PIL import Image
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config import UPLOAD_FOLDER
from database.models import Log, get_db

def log_action(telegram_id, action, ip_address=None, details=None):
    """Log user actions to the database"""
    db = get_db()
    log = Log(
        telegram_id=telegram_id,
        action=action,
        ip_address=ip_address,
        details=details
    )
    db.add(log)
    db.commit()

def save_payment_proof(telegram_id, file_data, file_extension="jpg"):
    """Save payment proof image to uploads folder"""
    # Create unique filename
    filename = f"{telegram_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{random_string(8)}.{file_extension}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    # Save the file
    try:
        if isinstance(file_data, bytes):
            # If file_data is already bytes
            with open(file_path, 'wb') as f:
                f.write(file_data)
        else:
            # If file_data is a file-like object
            with open(file_path, 'wb') as f:
                f.write(file_data.read())
        
        return filename
    except Exception as e:
        print(f"Error saving file: {e}")
        return None

def random_string(length=8):
    """Generate a random string of fixed length"""
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for i in range(length))

def shorten_url(url):
    """Shorten a URL using TinyURL"""
    try:
        s = pyshorteners.Shortener()
        return s.tinyurl.short(url)
    except Exception as e:
        print(f"Error shortening URL: {e}")
        return url

def is_valid_image(file_data):
    """Check if the file is a valid image"""
    try:
        img = Image.open(BytesIO(file_data))
        img.verify()  # Verify it's an image
        return True
    except Exception:
        return False

def is_spam(text):
    """Simple spam detection"""
    # Check for common spam indicators
    spam_keywords = ["casino", "porn", "sex", "viagra", "lottery", "free money", "bitcoin generator"]
    text_lower = text.lower()
    
    for keyword in spam_keywords:
        if keyword in text_lower:
            return True
    
    # Check for excessive use of special characters
    special_chars = "!@#$%^&*()_+={}[]|\\:;'<>,.?/"
    special_char_count = sum(1 for c in text if c in special_chars)
    
    if special_char_count > len(text) * 0.3:  # If more than 30% are special characters
        return True
    
    return False

def detect_duplicate_payment(image_data, user_id):
    """Simple duplicate payment detection based on image hash"""
    # This is a simplified version. In a real implementation, you might want
    # to use more sophisticated image comparison techniques
    image_hash = hashlib.md5(image_data).hexdigest()
    
    # TODO: Compare with previously submitted payment proofs
    # For now, just return False
    return False

def format_course_info(course):
    """Format course information for display in Telegram"""
    category_name = "Uncategorized"
    if course.category_obj:
        category_name = course.category_obj.name
    
    course_text = (
        f"📚 **{course.title}**\n\n"
        f"📝 **Description:** {course.description}\n\n"
        f"💰 **Price:** ₹{course.price:.2f}\n\n"
        f"🏷️ **Category:** {category_name}"
    )
    
    # We'll handle image display separately in the bot.py file
    return course_text 