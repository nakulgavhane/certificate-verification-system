from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user # type: ignore
from werkzeug.security import generate_password_hash, check_password_hash
from qr_scanner import verify_certificate
from models import db, User, VerificationHistory, Verification
from forms import LoginForm, RegistrationForm, UserBioForm
from flask_bootstrap import Bootstrap # type: ignore
import json
import os
from datetime import datetime, date
from sqlalchemy import inspect, text

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///certificates.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
Bootstrap(app)
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

# Authentication routes
@app.route('/')
def index():
    # Show home page to non-authenticated users
    if not current_user.is_authenticated:
        return redirect(url_for('home'))
    
    # Redirect authenticated users to appropriate dashboard
    if current_user.is_admin:
        return redirect(url_for('admin_home'))
    return redirect(url_for('user_dashboard'))

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_home'))
        return redirect(url_for('user_dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'error')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            if user.is_admin:
                next_page = url_for('admin_home')
            else:
                next_page = url_for('user_dashboard')
        return redirect(next_page)
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_home'))
        return redirect(url_for('user_dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

# User routes
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    verifications = VerificationHistory.query.filter_by(user_id=current_user.id).order_by(VerificationHistory.timestamp.desc()).all()
    # Categorize verifications
    verified = [v for v in verifications if v.status == 'valid']
    non_verified = [v for v in verifications if v.status == 'invalid']

    return render_template('user_dashboard.html', verified=verified, non_verified=non_verified)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = UserBioForm()
    if form.validate_on_submit():
        current_user.full_name = form.full_name.data
        current_user.bio = form.bio.data
        current_user.phone = form.phone.data
        current_user.address = form.address.data
        db.session.commit()
        flash('Your profile has been updated.', 'success')
        return redirect(url_for('profile'))
    elif request.method == 'GET':
        form.full_name.data = current_user.full_name
        form.bio.data = current_user.bio
        form.phone.data = current_user.phone
        form.address.data = current_user.address
    return render_template('profile.html', form=form)

# Certificate verification routes
@app.route('/upload_certificate', methods=['POST'])
@login_required
def upload_certificate():
    if 'certificate' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('user_dashboard'))
    
    file = request.files['certificate']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Check file size (5MB limit)
    file_content = file.read()
    file_size = len(file_content)
    file.seek(0)  # Reset file pointer after reading
    
    # 5MB in bytes
    if file_size > 5 * 1024 * 1024:
        flash('File size exceeds the 5MB limit', 'error')
        return redirect(url_for('user_dashboard'))

    # Process the certificate
    verification_result = verify_certificate(file)
    
    # Format file size for display
    if file_size < 1024:
        formatted_size = f"{file_size} bytes"
    elif file_size < 1024 * 1024:
        formatted_size = f"{(file_size / 1024):.2f} KB"
    else:
        formatted_size = f"{(file_size / (1024 * 1024)):.2f} MB"
    
    # Save verification history
    history = VerificationHistory(
        filename=file.filename,
        status=verification_result["status"],
        details=verification_result["details"],
        user_id=current_user.id,
        links=json.dumps(verification_result.get("links", [])),
        urls_in_text=json.dumps(verification_result.get("urls_in_text", [])),
        file_size=formatted_size  # Store formatted file size
    )
    db.session.add(history)
    db.session.commit()

    flash(f'Certificate verification completed. File Size: {formatted_size}', 'success')
    return redirect(url_for('view_verification', id=history.id))

def ensure_url_has_protocol(url):
    """Ensure URL starts with a protocol (http:// or https://)"""
    if not url.startswith(('http://', 'https://')):
        return 'https://' + url
    return url

@app.route('/view_verification/<int:id>')
@login_required
def view_verification(id):
    verification = VerificationHistory.query.get_or_404(id)
    if not current_user.is_admin and verification.user_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Process URLs to ensure they have proper protocol
    links = json.loads(verification.links) if verification.links else []
    urls_in_text = json.loads(verification.urls_in_text) if verification.urls_in_text else []
    
    # Ensure all URLs have proper protocol
    links = [ensure_url_has_protocol(link) for link in links]
    urls_in_text = [ensure_url_has_protocol(url) for url in urls_in_text]
    
    # Note: The status is now determined by link validation in the qr_scanner module
    return render_template('result.html',
                         status=verification.status,
                         details=verification.details,
                         links=links,
                         urls_in_text=urls_in_text)

# Admin routes
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('user_dashboard'))
    
    users = User.query.all()
    recent_verifications = VerificationHistory.query.order_by(VerificationHistory.timestamp.desc()).limit(10).all()
    total_users = User.query.filter_by(is_admin=False).count()
    total_verifications = VerificationHistory.query.count()
    valid_certificates = VerificationHistory.query.filter_by(status='valid').count()
    
    return render_template('admin_dashboard.html',
                         users=users,
                         recent_verifications=recent_verifications,
                         total_users=total_users,
                         total_verifications=total_verifications,
                          valid_certificates=valid_certificates)

# New route to delete a certificate
@app.route('/admin/delete_certification/<int:id>', methods=['POST'])
@login_required
def delete_certification(id):
    # Check if user is admin or owner of the certificate
    cert = VerificationHistory.query.get_or_404(id)
    
    if not current_user.is_admin and cert.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'You do not have permission to delete this certificate'}), 403
    
    try:
        db.session.delete(cert)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Certificate deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# New Admin Home Route
@app.route('/admin/home')
@login_required
def admin_home():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('user_dashboard'))

    # Fetch data similar to admin_dashboard
    total_users = User.query.filter_by(is_admin=False).count()
    total_verifications = VerificationHistory.query.count()
    valid_certificates = VerificationHistory.query.filter_by(status='valid').count()
    admin_name = current_user.full_name or current_user.username # Get admin's name

    return render_template('admin_home.html',
                           admin_name=admin_name,
                           total_users=total_users,
                           total_verifications=total_verifications,
                           valid_certificates=valid_certificates)


@app.route('/admin/delete_user/<int:id>', methods=['POST'])
@login_required
def delete_user(id):
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    user = User.query.get_or_404(id)
    if user.is_admin:
        return jsonify({'error': 'Cannot delete admin user'}), 400
    
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted successfully'})

@app.route('/admin/delete_verification/<int:id>', methods=['POST'])
@login_required
def delete_verification(id):
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    verification = VerificationHistory.query.get_or_404(id)
    db.session.delete(verification)
    db.session.commit()
    return jsonify({'message': 'Verification deleted successfully'})

@app.route('/admin/user_details/<int:id>', methods=['GET'])
@login_required
def user_details(id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('user_dashboard'))

    user = User.query.get_or_404(id)
    verifications = VerificationHistory.query.filter_by(user_id=user.id).all()

    # Categorize verifications
    verified_certificates = [v for v in verifications if v.status == 'valid']
    non_verified_certificates = [v for v in verifications if v.status == 'invalid']

    return render_template('user_details.html', user=user, 
                           verified_certificates=verified_certificates, 
                           non_verified_certificates=non_verified_certificates)

# API endpoints for admin dashboard stats
@app.route('/api/stats/today_verifications')
@login_required
def today_verifications():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    
    count = VerificationHistory.query.filter(
        VerificationHistory.timestamp >= today_start,
        VerificationHistory.timestamp <= today_end
    ).count()
    
    return jsonify({'count': count})

@app.route('/api/stats/today_new_users')
@login_required
def today_new_users():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    
    count = User.query.filter(
        User.profile_created >= today_start,
        User.profile_created <= today_end
    ).count()
    
    return jsonify({'count': count})

def format_time_diff(timestamp):
    now = datetime.now()
    time_diff = now - timestamp
    total_seconds = int(time_diff.total_seconds())
    
    # If less than a minute
    if total_seconds < 60:
        return "just now"
    
    # If less than an hour
    if total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    
    # If less than a day
    if total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    
    # If less than a week
    if total_seconds < 604800:
        days = total_seconds // 86400
        return f"{days} day{'s' if days > 1 else ''} ago"
    
    # If less than a month (approximated to 30 days)
    if total_seconds < 2592000:
        weeks = total_seconds // 604800
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    
    # If more than a month, show the actual date
    return timestamp.strftime("%B %d, %Y")

@app.route('/api/stats/recent_activity')
@login_required
def recent_activity():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get the most recent verifications
    recent_verifs = VerificationHistory.query.order_by(
        VerificationHistory.timestamp.desc()
    ).limit(5).all()
    
    # Get the most recent user registrations
    recent_users = User.query.order_by(
        User.profile_created.desc()
    ).limit(3).all()
    
    # Combine and sort by timestamp
    activities = []
    
    for v in recent_verifs:
        time_display = format_time_diff(v.timestamp)
        
        # Get filename and user info
        filename = v.filename if v.filename else "Unknown file"
        user = User.query.get(v.user_id)
        username = user.username if user else "Unknown user"
        
        # Create a more detailed message based on status
        message = ""
        if v.status == "valid":
            message = f"Valid certificate verification: {filename}"
        elif v.status == "invalid":
            message = f"Invalid certificate verification: {filename}"
        else:
            message = f"Certificate verification ({v.status}): {filename}"
        
        activities.append({
            'type': 'verification',
            'status': v.status,
            'message': message,
            'details': f"By user: {username}",
            'time': time_display,
            'timestamp': v.timestamp
        })
    
    for u in recent_users:
        if not u.is_admin:  # Don't include admin users
            time_display = format_time_diff(u.profile_created)
            
            activities.append({
                'type': 'user',
                'message': f"New user registered: {u.username}",
                'details': u.email if u.email else "",
                'time': time_display,
                'timestamp': u.profile_created
            })
    
    # Sort by timestamp, most recent first
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Take only the first 3
    activities = activities[:3]
    
    return jsonify(activities)

# Admin create user route
@app.route('/admin/create_user', methods=['POST'])
@login_required
def admin_create_user():
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied. Admin privileges required.'}), 403
    
    data = request.json
    
    # Basic validation
    if not data.get('username') or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Check if username exists
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    # Check if email exists
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    # Create new user
    user = User(
        username=data['username'],
        email=data['email'],
        full_name=data.get('full_name', ''),
        is_admin=data.get('is_admin', False)
    )
    user.set_password(data['password'])
    
    try:
        db.session.add(user)
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': 'User created successfully',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'is_admin': user.is_admin,
                'profile_created': user.profile_created.strftime('%Y-%m-%d')
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Anonymous certificate verification route
@app.route('/verify_anonymous', methods=['POST'])
def verify_anonymous():
    if 'certificate' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('home'))
    
    file = request.files['certificate']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('home'))
    
    # Check file size (5MB limit)
    file_content = file.read()
    file_size = len(file_content)
    file.seek(0)  # Reset file pointer after reading
    
    # 5MB in bytes
    if file_size > 5 * 1024 * 1024:
        flash('File size exceeds the 5MB limit', 'error')
        return redirect(url_for('home'))

    # Process the certificate
    verification_result = verify_certificate(file)
    
    # Format file size for display
    if file_size < 1024:
        formatted_size = f"{file_size} bytes"
    elif file_size < 1024 * 1024:
        formatted_size = f"{(file_size / 1024):.2f} KB"
    else:
        formatted_size = f"{(file_size / (1024 * 1024)):.2f} MB"
    
    # For anonymous users, store the result in the session instead of the database
    session_data = {
        'filename': file.filename,
        'status': verification_result["status"],
        'details': verification_result["details"],
        'file_size': formatted_size,
        'links': verification_result.get("links", []),
        'urls_in_text': verification_result.get("urls_in_text", [])
    }
    
    # Store in session
    if 'anonymous_verifications' not in session:
        session['anonymous_verifications'] = []
    
    # Add the new verification to the beginning of the list
    session['anonymous_verifications'].insert(0, session_data)
    
    # Only keep the most recent 5 verifications in the session
    if len(session['anonymous_verifications']) > 5:
        session['anonymous_verifications'] = session['anonymous_verifications'][:5]
    
    # Mark session as modified
    session.modified = True
    
    flash(f'Certificate verification completed. File Size: {formatted_size}', 'success')
    return redirect(url_for('anonymous_result'))

@app.route('/anonymous_result')
def anonymous_result():
    # Check if there are any anonymous verifications
    if 'anonymous_verifications' not in session or not session['anonymous_verifications']:
        flash('No verification results found', 'error')
        return redirect(url_for('home'))
    
    # Get the most recent verification result
    result = session['anonymous_verifications'][0]
    
    # Process URLs to ensure they have proper protocol
    links = [ensure_url_has_protocol(link) for link in result.get('links', [])]
    urls_in_text = [ensure_url_has_protocol(url) for url in result.get('urls_in_text', [])]
    
    # Note: The status is now determined by link validation in the qr_scanner module
    return render_template('anonymous_result.html',
                         status=result['status'],
                         details=result['details'],
                         links=links,
                         urls_in_text=urls_in_text,
                         filename=result['filename'],
                         file_size=result['file_size'])

def init_db():
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Check if file_size column exists in VerificationHistory table
        # If not, add it
        inspector = inspect(db.engine)
        columns = [column['name'] for column in inspector.get_columns('verification_history')]
        
        if 'file_size' not in columns:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE verification_history ADD COLUMN file_size VARCHAR(20)'))
                conn.commit()
            print("Added file_size column to verification_history table")
        
        # Create admin user if it doesn't exist
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True,
                full_name='Administrator',
                bio='System Administrator'
            )
            admin.set_password('admin')  # Change this password in production
            db.session.add(admin)
            db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
