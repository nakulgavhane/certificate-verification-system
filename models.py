from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    # Bio information
    full_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    profile_created = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    verifications = db.relationship('VerificationHistory', backref='user', lazy=True)
    certificates = db.relationship('Verification', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def total_verifications(self):
        return len(self.verifications)
    
    @property
    def valid_certificates(self):
        return sum(1 for v in self.verifications if v.status == 'valid')
    
    @property
    def invalid_certificates(self):
        return sum(1 for v in self.verifications if v.status == 'invalid')

class VerificationHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.now)  # Changed from utcnow to now
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    links = db.Column(db.Text)  # Store as JSON string
    urls_in_text = db.Column(db.Text)  # Store as JSON string
    file_size = db.Column(db.String(20))  # Store formatted file size

class Verification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    certificate_number = db.Column(db.String(100), unique=True, nullable=False)
    holder_name = db.Column(db.String(100), nullable=False)
    issue_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date)
    certificate_type = db.Column(db.String(50), nullable=False)
    issuing_authority = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='active')  # active, expired, revoked
    verification_count = db.Column(db.Integer, default=0)
    last_verified = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Additional details stored as JSON
    additional_details = db.Column(db.JSON)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'certificate_number': self.certificate_number,
            'holder_name': self.holder_name,
            'issue_date': self.issue_date.isoformat(),
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None,
            'certificate_type': self.certificate_type,
            'issuing_authority': self.issuing_authority,
            'status': self.status,
            'verification_count': self.verification_count,
            'last_verified': self.last_verified.isoformat() if self.last_verified else None,
            'additional_details': self.additional_details
        }