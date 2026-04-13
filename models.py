from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
db = SQLAlchemy()

class OTPVerification(db.Model):
    __tablename__ = "otp_verifications"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)  # NEW
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # traveler, admin, hotel, transport, travelagency
    profile_pic = db.Column(db.String(200), nullable=True)  # NEW
    
    # Temporarily comment out new columns until database is properly migrated
    # full_name = db.Column(db.String(150), nullable=True)  # NEW
    mobile = db.Column(db.String(20), unique=True, nullable=True)  # NEW
    # email_verified = db.Column(db.Boolean, default=False)  # NEW: OTP verification status
    # created_at = db.Column(db.DateTime, default=datetime.utcnow)  # NEW
    # updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # NEW

    hotels = db.relationship('Hotel', backref='owner', lazy=True)
    transports = db.relationship('Transport', backref='owner', lazy=True)
    # bookings = db.relationship("Booking", backref="user", lazy=True)
    messages_sent = db.relationship("Message", foreign_keys='Message.sender_id', backref="sender", lazy=True)
    messages_received = db.relationship("Message", foreign_keys='Message.receiver_id', backref="receiver", lazy=True)
    packages = db.relationship("TravelPackage", backref="agency", lazy=True)
    package_bookings = db.relationship("PackageBooking", backref="traveler", lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)

class Hotel(db.Model):
    __tablename__ = "hotels"
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Legacy required fields (from old schema)
    name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    price_per_night = db.Column(db.Float, nullable=False)
    
    # New fields
    hotel_name = db.Column(db.String(200), nullable=False)
    area = db.Column(db.String(100))
    city = db.Column(db.String(100))
    distance_from_airport = db.Column(db.String(100))
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    main_image = db.Column(db.String(300))
    total_images = db.Column(db.Integer)

    free_cancellation = db.Column(db.Boolean, default=False)
    zero_payment_available = db.Column(db.Boolean, default=False)

    short_highlight = db.Column(db.Text)
    full_description = db.Column(db.Text)  # NEW: Full hotel description

    rating_score = db.Column(db.Float)
    rating_label = db.Column(db.String(50))
    total_reviews = db.Column(db.Integer)

    original_price = db.Column(db.Float)
    discounted_price = db.Column(db.Float)
    taxes = db.Column(db.Float)

    price_per = db.Column(db.String(20))  # night/day

    is_favorite = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # NEW: Relationships
    images = db.relationship('HotelImage', back_populates='hotel', lazy=True, cascade='all, delete-orphan')
    amenities = db.relationship('HotelAmenity', back_populates='hotel', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('HotelReview', back_populates='hotel', lazy=True, cascade='all, delete-orphan')
    bookings = db.relationship('HotelBooking', back_populates='hotel', lazy=True, cascade='all, delete-orphan')
    rooms = db.relationship('Room', back_populates='hotel', lazy=True, cascade='all, delete-orphan')


# =========================================================
# HOTEL IMAGES (Multiple Images Gallery)
# =========================================================
class HotelImage(db.Model):
    __tablename__ = "hotel_images"
    
    id = db.Column(db.Integer, primary_key=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey('hotels.id'), nullable=False)
    image_url = db.Column(db.String(300), nullable=False)
    caption = db.Column(db.String(200))
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    hotel = db.relationship('Hotel', back_populates='images')


# =========================================================
# HOTEL AMENITIES
# =========================================================
class HotelAmenity(db.Model):
    __tablename__ = "hotel_amenities"
    
    id = db.Column(db.Integer, primary_key=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey('hotels.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # WiFi, Pool, Parking, etc.
    icon = db.Column(db.String(50))  # Icon class or emoji
    category = db.Column(db.String(50))  # General, Room, Bathroom, etc.
    
    hotel = db.relationship('Hotel', back_populates='amenities')


# =========================================================
# HOTEL REVIEWS
# =========================================================
class HotelReview(db.Model):
    __tablename__ = "hotel_reviews"
    
    id = db.Column(db.Integer, primary_key=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey('hotels.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Float, nullable=False)  # 1-5 stars
    title = db.Column(db.String(200))
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='hotel_reviews')
    hotel = db.relationship('Hotel', back_populates='reviews')


# =========================================================
# HOTEL BOOKINGS
# =========================================================
class HotelBooking(db.Model):
    __tablename__ = "hotel_bookings"
    
    id = db.Column(db.Integer, primary_key=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey('hotels.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=True)  # Optional for backward compatibility
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    check_in = db.Column(db.Date, nullable=False)
    check_out = db.Column(db.Date, nullable=False)
    guests = db.Column(db.Integer, nullable=False)
    rooms = db.Column(db.Integer, default=1)
    
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending")  # pending, confirmed, cancelled, completed
    
    guest_name = db.Column(db.String(100))
    guest_email = db.Column(db.String(120))
    guest_phone = db.Column(db.String(20))
    special_requests = db.Column(db.Text)
    
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='hotel_bookings')
    hotel = db.relationship('Hotel', back_populates='bookings')

# =========================================================
# ROOM MANAGEMENT SYSTEM
# =========================================================
class Room(db.Model):
    __tablename__ = "rooms"
    
    id = db.Column(db.Integer, primary_key=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey('hotels.id'), nullable=False)
    room_number = db.Column(db.String(20), nullable=False)
    room_type = db.Column(db.String(50), nullable=False)  # Single, Double, Deluxe, Suite
    capacity = db.Column(db.Integer, nullable=False, default=2)
    price_per_night = db.Column(db.Float, nullable=False)
    price_per_day = db.Column(db.Float, nullable=True)
    description = db.Column(db.Text)
    amenities = db.Column(db.Text)  # JSON string of amenities
    images = db.Column(db.Text)  # JSON string of image URLs
    status = db.Column(db.String(20), default='available')  # available, booked, maintenance
    floor_number = db.Column(db.Integer, default=1)
    size_sqft = db.Column(db.Integer)
    bed_type = db.Column(db.String(50))  # Single, Double, Queen, King
    view_type = db.Column(db.String(50))  # City, Garden, Pool, Sea
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    hotel = db.relationship('Hotel', back_populates='rooms')
    bookings = db.relationship('HotelBooking', backref='room', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'hotel_id': self.hotel_id,
            'room_number': self.room_number,
            'room_type': self.room_type,
            'capacity': self.capacity,
            'price_per_night': self.price_per_night,
            'price_per_day': self.price_per_day,
            'description': self.description,
            'amenities': json.loads(self.amenities) if self.amenities else [],
            'images': json.loads(self.images) if self.images else [],
            'status': self.status,
            'floor_number': self.floor_number,
            'size_sqft': self.size_sqft,
            'bed_type': self.bed_type,
            'view_type': self.view_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_amenities_list(self):
        """Parse amenities JSON string to list"""
        try:
            return json.loads(self.amenities) if self.amenities else []
        except:
            return []
    
    def set_amenities(self, amenities_list):
        """Set amenities from list"""
        self.amenities = json.dumps(amenities_list) if amenities_list else None
    
    def get_images_list(self):
        """Parse images JSON string to list"""
        try:
            return json.loads(self.images) if self.images else []
        except:
            return []
    
    def set_images(self, images_list):
        """Set images from list"""
        self.images = json.dumps(images_list) if images_list else None
    
    def is_available(self, check_in=None, check_out=None):
        """Check if room is available for given dates"""
        if self.status != 'available':
            return False
            
        if not check_in or not check_out:
            return True
            
        # Check for overlapping bookings
        overlapping_bookings = self.bookings.filter(
            HotelBooking.status.in_(['confirmed', 'pending'])
        ).filter(
            db.or_(
                db.and_(HotelBooking.check_in <= check_in, HotelBooking.check_out > check_in),
                db.and_(HotelBooking.check_in < check_out, HotelBooking.check_out >= check_out),
                db.and_(HotelBooking.check_in >= check_in, HotelBooking.check_out <= check_out)
            )
        ).first()
        
        return overlapping_bookings is None

# class Booking(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     room_id = db.Column(db.Integer, db.ForeignKey('room.id'))
#     user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
#     start_date = db.Column(db.Date)
#     end_date = db.Column(db.Date)
#     status = db.Column(db.String(50), default="booked")  # booked, cancelled

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    read = db.Column(db.Boolean, default=False)

class Transport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agency_name = db.Column(db.String(100), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    vehicle_type = db.Column(db.String(50))
    seats = db.Column(db.Integer)
    price_per_km = db.Column(db.Float)
    image_url = db.Column(db.String(200))


# ---------------------------
# Contact form submissions
# ---------------------------
class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(200), nullable=True)
    message = db.Column(db.Text, nullable=False)
    attachment = db.Column(db.String(200), nullable=True)
    consent = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=db.func.now())

#---------------------------
# About Us messages
#---------------------------
class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100), nullable=False)
    image_filename = db.Column(db.String(150), nullable=True)

    def __repr__(self):
        return f"<TeamMember {self.name}>"

class Tour(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    duration = db.Column(db.String(50), default='1 Day')
    active = db.Column(db.Boolean, default=True)
    
    # Image fields
    image_url = db.Column(db.String(500), nullable=True)
    image_alt_text = db.Column(db.String(200), nullable=True)
    image_source = db.Column(db.String(50), default='unsplash')
    image_hash = db.Column(db.String(100), nullable=True)
    photographer = db.Column(db.String(100), nullable=True)
    photographer_url = db.Column(db.String(500), nullable=True)
    unsplash_url = db.Column(db.String(500), nullable=True)

    def __repr__(self):
        return f"<Tour {self.title}>"
    
    def to_dict(self):
        """Convert Tour object to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'location': self.location,
            'price': self.price,
            'active': self.active,
            'image_url': getattr(self, 'image_url', None),
            'image_alt_text': getattr(self, 'image_alt_text', None),
            'image_source': getattr(self, 'image_source', 'unsplash'),
            'photographer': getattr(self, 'photographer', None),
            'photographer_url': getattr(self, 'photographer_url', None),
            'unsplash_url': getattr(self, 'unsplash_url', None)
        }


class TourBooking(db.Model):
    __tablename__ = "tour_bookings"
    
    id = db.Column(db.Integer, primary_key=True)
    tour_id = db.Column(db.Integer, db.ForeignKey('tour.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    tour_date = db.Column(db.Date, nullable=False)
    travelers_count = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    guest_name = db.Column(db.String(100), nullable=False)
    guest_email = db.Column(db.String(120), nullable=False)
    guest_phone = db.Column(db.String(20), nullable=False)
    special_requests = db.Column(db.Text)
    
    status = db.Column(db.String(50), default="confirmed")  # confirmed / cancelled / completed
    
    # Relationships
    tour = db.relationship('Tour', backref='bookings')
    user = db.relationship('User', backref='tour_bookings')
    
    def __repr__(self):
        return f"<TourBooking {self.id}>"
    

# ---------------- USER PREFERENCES ----------------
class UserPreference(db.Model):
    __tablename__ = "user_preferences"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    preference_type = db.Column(db.String(100), nullable=False)
    preference_value = db.Column(db.String(200), nullable=False)


# ---------------- DESTINATIONS ----------------
class Destination(db.Model):
    __tablename__ = "destinations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    state = db.Column(db.String(100), nullable=False, default="Maharashtra")
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(300), nullable=True)
    category = db.Column(db.String(50), nullable=True)
    rating = db.Column(db.Float, default=4.5)
    price = db.Column(db.String(50), nullable=True)
    reviews = db.Column(db.Integer, default=0)
    itineraries = db.relationship("Itinerary", backref="destination", lazy=True)


# ---------------- ITINERARIES ----------------
class Itinerary(db.Model):
    __tablename__ = "itineraries"
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(150), nullable=False)   # FIXED: Added city column
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    destination_id = db.Column(db.Integer, db.ForeignKey("destinations.id"), nullable=False)
    days = db.Column(db.Integer, nullable=False)
    plan = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    day_plans = db.relationship("DayPlan", backref="itinerary", lazy=True)


# ---------------- DAY PLANS ----------------
class DayPlan(db.Model):
    __tablename__ = "day_plans"
    id = db.Column(db.Integer, primary_key=True)
    itinerary_id = db.Column(db.Integer, db.ForeignKey("itineraries.id"), nullable=False)
    day_number = db.Column(db.Integer, nullable=False)
    summary = db.Column(db.Text, nullable=True)

    activities = db.relationship("Activity", backref="day_plan", lazy=True)


# ---------------- ACTIVITIES ----------------
class Activity(db.Model):
    __tablename__ = "activities"
    id = db.Column(db.Integer, primary_key=True)
    day_plan_id = db.Column(db.Integer, db.ForeignKey("day_plans.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    time = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)

# ---------------- BEST-SELLING DESTINATIONS ----------------
class BestSellingDestination(db.Model):
    __tablename__ = "best_selling_destinations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    country = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sales_count = db.Column(db.Integer, default=0)



# =========================================================
# TRAVEL PACKAGES (AGENCY SYSTEM)
# =========================================================
class TravelPackage(db.Model):
    __tablename__ = "travel_packages"

    id = db.Column(db.Integer, primary_key=True)
    agency_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    title = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    duration = db.Column(db.String(50), nullable=False)

    hotel = db.Column(db.String(150), nullable=True)
    meals = db.Column(db.String(150), nullable=True)
    activities = db.Column(db.String(200), nullable=True)

    complimentary = db.Column(db.Text, nullable=True)
    price_per_person = db.Column(db.Float, nullable=False)

    status = db.Column(db.String(50), default="active")  # active / inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships (agency relationship is defined in User model with backref)
    images = db.relationship("PackageImage", backref="package", lazy=True)
    bookings = db.relationship("PackageBooking", backref="package", lazy=True)

    def __repr__(self):
        return f"<TravelPackage {self.title}>"
    
    def to_dict(self):
        """Convert TravelPackage object to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'title': self.title,
            'location': self.location,
            'duration': self.duration,
            'hotel': self.hotel,
            'meals': self.meals,
            'activities': self.activities,
            'complimentary': self.complimentary,
            'price_per_person': self.price_per_person,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'image_url': self.images[0].image_url if self.images else None
        }


class PackageImage(db.Model):
    __tablename__ = "package_images"

    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey("travel_packages.id"), nullable=False)
    image_url = db.Column(db.String(300), nullable=False)


# =========================================================
# PACKAGE BOOKINGS + INVOICE SYSTEM
# =========================================================
class PackageBooking(db.Model):
    __tablename__ = "package_bookings"

    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey("travel_packages.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    travelers_count = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)

    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default="confirmed")  # confirmed / cancelled / completed

    invoice = db.relationship("Invoice", backref="booking", uselist=False)


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("package_bookings.id"), nullable=False)

    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    issued_date = db.Column(db.DateTime, default=datetime.utcnow)
    paid = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"

# =========================================================
# HIDDEN GEMS SYSTEM
# =========================================================
class HiddenGem(db.Model):
    __tablename__ = "hidden_gems"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(300), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Nature, Cultural, Food Spots, Unique Experiences
    subcategory = db.Column(db.String(100), nullable=False)  # Hidden waterfalls, Local festivals, etc.
    
    # Image
    image_url = db.Column(db.String(400), nullable=True)
    image_alt_text = db.Column(db.String(200), nullable=True)
    image_source = db.Column(db.String(50), default='unsplash')  # unsplash, unsplash_api, uploaded
    image_hash = db.Column(db.String(100), nullable=True)
    photographer = db.Column(db.String(100), nullable=True)
    photographer_url = db.Column(db.String(500), nullable=True)
    unsplash_url = db.Column(db.String(500), nullable=True)
    
    # Visit information
    best_time_to_visit = db.Column(db.String(200), nullable=True)
    nearby_transport = db.Column(db.Text, nullable=True)
    
    # Location data for maps
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    google_maps_url = db.Column(db.String(500), nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    ratings = db.relationship("HiddenGemRating", backref="gem", lazy=True, cascade='all, delete-orphan')
    itinerary_items = db.relationship("ItineraryHiddenGem", backref="gem", lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<HiddenGem {self.name}>"
    
    def average_rating(self):
        if not self.ratings:
            return 0
        return sum(r.rating for r in self.ratings) / len(self.ratings)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'location': self.location,
            'category': self.category,
            'subcategory': self.subcategory,
            'image_url': self.image_url,
            'image_alt_text': self.image_alt_text,
            'image_source': self.image_source,
            'photographer': self.photographer,
            'photographer_url': self.photographer_url,
            'unsplash_url': self.unsplash_url,
            'best_time_to_visit': self.best_time_to_visit,
            'nearby_transport': self.nearby_transport,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'google_maps_url': self.google_maps_url,
            'average_rating': self.average_rating(),
            'total_ratings': len(self.ratings)
        }


class HiddenGemRating(db.Model):
    __tablename__ = "hidden_gem_ratings"
    
    id = db.Column(db.Integer, primary_key=True)
    gem_id = db.Column(db.Integer, db.ForeignKey("hidden_gems.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    rating = db.Column(db.Float, nullable=False)  # 1-5 stars
    review = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='hidden_gem_ratings')


class ItineraryHiddenGem(db.Model):
    __tablename__ = "itinerary_hidden_gems"
    
    id = db.Column(db.Integer, primary_key=True)
    itinerary_id = db.Column(db.Integer, db.ForeignKey("itineraries.id"), nullable=False)
    gem_id = db.Column(db.Integer, db.ForeignKey("hidden_gems.id"), nullable=False)
    day_number = db.Column(db.Integer, nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    itinerary = db.relationship("Itinerary", backref="hidden_gems")
