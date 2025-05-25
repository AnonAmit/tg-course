import os
import sys
import hashlib
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.models import get_db, Admin, Course, Category
from config.config import ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_EMAIL

def hash_password(password):
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_or_create_category(db, name):
    """Helper function to get or create a category."""
    category = db.query(Category).filter_by(name=name).first()
    if not category:
        category = Category(name=name)
        db.add(category)
        # We might need to flush to get the ID if we need it immediately before commit
        # For this script, committing at the end is fine.
    return category

def initialize_database():
    """Initialize the database with default admin and sample courses"""
    db = get_db()
    
    admin_exists = db.query(Admin).filter_by(username=ADMIN_USERNAME).first()
    if not admin_exists:
        admin = Admin(
            username=ADMIN_USERNAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            email=ADMIN_EMAIL,
            created_date=datetime.datetime.now(datetime.UTC)
        )
        db.add(admin)
        print("Default admin created.")

        # Create Categories
        cat_programming = get_or_create_category(db, "Programming")
        cat_data_science = get_or_create_category(db, "Data Science")
        cat_web_dev = get_or_create_category(db, "Web Development")
        
        # Add sample courses only if admin was just created (implies fresh DB or first setup)
        sample_courses_data = [
            {
                "title": "Python Programming Basics",
                "description": "Learn Python from scratch with this comprehensive course.",
                "price": 29.99,
                "file_link": "https://drive.google.com/sample_link_1",
                "category_obj": cat_programming,
                "image_link": "https://example.com/python_course.jpg",
                "is_active": True
            },
            {
                "title": "Advanced Machine Learning",
                "description": "Dive deep into machine learning algorithms and techniques.",
                "price": 49.99,
                "file_link": "https://drive.google.com/sample_link_2",
                "category_obj": cat_data_science,
                "image_link": "https://example.com/ml_course.jpg",
                "is_active": True
            },
            {
                "title": "Web Development with Flask",
                "description": "Build web applications using Flask framework.",
                "price": 39.99,
                "file_link": "https://drive.google.com/sample_link_3",
                "category_obj": cat_web_dev,
                "image_link": "https://example.com/flask_course.jpg",
                "is_active": True
            }
        ]
        
        for course_data in sample_courses_data:
            category_object = course_data.pop('category_obj')
            course = Course(**course_data, category_obj=category_object)
            db.add(course)
        
        db.commit()
        print("Database initialized with default admin and sample courses/categories.")
    else:
        print("Database already initialized or admin exists.")

if __name__ == "__main__":
    initialize_database() 