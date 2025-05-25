from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config import DATABASE_URL

Base = declarative_base()

class Category(Base):
    __tablename__ = 'categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

    courses = relationship("Course", back_populates="category_obj")

    def __repr__(self):
        return f"<Category {self.name}>"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), unique=True, nullable=False)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    joined_date = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(String(255), nullable=True)
    
    payments = relationship("Payment", back_populates="user")
    
    def __repr__(self):
        return f"<User {self.username or self.telegram_id}>"

class Course(Base):
    __tablename__ = 'courses'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    file_link = Column(String(500), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=True)
    image_link = Column(String(500), nullable=True)
    qr_code_image = Column(String(255), nullable=True) # Stores filename of the QR code
    is_free = Column(Boolean, default=False) # Indicates if the course is free
    demo_video_link = Column(String(500), nullable=True) # Link to demo video
    created_date = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    updated_date = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC), onupdate=lambda: datetime.datetime.now(datetime.UTC))
    is_active = Column(Boolean, default=True)
    payment_options = Column(String(255), nullable=True)  # Comma-separated list of payment methods
    
    category_obj = relationship("Category", back_populates="courses")
    payments = relationship("Payment", back_populates="course")
    
    def __repr__(self):
        return f"<Course {self.title}>"

class Payment(Base):
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    course_id = Column(Integer, ForeignKey('courses.id'), nullable=False)
    payment_method = Column(String(50), nullable=False)  # UPI, Crypto, PayPal, COD, Gift Card
    payment_proof = Column(String(255), nullable=True)  # Path to the image
    amount = Column(Float, nullable=False)
    status = Column(String(50), default='pending')  # pending, approved, rejected
    submission_date = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    approval_date = Column(DateTime, nullable=True)
    ip_address = Column(String(50), nullable=True)
    details = Column(Text, nullable=True)  # Additional payment details like gift card codes
    
    user = relationship("User", back_populates="payments")
    course = relationship("Course", back_populates="payments")
    
    def __repr__(self):
        return f"<Payment {self.id} - {self.status}>"
    
    @property
    def gift_card_code(self):
        """Extract gift card code from details"""
        if self.payment_method == 'gift' and self.details and 'Gift Card Code:' in self.details:
            code = self.details.replace('Gift Card Code:', '').strip()
            # Additional check to remove [REDEEMED] marker if present
            if '[REDEEMED]' in code:
                code = code.replace('[REDEEMED]', '').strip()
            return code
        return None

class Log(Base):
    __tablename__ = 'logs'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), nullable=True)
    action = Column(String(255), nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    ip_address = Column(String(50), nullable=True)
    details = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<Log {self.action} at {self.timestamp}>"

class Admin(Base):
    __tablename__ = 'admins'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    created_date = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    last_login = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Admin {self.username}>"

class BotSetting(Base):
    __tablename__ = 'bot_settings'

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)

    def __repr__(self):
        return f"<BotSetting {self.key}={self.value[:50]}...>"

class CourseRequest(Base):
    __tablename__ = 'course_requests'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    request_text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.UTC))
    is_fulfilled = Column(Boolean, default=False) # Admin can mark as fulfilled

    user = relationship("User") # Relationship to User model

    def __repr__(self):
        return f"<CourseRequest by {self.user_id} for {self.request_text[:50]}...>"

# Initialize the database
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close() 