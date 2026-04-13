#!/usr/bin/env python3
"""
Profile Models Enhancement
Complete traveler profile system with preferences, history, and AI recommendations
"""

from datetime import datetime
from models import db

class TravelerProfile(db.Model):
    """Extended traveler profile with personal details and preferences"""
    __tablename__ = "traveler_profiles"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Basic Information
    full_name = db.Column(db.String(150), nullable=True)
    profile_photo = db.Column(db.String(200), nullable=True)
    mobile = db.Column(db.String(20), nullable=True)
    
    # Personal Details
    gender = db.Column(db.String(10), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    nationality = db.Column(db.String(50), nullable=True)
    language_preference = db.Column(db.String(50), default='English')
    
    # Address
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    
    # Travel Preferences
    travel_type = db.Column(db.String(20), nullable=True)
    budget_range = db.Column(db.String(20), nullable=True)
    preferred_destinations = db.Column(db.Text, nullable=True)
    travel_frequency = db.Column(db.String(20), nullable=True)
    
    # Profile completion tracking
    profile_completion = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref='traveler_profile', foreign_keys=[user_id])

class TravelHistory(db.Model):
    """User's travel history and bookings"""
    __tablename__ = "travel_history"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Trip Details
    trip_name = db.Column(db.String(200), nullable=False)
    destination = db.Column(db.String(200), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey('travel_packages.id'), nullable=True)
    
    # Status and Dates
    status = db.Column(db.String(20), default='upcoming')
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Financial
    total_cost = db.Column(db.Float, nullable=True)
    
    # Experience
    rating = db.Column(db.Integer, nullable=True)
    review = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='travel_history', foreign_keys=[user_id])

class Wishlist(db.Model):
    """User's saved destinations and packages"""
    __tablename__ = "wishlists"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Item Details
    item_type = db.Column(db.String(20), nullable=False)
    item_id = db.Column(db.Integer, nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    
    # Metadata
    saved_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    user = db.Column

(db.Integer, db.ForeignKey('users.id'))

class UserReview(db.Model):
    """Reviews and ratings given by user"""
    __tablename__ = "user_reviews"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Review Target
    target_type = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    target_name = db.Column(db.String(200), nullable=False)
    
    # Review Content
    rating = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=True)
    review_text = db.Column(db.Text, nullable=True)
    
    # Media
    photos = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='user_reviews', foreign_keys=[user_id])

class NotificationPreference(db.Model):
    """User notification settings"""
    __tablename__ = "notification_preferences"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Notification Types
    trip_reminders = db.Column(db.Boolean, default=True)
    offers_discounts = db.Column(db.Boolean, default=True)
    booking_confirmations = db.Column(db.Boolean, default=True)
    travel_recommendations = db.Column(db.Boolean, default=True)
    
    # Email Settings
    email_notifications = db.Column(db.Boolean, default=True)
    sms_notifications = db.Column(db.Boolean, default=False)
    
    # Relationships
    user = db.relationship('User', backref='notification_prefs', foreign_keys=[user_id])
