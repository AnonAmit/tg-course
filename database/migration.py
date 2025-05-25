import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import sqlalchemy as sa

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config import DATABASE_URL

def run_migration():
    """Run database migration to add new fields"""
    print("Starting database migration...")
    
    engine = create_engine(DATABASE_URL)
    
    # Check if columns already exist
    inspect = sa.inspect(engine)
    course_columns = inspect.get_columns('courses')
    payment_columns = inspect.get_columns('payments')
    
    course_columns_names = [col['name'] for col in course_columns]
    payment_columns_names = [col['name'] for col in payment_columns]
    
    # Add payment_options column to Course table if it doesn't exist
    if 'payment_options' not in course_columns_names:
        print("Adding payment_options column to courses table...")
        try:
            with engine.connect() as conn:
                conn.execute(text('ALTER TABLE courses ADD COLUMN payment_options VARCHAR(255)'))
                conn.commit()
            print("Successfully added payment_options column")
        except Exception as e:
            print(f"Error adding payment_options column: {e}")
    
    # Add details column to Payment table if it doesn't exist
    if 'details' not in payment_columns_names:
        print("Adding details column to payments table...")
        try:
            with engine.connect() as conn:
                conn.execute(text('ALTER TABLE payments ADD COLUMN details TEXT'))
                conn.commit()
            print("Successfully added details column")
        except Exception as e:
            print(f"Error adding details column: {e}")
    
    print("Migration completed!")

if __name__ == "__main__":
    run_migration() 