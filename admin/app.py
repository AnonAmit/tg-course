import os
import sys
import datetime
import hashlib
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config import ADMIN_USERNAME, ADMIN_PASSWORD, UPLOAD_FOLDER
from database.models import get_db, Admin, Course, User, Payment, Log, Category, BotSetting, CourseRequest

# Add method to Payment class for getting associated course
Payment.get_course = lambda self: get_db().query(Course).filter_by(id=self.course_id).first()

# Add property to make payment proof accessible via both payment_proof and proof_file
@property
def proof_file(self):
    return self.payment_proof

@proof_file.setter
def proof_file(self, value):
    self.payment_proof = value

Payment.proof_file = proof_file

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev_secret_key')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed file extensions for security
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User loader for Flask-Login
class AdminUser(UserMixin):
    def __init__(self, admin_id, username):
        self.id = admin_id
        self.username = username

@login_manager.user_loader
def load_user(admin_id):
    db = get_db()
    admin = db.query(Admin).filter_by(id=int(admin_id)).first()
    if admin:
        return AdminUser(admin.id, admin.username)
    return None

# Helper functions
def hash_password(password):
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_stats():
    """Get system statistics"""
    db = get_db()
    total_users = db.query(User).count()
    total_courses = db.query(Course).count()
    total_payments = db.query(Payment).count()
    
    pending_payments = db.query(Payment).filter_by(status='pending').count()
    approved_payments = db.query(Payment).filter_by(status='approved').count()
    
    # Calculate revenue
    revenue = db.query(func.sum(Payment.amount)).filter_by(status='approved').scalar() or 0
    
    # Recent payments
    recent_payments = db.query(Payment).order_by(Payment.submission_date.desc()).limit(5).all()
    
    return {
        'total_users': total_users,
        'total_courses': total_courses,
        'total_payments': total_payments,
        'pending_payments': pending_payments,
        'approved_payments': approved_payments,
        'revenue': revenue,
        'recent_payments': recent_payments
    }

def get_user_logs(telegram_id):
    """Get logs for a specific user"""
    db = get_db()
    logs = db.query(Log).filter_by(telegram_id=telegram_id).order_by(Log.timestamp.desc()).limit(50).all()
    return logs

def allowed_file(filename):
    """Check if a file has an allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route('/')
def index():
    """Redirect to login or dashboard"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        db = get_db()
        admin = db.query(Admin).filter_by(username=username).first()
        
        if admin and admin.password_hash == hash_password(password):
            admin.last_login = datetime.datetime.now(datetime.UTC)
            db.commit()
            
            user = AdminUser(admin.id, admin.username)
            login_user(user)
            
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Admin logout"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Admin dashboard"""
    stats = get_stats()
    return render_template('dashboard.html', stats=stats)

@app.route('/courses')
@login_required
def courses():
    """Course management"""
    search_query = request.args.get('search', '')
    
    db = get_db()
    query = db.query(Course)
    
    if search_query:
        # Search in course title or category name using LIKE
        query = query.join(Category, Course.category_id == Category.id, isouter=True).filter(
            Course.title.ilike(f'%{search_query}%') |
            Category.name.ilike(f'%{search_query}%')
        )
    
    courses_list = query.order_by(Course.created_date.desc()).all()
    
    return render_template('courses.html', courses=courses_list, search_query=search_query)

@app.route('/course/add', methods=['GET', 'POST'])
@login_required
def add_course():
    """Add a new course"""
    db = get_db()
    categories_list = db.query(Category).order_by(Category.name).all()

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        file_link = request.form.get('file_link')
        category_id = request.form.get('category_id')
        category_id = int(category_id) if category_id else None
        image_link = request.form.get('image_link')
        
        # Get payment options as a list
        payment_options = request.form.getlist('payment_options')
        payment_options_str = ','.join(payment_options) if payment_options else None
        
        qr_code_image = request.form.get('qr_code_image')
        is_free = 'is_free' in request.form
        demo_video_link = request.form.get('demo_video_link')

        if not title or not file_link or (not is_free and price <= 0):
            flash('Please fill all required fields. Price must be greater than 0 unless the course is marked as free.', 'danger')
            return redirect(url_for('add_course'))
        
        # Handle image upload if provided
        image_file = request.files.get('image_upload')
        if image_file and image_file.filename and allowed_file(image_file.filename):
            # Secure the filename
            filename = secure_filename(image_file.filename)
            # Create a unique filename to prevent overwriting
            unique_filename = f"{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d%H%M%S')}_{filename}"
            # Save the file
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            image_file.save(image_path)
            # Set the image link to the uploaded file URL
            image_link = url_for('uploaded_file', filename=unique_filename, _external=True)
        elif image_file and image_file.filename and not allowed_file(image_file.filename):
            flash('Invalid file type. Only images (PNG, JPG, JPEG, GIF, WEBP) are allowed.', 'danger')
            return redirect(url_for('add_course'))
        
        db = get_db()
        course = Course(
            title=title,
            description=description,
            price=price,
            file_link=file_link,
            category_id=category_id,
            image_link=image_link,
            is_active=True,
            payment_options=payment_options_str,
            qr_code_image=qr_code_image if qr_code_image else None,
            is_free=is_free,
            demo_video_link=demo_video_link if demo_video_link else None
        )
        db.add(course)
        db.commit()
        
        flash('Course added successfully!', 'success')
        return redirect(url_for('courses'))
    
    return render_template('course_form.html', course=None, categories=categories_list)

@app.route('/course/edit/<int:course_id>', methods=['GET', 'POST'])
@login_required
def edit_course(course_id):
    """Edit an existing course"""
    db = get_db()
    course = db.query(Course).filter_by(id=course_id).first()
    categories_list = db.query(Category).order_by(Category.name).all()

    if not course:
        flash('Course not found.', 'danger')
        return redirect(url_for('courses'))
    
    if request.method == 'POST':
        course.title = request.form.get('title')
        course.description = request.form.get('description')
        course.price = float(request.form.get('price'))
        course.file_link = request.form.get('file_link')
        category_id = request.form.get('category_id')
        course.category_id = int(category_id) if category_id else None
        
        # Get payment options as a list
        payment_options = request.form.getlist('payment_options')
        course.payment_options = ','.join(payment_options) if payment_options else None

        course.qr_code_image = request.form.get('qr_code_image')
        if course.qr_code_image == "": # Handle empty string from select
            course.qr_code_image = None
        course.is_free = 'is_free' in request.form
        course.demo_video_link = request.form.get('demo_video_link')
        if course.demo_video_link == "":
            course.demo_video_link = None

        if not course.is_free and course.price <= 0:
            flash('Price must be greater than 0 unless the course is marked as free.', 'danger')
            return redirect(url_for('edit_course', course_id=course_id))
        
        # Keep existing image_link as default
        image_link = request.form.get('image_link')
        if not image_link:
            image_link = course.image_link
        
        # Handle image upload if provided
        image_file = request.files.get('image_upload')
        if image_file and image_file.filename and allowed_file(image_file.filename):
            # Secure the filename
            filename = secure_filename(image_file.filename)
            # Create a unique filename to prevent overwriting
            unique_filename = f"{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d%H%M%S')}_{filename}"
            # Save the file
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            image_file.save(image_path)
            # Set the image link to the uploaded file URL
            image_link = url_for('uploaded_file', filename=unique_filename, _external=True)
        elif image_file and image_file.filename and not allowed_file(image_file.filename):
            flash('Invalid file type. Only images (PNG, JPG, JPEG, GIF, WEBP) are allowed.', 'danger')
            return redirect(url_for('edit_course', course_id=course_id))
        
        # Update the image link (either from upload or form input)
        course.image_link = image_link
        course.is_active = 'is_active' in request.form
        # course.updated_date is automatically handled by the model's onupdate
        
        db.commit()
        
        flash('Course updated successfully!', 'success')
        return redirect(url_for('courses'))
    
    return render_template('course_form.html', course=course, categories=categories_list)

@app.route('/course/delete/<int:course_id>')
@login_required
def delete_course(course_id):
    """Delete a course"""
    db = get_db()
    course = db.query(Course).filter_by(id=course_id).first()
    
    if not course:
        flash('Course not found.', 'danger')
        return redirect(url_for('courses'))
    
    # Check if there are any payments associated with this course
    payment_count = db.query(Payment).filter_by(course_id=course_id).count()
    if payment_count > 0:
        flash(f'Cannot delete this course because it has {payment_count} associated payments. Consider marking it as inactive instead.', 'danger')
        return redirect(url_for('courses'))
    
    # If no payments are associated, proceed with deletion
    db.delete(course)
    db.commit()
    flash('Course deleted successfully!', 'success')
    
    return redirect(url_for('courses'))

@app.route('/payments')
@login_required
def payments():
    """Payment management"""
    status = request.args.get('status', 'all')
    
    db = get_db()
    query = db.query(Payment)
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    payments_list = query.order_by(Payment.submission_date.desc()).all()
    
    # Gather user and course info
    payment_data = []
    for payment in payments_list:
        user = db.query(User).filter_by(id=payment.user_id).first()
        course = db.query(Course).filter_by(id=payment.course_id).first()
        
        payment_data.append({
            'payment': payment,
            'user': user,
            'course': course
        })
    
    return render_template('payments.html', payments=payment_data, current_status=status)

@app.route('/payment/<int:payment_id>')
@login_required
def payment_detail(payment_id):
    """View payment details"""
    db = get_db()
    payment = db.query(Payment).filter_by(id=payment_id).first()
    
    if not payment:
        flash('Payment not found.', 'danger')
        return redirect(url_for('payments'))
    
    user = db.query(User).filter_by(id=payment.user_id).first()
    course = db.query(Course).filter_by(id=payment.course_id).first()
    
    return render_template('payment_detail.html', payment=payment, user=user, course=course)

@app.route('/payment/approve/<int:payment_id>')
@login_required
def approve_payment(payment_id):
    """Approve a payment"""
    db = get_db()
    payment = db.query(Payment).filter_by(id=payment_id).first()
    
    if payment:
        payment.status = 'approved'
        payment.approval_date = datetime.datetime.now(datetime.UTC)
        
        # Record if it's a gift card payment for tracking purposes
        if payment.payment_method == 'gift' and payment.details:
            payment.details += " [REDEEMED]"
            
        db.commit()
        
        # TODO: Send notification to user (implement in a production environment)
        
        flash('Payment approved successfully!', 'success')
    else:
        flash('Payment not found.', 'danger')
    
    return redirect(url_for('payments'))

@app.route('/payment/reject/<int:payment_id>')
@login_required
def reject_payment(payment_id):
    """Reject a payment"""
    db = get_db()
    payment = db.query(Payment).filter_by(id=payment_id).first()
    
    if payment:
        payment.status = 'rejected'
        db.commit()
        
        # TODO: Send notification to user (implement in a production environment)
        
        flash('Payment rejected.', 'info')
    else:
        flash('Payment not found.', 'danger')
    
    return redirect(url_for('payments'))

@app.route('/users')
@login_required
def users():
    """User management"""
    db = get_db()
    users_list = db.query(User).order_by(User.joined_date.desc()).all()
    
    return render_template('users.html', users=users_list)

@app.route('/user/<int:user_id>')
@login_required
def user_detail(user_id):
    """View user details"""
    db = get_db()
    user = db.query(User).filter_by(id=user_id).first()
    
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('users'))
    
    payments = db.query(Payment).filter_by(user_id=user.id).all()
    logs = db.query(Log).filter_by(telegram_id=user.telegram_id).order_by(Log.timestamp.desc()).limit(50).all()
    
    # Pass the function to the template context
    return render_template(
        'user_detail.html', 
        user=user, 
        payments=payments, 
        logs=logs,
        get_user_logs=get_user_logs
    )

@app.route('/user/ban/<int:user_id>', methods=['POST'])
@login_required
def ban_user(user_id):
    """Ban a user"""
    reason = request.form.get('reason', '')
    
    db = get_db()
    user = db.query(User).filter_by(id=user_id).first()
    
    if user:
        user.is_banned = True
        user.ban_reason = reason
        db.commit()
        
        flash('User banned successfully.', 'success')
    else:
        flash('User not found.', 'danger')
    
    return redirect(url_for('user_detail', user_id=user_id))

@app.route('/user/unban/<int:user_id>')
@login_required
def unban_user(user_id):
    """Unban a user"""
    db = get_db()
    user = db.query(User).filter_by(id=user_id).first()
    
    if user:
        user.is_banned = False
        user.ban_reason = None
        db.commit()
        
        flash('User unbanned successfully.', 'success')
    else:
        flash('User not found.', 'danger')
    
    return redirect(url_for('user_detail', user_id=user_id))

@app.route('/logs')
@login_required
def logs():
    """View system logs"""
    db = get_db()
    logs_list = db.query(Log).order_by(Log.timestamp.desc()).limit(100).all()
    
    return render_template('logs.html', logs=logs_list)

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/course/<int:course_id>')
@login_required
def course_detail(course_id):
    """View course details"""
    db = get_db()
    course = db.query(Course).filter_by(id=course_id).first()
    
    if not course:
        flash('Course not found.', 'danger')
        return redirect(url_for('courses'))
    
    return render_template('course_detail.html', course=course)

@app.route('/fix-gift-codes')
@login_required
def fix_gift_codes():
    """Fix any masked gift card codes in the database"""
    db = get_db()
    # Find all gift card payments
    gift_payments = db.query(Payment).filter_by(payment_method='gift').all()
    
    fixed_count = 0
    for payment in gift_payments:
        if payment.details and '*' in payment.details:
            # This is a masked code that needs fixing
            # Since we can't recover the original code, we'll mark it for manual update
            payment.details = "NEEDS MANUAL UPDATE - Was masked: " + payment.details
            fixed_count += 1
    
    if fixed_count > 0:
        db.commit()
        flash(f'Found {fixed_count} masked gift card codes that need manual updates.', 'warning')
    else:
        flash('No masked gift card codes found in the database.', 'success')
    
    return redirect(url_for('payments'))

# CATEGORY ROUTES
@app.route('/categories')
@login_required
def categories():
    """Category management page"""
    db = get_db()
    all_categories = db.query(Category).order_by(Category.name).all()
    return render_template('categories.html', categories=all_categories)

@app.route('/category/add', methods=['GET', 'POST'])
@login_required
def add_category():
    """Add a new category"""
    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Category name is required.', 'danger')
            return render_template('category_form.html', category=None)
        
        db = get_db()
        existing_category = db.query(Category).filter(func.lower(Category.name) == func.lower(name)).first()
        if existing_category:
            flash('Category with this name already exists.', 'danger')
            return render_template('category_form.html', category=None, name=name)

        new_category = Category(name=name)
        db.add(new_category)
        db.commit()
        flash('Category added successfully!', 'success')
        return redirect(url_for('categories'))
    
    return render_template('category_form.html', category=None)

@app.route('/category/edit/<int:category_id>', methods=['GET', 'POST'])
@login_required
def edit_category(category_id):
    """Edit an existing category"""
    db = get_db()
    category = db.query(Category).filter_by(id=category_id).first()
    
    if not category:
        flash('Category not found.', 'danger')
        return redirect(url_for('categories'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Category name is required.', 'danger')
            return render_template('category_form.html', category=category)

        existing_category = db.query(Category).filter(func.lower(Category.name) == func.lower(name), Category.id != category_id).first()
        if existing_category:
            flash('Another category with this name already exists.', 'danger')
            return render_template('category_form.html', category=category, name=name)

        category.name = name
        db.commit()
        flash('Category updated successfully!', 'success')
        return redirect(url_for('categories'))
    
    return render_template('category_form.html', category=category)

@app.route('/category/delete/<int:category_id>')
@login_required
def delete_category(category_id):
    """Delete a category"""
    db = get_db()
    category = db.query(Category).filter_by(id=category_id).first()
    
    if not category:
        flash('Category not found.', 'danger')
        return redirect(url_for('categories'))
    
    # Unassign courses from this category before deleting
    courses_to_update = db.query(Course).filter_by(category_id=category_id).all()
    for course in courses_to_update:
        course.category_id = None
    
    db.delete(category)
    db.commit()
    flash('Category deleted successfully! Associated courses have been unassigned.', 'success')
    return redirect(url_for('categories'))

# BOT SETTINGS ROUTE
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def bot_settings():
    """Manage bot settings"""
    db = get_db()
    settings_keys = ['dmca_policy_text'] # Add more keys as needed
    current_settings = {s.key: s.value for s in db.query(BotSetting).filter(BotSetting.key.in_(settings_keys)).all()}

    if request.method == 'POST':
        for key in settings_keys:
            if key in request.form:
                value = request.form.get(key)
                setting = db.query(BotSetting).filter_by(key=key).first()
                if setting:
                    setting.value = value
                else:
                    new_setting = BotSetting(key=key, value=value)
                    db.add(new_setting)
        db.commit()
        flash('Settings updated successfully!', 'success')
        # Re-fetch to display updated values
        current_settings = {s.key: s.value for s in db.query(BotSetting).filter(BotSetting.key.in_(settings_keys)).all()}
    
    return render_template('settings.html', settings=current_settings)

# COURSE REQUEST ROUTES
@app.route('/course-requests')
@login_required
def course_requests_list():
    """Display course requests"""
    db = get_db()
    all_requests = db.query(CourseRequest).order_by(CourseRequest.is_fulfilled.asc(), CourseRequest.timestamp.desc()).all()
    return render_template('course_requests.html', requests=all_requests)

@app.route('/course-request/fulfill/<int:request_id>')
@login_required
def fulfill_course_request(request_id):
    """Mark a course request as fulfilled"""
    db = get_db()
    req = db.query(CourseRequest).filter_by(id=request_id).first()
    if req:
        req.is_fulfilled = True
        db.commit()
        flash('Course request marked as fulfilled.', 'success')
    else:
        flash('Course request not found.', 'danger')
    return redirect(url_for('course_requests_list'))

@app.route('/course-request/delete/<int:request_id>')
@login_required
def delete_course_request(request_id):
    """Delete a course request"""
    db = get_db()
    req = db.query(CourseRequest).filter_by(id=request_id).first()
    if req:
        db.delete(req)
        db.commit()
        flash('Course request deleted.', 'success')
    else:
        flash('Course request not found.', 'danger')
    return redirect(url_for('course_requests_list'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 