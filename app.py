# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
from models import db, User, Hotel, Transport, ContactMessage, TeamMember, Tour, Itinerary, Destination, TravelPackage, PackageImage, HotelImage, HotelAmenity, HotelReview, HotelBooking, PackageBooking, TourBooking, OTPVerification, HiddenGem, HiddenGemRating, ItineraryHiddenGem
from profile_models import TravelerProfile, TravelHistory, Wishlist, UserReview, NotificationPreference
from config import Config
import os
from flask_cors import CORS
from werkzeug.utils import secure_filename
from flask import jsonify
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
from sqlalchemy import text
import google.generativeai as genai
from models  import db, User, UserPreference, Destination, Itinerary, DayPlan, Activity,TravelPackage, PackageImage
from flask import send_from_directory
from hotel_import_service import hotel_import_service
from datetime import datetime, timedelta
import requests
import re
import urllib.parse
from bs4 import BeautifulSoup
from external_apis import external_apis
from werkzeug.middleware.proxy_fix import ProxyFix
import socket
socket.setdefaulttimeout(15)
import threading

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Simple cache for API responses
_api_cache = {}
_cache_timeout = 300  # 5 minutes




app = Flask(__name__)
CORS(app)  # allow requests from frontend
app.config.from_object(Config)
db.init_app(app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Ensure database connections are properly closed after each request
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

# Create uploads folder if not exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_unsplash_image_api(place_name, location="", category=""):
    """
    Fetch a real photo using:
    1. Google Places API (New)
    2. Wikimedia Commons free image search
    3. Unsplash search
    """
    google_key   = os.getenv("GOOGLE_API_KEY", "")
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    fallback_url = "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&fit=crop&w=800&q=80"

    search_query = f"{place_name} {location}".strip()

    # --- 1. Google Places API (New) ---
    if google_key:
        try:
            r = requests.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": google_key,
                    "X-Goog-FieldMask": "places.displayName,places.photos"
                },
                json={"textQuery": search_query},
                timeout=8
            )
            places = r.json().get("places", [])
            if places and places[0].get("photos"):
                photo_name = places[0]["photos"][0]["name"]
                photo_url = (
                    f"https://places.googleapis.com/v1/{photo_name}/media"
                    f"?maxWidthPx=800&key={google_key}"
                )
                return {
                    "url": photo_url,
                    "small_url": photo_url.replace("maxWidthPx=800", "maxWidthPx=400"),
                    "download_url": photo_url.replace("maxWidthPx=800", "maxWidthPx=1600"),
                    "alt_text": places[0].get("displayName", {}).get("text", place_name),
                    "photographer": "Google Places",
                    "photographer_url": "https://maps.google.com",
                    "unsplash_url": "",
                    "width": 800, "height": 600,
                    "description": place_name, "color": "#000000"
                }
        except Exception:
            pass

    # --- 2. Wikimedia Commons (free, no key, works everywhere) ---
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"File:{search_query}",
                "gsrnamespace": 6,
                "gsrlimit": 1,
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": 800,
                "format": "json",
            },
            timeout=6,
        )
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [])
            if info and info[0].get("thumburl"):
                img_url = info[0]["thumburl"]
                return {
                    "url": img_url, "small_url": img_url, "download_url": img_url,
                    "alt_text": search_query, "photographer": "Wikimedia Commons",
                    "photographer_url": "https://commons.wikimedia.org",
                    "unsplash_url": "", "width": 800, "height": 600,
                    "description": place_name, "color": "#000000"
                }
    except Exception:
        pass

    # --- 3. Unsplash search ---
    if unsplash_key:
        try:
            resp = requests.get(
                "https://api.unsplash.com/search/photos",
                headers={"Authorization": f"Client-ID {unsplash_key}"},
                params={"query": search_query, "per_page": 1, "orientation": "landscape"},
                timeout=8,
            )
            results = resp.json().get("results", [])
            if results:
                photo = results[0]
                return {
                    "url": photo["urls"]["regular"],
                    "small_url": photo["urls"]["small"],
                    "download_url": photo["urls"]["full"],
                    "alt_text": photo.get("alt_description", place_name),
                    "photographer": photo["user"]["name"],
                    "photographer_url": photo["user"]["links"]["html"],
                    "unsplash_url": photo["links"]["html"],
                    "width": photo["width"], "height": photo["height"],
                    "description": photo.get("description", ""), "color": photo.get("color", "#000000")
                }
        except Exception:
            pass

    return {
        "url": fallback_url, "small_url": fallback_url, "download_url": fallback_url,
        "alt_text": place_name, "photographer": "", "photographer_url": "",
        "unsplash_url": "", "width": 800, "height": 600,
        "description": place_name, "color": "#000000"
    }



# ==================== EXTERNAL APIS ====================

@app.route("/api/hotels/search", methods=["POST"])
def search_external_hotels():
    """Search hotels using Booking.com API"""
    try:
        data = request.get_json()
        location = data.get("location", "").strip()
        check_in = data.get("check_in", "")
        check_out = data.get("check_out", "")
        guests = data.get("guests", 1)
        rooms = data.get("rooms", 1)
        
        if not location or not check_in or not check_out:
            return jsonify({
                "success": False,
                "message": "Location, check-in, and check-out dates are required"
            })
        
        # Search hotels
        hotels = external_apis.search_hotels_booking(
            location, check_in, check_out, guests, rooms
        )
        
        return jsonify({
            "success": True,
            "hotels": hotels,
            "message": f"Found {len(hotels)} hotels in {location}"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error searching hotels: {str(e)}"
        })

@app.route("/api/trains/search", methods=["POST"])
def search_trains():
    """Search trains using Indian Railway API"""
    try:
        data = request.get_json()
        from_station = data.get("from_station", "").strip().upper()
        to_station = data.get("to_station", "").strip().upper()
        travel_date = data.get("travel_date", "")
        class_type = data.get("class_type", "1A")
        
        if not from_station or not to_station or not travel_date:
            return jsonify({
                "success": False,
                "message": "From station, to station, and travel date are required"
            })
        
        # Search trains
        trains = external_apis.search_trains_indian_railway(
            from_station, to_station, travel_date, class_type
        )
        
        return jsonify({
            "success": True,
            "trains": trains,
            "message": f"Found {len(trains)} trains from {from_station} to {to_station}"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error searching trains: {str(e)}"
        })

@app.route("/api/flights/search", methods=["POST"])
def search_flights():
    """Search flights using external API"""
    try:
        data = request.get_json()
        from_city = data.get("from_city", "").strip()
        to_city = data.get("to_city", "").strip()
        departure_date = data.get("departure_date", "")
        passengers = data.get("passengers", 1)
        
        if not from_city or not to_city or not departure_date:
            return jsonify({
                "success": False,
                "message": "From city, to city, and departure date are required"
            })
        
        # Search flights
        flights = external_apis.search_flights(
            from_city, to_city, departure_date, passengers
        )
        
        return jsonify({
            "success": True,
            "flights": flights,
            "message": f"Found {len(flights)} flights from {from_city} to {to_city}"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error searching flights: {str(e)}"
        })

@app.route("/api/buses/search", methods=["POST"])
def search_buses():
    """Search buses using external API"""
    try:
        data = request.get_json()
        from_city = data.get("from_city", "").strip()
        to_city = data.get("to_city", "").strip()
        travel_date = data.get("travel_date", "")
        passengers = data.get("passengers", 1)
        
        if not from_city or not to_city or not travel_date:
            return jsonify({
                "success": False,
                "message": "From city, to city, and travel date are required"
            })
        
        # Search buses
        buses = external_apis.search_buses(
            from_city, to_city, travel_date, passengers
        )
        
        return jsonify({
            "success": True,
            "buses": buses,
            "message": f"Found {len(buses)} buses from {from_city} to {to_city}"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error searching buses: {str(e)}"
        })



@app.route("/healthz")
def health():
    return "OK", 200
    
# ==================== HIDDEN GEMS ====================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({"success": False, "message": "Not logged in"}), 401
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                # Return JSON for API/AJAX requests
                if request.path.startswith('/api/'):
                    return jsonify({"success": False, "message": "Not logged in"}), 401
                flash('Please login to access this page.', 'warning')
                return redirect(url_for('login'))
            
            user_role = session.get('role')
            if user_role not in allowed_roles:
                # Return JSON for API/AJAX requests
                if request.path.startswith('/api/'):
                    return jsonify({"success": False, "message": "Access denied. Insufficient privileges."}), 403
                flash('Access denied. Insufficient privileges.', 'danger')
                # Redirect to appropriate dashboard based on role
                if user_role == 'traveler':
                    return redirect(url_for('dashboard_traveler'))
                elif user_role == 'hotel':
                    return redirect(url_for('dashboard_hotel'))
                elif user_role == 'transport':
                    return redirect(url_for('dashboard_transport'))
                elif user_role == 'travelagency':
                    return redirect(url_for('dashboard_agency'))
                else:
                    return redirect(url_for('dashboard_admin'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_only_access(f):
    """Decorator to restrict admin users to only admin dashboard"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session and session.get('role') == 'admin':
            # Admin trying to access non-admin pages - logout and redirect
            current_route = request.endpoint
            if current_route not in ['dashboard_admin', 'logout', 'static']:
                flash('Admin users can only access the admin dashboard. You have been logged out for security.', 'warning')
                session.clear()
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def owner_required(resource_type):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login to access this page.', 'warning')
                return redirect(url_for('login'))
            
            user_id = session.get('user_id')
            user_role = session.get('role')
            
            # Admin can access everything
            if user_role == 'admin':
                return f(*args, **kwargs)
            
            # Check ownership based on resource type
            if resource_type == 'hotel':
                hotel_id = kwargs.get('hotel_id')
                if hotel_id:
                    hotel = Hotel.query.get(hotel_id)
                    if hotel and hotel.owner_id != user_id:
                        flash('Access denied. You can only manage your own hotels.', 'danger')
                        return redirect(url_for('dashboard_hotel'))
            
            elif resource_type == 'transport':
                transport_id = kwargs.get('transport_id')
                if transport_id:
                    transport = Transport.query.get(transport_id)
                    if transport and transport.owner_id != user_id:
                        flash('Access denied. You can only manage your own transport services.', 'danger')
                        return redirect(url_for('dashboard_transport'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Initialize DB safely
if app.config.get("AUTO_CREATE_TABLES", False):
    with app.app_context():
        db.create_all()

# Global before_request handler for admin access control
@app.before_request
def check_admin_access():
    """Restrict admin users to only admin dashboard"""
    if 'user_id' in session and session.get('role') == 'admin':
        # List of allowed endpoints for admin
        allowed_endpoints = [
            'dashboard_admin',
            'logout',
            'static',
            'admin_stats',
            'admin_users',
            'admin_hotels',
            'admin_transports',
            'admin_agencies',
            'admin_bookings',
            'admin_reviews',
            'admin_packages',
            'admin_contacts',
            'delete_user_admin',
            'delete_hotel_admin',
            'delete_transport_admin',
            'delete_review_admin',
            'delete_package_admin'
        ]
        
        current_endpoint = request.endpoint
        
        # If admin tries to access non-admin pages, logout
        if current_endpoint and current_endpoint not in allowed_endpoints:
            flash('Admin users can only access the admin dashboard. You have been logged out for security.', 'warning')
            session.clear()
            return redirect(url_for('login'))




# --------- AUTH ROUTES ---------





@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Get form data
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        mobile = request.form.get("mobile", "").strip()
        username = request.form.get("username", "").strip()  # Keep for backward compatibility
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "")
        terms = request.form.get("terms", "")
        email_otp = request.form.get("email_otp", "").strip()
        
        # Validation
        errors = []
        
        # Basic validations
        import re as _re
        if len(full_name) < 2:
            errors.append("Full name must be at least 2 characters")
        elif not _re.match(r'^[a-zA-Z\s]+$', full_name):
            errors.append("Full name must contain only letters")

        # Strict email validation
        email_pattern = _re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
        if not email or not email_pattern.match(email) or '..' in email:
            errors.append("Please enter a valid email address")
        else:
            local = email.split('@')[0]
            if local.startswith('.') or local.endswith('.'):
                errors.append("Please enter a valid email address")

        if len(mobile) != 10 or not mobile.isdigit():
            errors.append("Please enter a valid 10-digit mobile number")

        # Role defaults to traveler if not provided
        if not role:
            role = 'traveler'
        
        # Password validation
        password_errors = validate_password_requirements(password)
        if password_errors:
            errors.extend(password_errors)
        
        if password != confirm_password:
            errors.append("Passwords do not match")
        
        # OTP verification
        if not email_otp or len(email_otp) != 6:
            errors.append("Please verify your email with OTP")
        
        # Terms agreement
        if not terms:
            errors.append("Please agree to Terms of Service and Privacy Policy")
        
        # Check for existing users (using basic fields only)
        if User.query.filter_by(email=email).first():
            errors.append("Email already registered!")
        
        if username and User.query.filter_by(username=username).first():
            errors.append("Username already exists!")
        
        if mobile and User.query.filter_by(mobile=mobile).first():
            errors.append("Mobile number already registered!")
        
        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("register"))
        
        # Create user if all validations pass
        try:
            # Use full_name as username (since User model doesn't have full_name field yet)
            username_to_use = full_name if full_name else (username if username else email.split('@')[0])
            
            # Create user with available fields only
            new_user = User(
                username=username_to_use,  # Store full_name as username
                email=email,
                mobile=mobile,  # Save phone number
                role=role
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            # Clean up OTP sessions
            cleanup_otp_sessions(email)
            
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))
            
        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {str(e)}")  # Debug line
            flash("Registration failed. Please try again.", "danger")
            return redirect(url_for("register"))
    
    return render_template("register.html")

# Helper functions for validation
def validate_password_requirements(password):
    errors = []
    
    if len(password) < 8:
        errors.append("Password must be at least 8 characters")
    
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one number")
    
    if not any(c in '!@#$%^&*' for c in password):
        errors.append("Password must contain at least one special character")
    
    return errors

def cleanup_otp_sessions(email):
    OTPVerification.query.filter_by(email=email).update({"is_used": True})
    db.session.commit()
  def send_otp_email(email, otp):
    """Send OTP email to user (safe + Render-friendly)"""
    try:
        print(f"🔍 Debug: Sending OTP email to {email}")
        print(f"🔍 Debug: Email config - ADDRESS: {EMAIL_ADDRESS}, PASSWORD: {'SET' if EMAIL_PASSWORD else 'NOT SET'}")

        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = email
        msg['Subject'] = "🔐 Your OTP Verification Code - Tripoora"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; background:#f8f9fa; padding:20px;">
            <div style="max-width:600px;margin:auto;background:white;padding:20px;border-radius:10px;">
                <h2 style="color:#ff7f50;">🔐 Tripoora OTP Verification</h2>
                <p>Your OTP code is:</p>
                <h1 style="letter-spacing:5px;color:#3d5a4a;">{otp}</h1>
                <p>This OTP will expire soon. Do not share it with anyone.</p>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, "html"))

        # ✅ FIX 1: safer connection (no duplicate connect)
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)

        print("🔍 Debug: Connecting SMTP...")
        server.ehlo()

        print("🔍 Debug: Starting TLS...")
        server.starttls()
        server.ehlo()

        print("🔍 Debug: Logging in...")
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

        print("🔍 Debug: Sending email...")
        server.send_message(msg)

        server.quit()

        print(f"✅ OTP email sent successfully to {email}")
        return True

    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        return False


# API endpoints for frontend
@app.route("/api/send-otp", methods=["POST"])
def send_otp():
    email = request.form.get("email", "").strip()

    if not email or '@' not in email:
        return jsonify({"success": False, "message": "Invalid email address"})

    if User.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "Email already registered"})

    try:
        import random
        from datetime import datetime, timedelta

        otp = str(random.randint(100000, 999999))

        from datetime import datetime, timedelta

expires_at = datetime.utcnow() + timedelta(minutes=10)

otp_record = OTPVerification(
    email=email,
    otp=otp,
    expires_at=expires_at
)

        db.session.add(otp_record)
        db.session.commit()

        # ✅ SAFE EMAIL THREAD
        def safe_send_email(email, otp):
            try:
                send_otp_email(email, otp)
            except Exception as e:
                print(f"❌ Background email failed: {e}")

        threading.Thread(
            target=safe_send_email,
            args=(email, otp),
            daemon=True
        ).start()

        return jsonify({
            "success": True,
            "message": "OTP generated successfully"
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"success": False, "message": "Failed to send OTP"})
        
@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        otp = request.form.get("otp", "").strip()
        
        if not email or not otp:
            return jsonify({"success": False, "message": "Email and OTP required"})
        
        # Verify OTP
        otp_record = OTPVerification.query.filter_by(
            email=email,
            otp=otp,
            is_used=False
        ).first()
        
        if not otp_record or otp_record.expires_at < datetime.utcnow():
            return jsonify({"success": False, "message": "Invalid or expired OTP"})
        
        # Mark OTP as used
        otp_record.is_used = True
        db.session.commit()
        
        return jsonify({"success": True, "message": "OTP verified successfully"})
    
    return jsonify({"success": False, "message": "Invalid request"})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_or_email = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember_me = request.form.get("remember", "") == "on"
        
        # Try to find user by username or email
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["role"] = user.role
            session["username"] = user.username
            # Temporarily use username since full_name is not available
            session["full_name"] = user.username
            
            # Handle remember me
            if remember_me:
                session.permanent = True
            
            flash("Login successful!", "success")
            
            # Redirect based on role
            if user.role == "traveler":
                return redirect(url_for("dashboard_traveler"))
            elif user.role == "hotel":
                return redirect(url_for("dashboard_hotel"))
            elif user.role == "transport":
                return redirect(url_for("dashboard_transport"))
            elif user.role == "travelagency":
                return redirect(url_for("dashboard_agency"))
            else:
                return redirect(url_for("dashboard_admin"))
        else:
            flash("Invalid email/username or password!", "danger")
    
    return render_template("login.html")

@app.route("/api/forgot-password", methods=["POST"])
def forgot_password():
    if request.method == "POST":
        data = request.get_json()
        email = data.get("email", "").strip()
        
        if not email:
            return jsonify({"success": False, "message": "Email is required"})
        
        # Check if user exists
        user = User.query.filter_by(email=email).first()
        if not user:
            # Don't reveal if user exists for security
            return jsonify({"success": True, "message": "If an account exists with this email, a reset link has been sent."})
        
        try:
            # Generate reset token (in production, send email)
            import uuid
            reset_token = str(uuid.uuid4())
            
            # Store token in session or database (simplified for demo)
            session['reset_token'] = reset_token
            session['reset_email'] = email
            
            # In production, send email with reset link
            # For demo, return success message
            return jsonify({
                "success": True, 
                "message": "Password reset link sent to your email!",
                "demo_reset_link": f"/reset-password?token={reset_token}"  # Remove in production
            })
            
        except Exception as e:
            return jsonify({"success": False, "message": "Failed to send reset email"})
    
    return jsonify({"success": False, "message": "Invalid request"})

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    token = request.args.get('token')
    reset_email = session.get('reset_email')
    
    if not token or not reset_email or token != session.get('reset_token'):
        flash("Invalid or expired reset link!", "danger")
        return redirect(url_for("login"))
    
    if request.method == "POST":
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        if not new_password or not confirm_password:
            flash("Please enter and confirm your new password", "danger")
        elif new_password != confirm_password:
            flash("Passwords do not match!", "danger")
        else:
            # Find user and update password
            user = User.query.filter_by(email=reset_email).first()
            if user:
                user.set_password(new_password)
                db.session.commit()
                
                # Clear reset session
                session.pop('reset_token', None)
                session.pop('reset_email', None)
                
                flash("Password reset successful! Please login with your new password.", "success")
                return redirect(url_for("login"))
            else:
                flash("User not found!", "danger")
    
    return render_template("reset_password.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))








# --------- DASHBOARDS -------------------------------------------------------------------------------------------------------------------------------------------------------------------



@app.route("/")
def index():
    hotels = Hotel.query.all()
    transports = Transport.query.all()
    return render_template("index.html", hotels=hotels, transports=transports)

@app.route("/dashboard/traveler")
@login_required
@role_required('traveler')
def dashboard_traveler():
    """Traveler dashboard with access to book services but not manage them"""
    return render_template("dashboard_traveler.html")

@app.route("/dashboard/agency")
@login_required
@role_required('travelagency', 'admin')
def dashboard_agency():
    """Travel agency dashboard with package management"""
    return render_template("dashboard_travel_agency.html")



@app.route("/dashboard/transport")
@login_required
@role_required('transport')
def dashboard_transport():
    """Transport dashboard with transport management"""
    # Get transports for the current transport provider
    user_id = session.get("user_id")
    transports = Transport.query.filter_by(owner_id=user_id).all()
    return render_template("dashboard_transport.html", transports=transports)


# -------------------------
# ADD PACKAGE API
# -------------------------
@app.route("/add_packages", methods=["GET", "POST"])
@login_required
@role_required('travelagency', 'admin')
def add_packages():
    if request.method == "GET":
        return render_template("add_packages.html")

    # POST logic here
    try:
        title = request.form.get("title")
        location = request.form.get("location")
        duration = request.form.get("duration")
        hotel = request.form.get("hotel")
        meals = request.form.get("meals")
        activities = request.form.get("activities")
        complimentary = request.form.get("complimentary")
        price = float(request.form.get("price"))

        image_file = request.files.get("image")

        if not image_file:
            return jsonify({"error": "Image is required"}), 400

        filename = secure_filename(image_file.filename)
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image_file.save(image_path)

        # Get logged-in user or create a default agency user
        user_id = session.get("user_id")
        if not user_id:
            # Create or get a default agency user
            default_user = User.query.filter_by(username="default_agency").first()
            if not default_user:
                default_user = User(username="default_agency", role="travelagency", email="agency@example.com")
                default_user.set_password("password123")
                db.session.add(default_user)
                db.session.commit()
            user_id = default_user.id

        # Create Package
        new_package = TravelPackage(
            agency_id=user_id,
            title=title,
            location=location,
            duration=duration,
            hotel=hotel,
            meals=meals,
            activities=activities,
            complimentary=complimentary,
            price_per_person=price
        )

        db.session.add(new_package)
        db.session.commit()

        # Save Image
        package_image = PackageImage(
            package_id=new_package.id,
            image_url=f"uploads/{filename}"
        )

        db.session.add(package_image)
        db.session.commit()

        return jsonify({"message": "Package added successfully!", "package_id": new_package.id})

    except Exception as e:
        db.session.rollback()
        print(f"Error adding package: {str(e)}")
        return jsonify({"error": str(e)}), 500
    






# -------------------------
# GET ALL PACKAGES
# -------------------------
@app.route("/get-packages", methods=["GET"])
def get_packages():
    try:
        packages = TravelPackage.query.all()

        result = []

        for pkg in packages:
            image_url = None
            if pkg.images:
                # Remove leading slash if present
                img_path = pkg.images[0].image_url
                if img_path.startswith('/'):
                    img_path = img_path[1:]
                image_url = url_for('static', filename=img_path)

            # Get agency name
            agency_name = pkg.agency.username if pkg.agency else "Unknown Agency"

            result.append({
                "id": pkg.id,
                "title": pkg.title,
                "location": pkg.location,
                "duration": pkg.duration,
                "hotel": pkg.hotel,
                "meals": pkg.meals,
                "activities": pkg.activities,
                "complimentary": pkg.complimentary,
                "price": pkg.price_per_person,
                "status": pkg.status,
                "agency_name": agency_name,
                "image": image_url if image_url else url_for('static', filename='uploads/default.jpg')
            })

        return jsonify(result)

    except Exception as e:
        print(f"Error getting packages: {str(e)}")
        return jsonify({"error": str(e)}), 500
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------------
# ADD PACKAGE API
# -------------------------

# ... (rest of the code remains the same)

@app.route("/dashboard/admin")
@login_required
@role_required('admin')
def dashboard_admin():
    # Get all data for dashboard
    users = User.query.all()
    hotels = Hotel.query.all()
    transports = Transport.query.all()
    tours = Tour.query.all()
    packages = TravelPackage.query.all()
    itineraries = Itinerary.query.all()
    contact_messages = ContactMessage.query.all()
    hidden_gems = HiddenGem.query.all() if HiddenGem else []
    
    # Calculate statistics
    stats = {
        'total_users': len(users),
        'total_hotels': len(hotels),
        'total_tours': len(tours),
        'total_packages': len(packages),
        'total_transports': len(transports),
        'total_itineraries': len(itineraries),
        'total_messages': len(contact_messages),
        'total_hidden_gems': len(hidden_gems),
        'travelers': len([u for u in users if u.role == 'traveler']),
        'hotel_managers': len([u for u in users if u.role == 'hotel']),
        'tour_operators': len([u for u in users if u.role == 'travelagency']),
        'transport_providers': len([u for u in users if u.role == 'transport']),
    }
    
    # Get recent activities
    recent_users = User.query.order_by(User.id.desc()).limit(5).all()
    recent_itineraries = Itinerary.query.order_by(Itinerary.created_at.desc()).limit(5).all()
    recent_messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(5).all()
    
    return render_template("dashboard_admin.html", 
                         users=users, 
                         hotels=hotels, 
                         transports=transports,
                         tours=tours,
                         packages=packages,
                         itineraries=itineraries,
                         contact_messages=contact_messages,
                         hidden_gems=hidden_gems,
                         stats=stats,
                         recent_users=recent_users,
                         recent_itineraries=recent_itineraries,
                         recent_messages=recent_messages)

# ---------------- DASHBOARD ----------------
@app.route("/hotels")
def hotels():
    # Load initial hotels from Maharashtra to display on page load
    try:
        initial_hotels = Hotel.query.limit(20).all()
        hotels_data = [{
            "id": h.id,
            "name": h.hotel_name,
            "city": h.city,
            "area": h.area,
            "description": h.short_highlight or f"{h.hotel_name} in {h.area}, {h.city}",
            "image": url_for('static', filename=h.main_image) if h.main_image else url_for('static', filename='uploads/default.jpg'),
            "rating": h.rating_score or 4.5,
            "price_per_night": h.discounted_price or h.original_price or 0
        } for h in initial_hotels]
    except Exception as e:
        print(f"Error loading initial hotels: {e}")
        hotels_data = []
    
    return render_template("hotels.html", initial_hotels=hotels_data)


# ----- HOTEL DASHBOARD -----
# ---------------- DASHBOARD ----------------
@app.route("/dashboard/hotel")
@login_required
@role_required('hotel', 'admin')
def dashboard_hotel():
    user_id = session.get("user_id")
    hotels = Hotel.query.filter_by(owner_id=user_id).all()
    
    # Calculate dashboard statistics
    total_rooms = 0
    available_rooms = 0
    total_bookings = 0
    total_revenue = 0
    
    # Get all rooms for this hotel owner
    all_rooms = []
    for hotel in hotels:
        rooms = Room.query.filter_by(hotel_id=hotel.id).all()
        all_rooms.extend(rooms)
        total_rooms += len(rooms)
        available_rooms += len([r for r in rooms if r.status == 'available'])
        
        # Count bookings for this hotel
        bookings = HotelBooking.query.filter_by(hotel_id=hotel.id).all()
        total_bookings += len(bookings)
        total_revenue += sum(b.total_price for b in bookings if b.status == 'confirmed' and b.total_price)
    
    # Ensure total_revenue is an integer
    total_revenue = int(total_revenue) if total_revenue else 0
    
    # Get recent bookings (last 10)
    recent_bookings = []
    for hotel in hotels:
        bookings = HotelBooking.query.filter_by(hotel_id=hotel.id).order_by(HotelBooking.booking_date.desc()).limit(5).all()
        recent_bookings.extend(bookings)
    
    # Sort recent bookings by date and limit to 10
    recent_bookings = sorted(recent_bookings, key=lambda x: x.booking_date, reverse=True)[:10]
    
    # Create sample notifications
    notifications = [
        {
            'icon': '📅',
            'title': 'New Booking Received',
            'message': f'A new booking has been confirmed for one of your properties',
            'time': '2 hours ago'
        },
        {
            'icon': '💰',
            'title': 'Payment Received',
            'message': f'Payment received for recent booking',
            'time': '5 hours ago'
        }
    ]
    
    # Add dynamic notifications based on recent activity
    if recent_bookings:
        latest_booking = recent_bookings[0]
        if latest_booking.status == 'pending':
            notifications.insert(0, {
                'icon': '⏰',
                'title': 'Pending Booking',
                'message': f'New booking from {latest_booking.guest_name or "Guest"} needs approval',
                'time': 'Just now'
            })
    
    return render_template("dashboard_hotel_enhanced.html", 
                         hotels=hotels,
                         rooms=all_rooms,
                         recent_bookings=recent_bookings,
                         notifications=notifications,
                         total_rooms=total_rooms,
                         available_rooms=available_rooms,
                         total_bookings=total_bookings,
                         total_revenue=total_revenue)

# -----------------------
# ADD HOTEL ROUTE
# -----------------------
@app.route('/add_hotel', methods=['GET', 'POST'])
@login_required
@role_required('hotel', 'travelagency', 'admin')
def add_hotel():
    if request.method == 'POST':
        try:
            # Handle image upload
            image = request.files.get('main_image')
            if not image:
                flash("Please upload a hotel image!", "danger")
                return redirect(url_for('add_hotel'))
            
            filename = secure_filename(image.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)

            # Create new hotel
            new_hotel = Hotel(
                hotel_name=request.form['hotel_name'],
                area=request.form.get('area', ''),
                city=request.form.get('city', ''),
                distance_from_airport=request.form.get('distance_from_airport', ''),
                main_image='uploads/' + filename,
                total_images=int(request.form.get('total_images', 1)),
                free_cancellation=bool(request.form.get('free_cancellation')),
                zero_payment_available=bool(request.form.get('zero_payment_available')),
                short_highlight=request.form.get('short_highlight', ''),
                rating_score=float(request.form.get('rating_score', 0)),
                rating_label=request.form.get('rating_label', ''),
                total_reviews=int(request.form.get('total_reviews', 0)),
                original_price=float(request.form.get('original_price', 0)),
                discounted_price=float(request.form.get('discounted_price', 0)),
                taxes=float(request.form.get('taxes', 0)),
                price_per=request.form.get('price_per', 'night'),
                is_favorite=bool(request.form.get('is_favorite')),
                owner_id=session.get('user_id')
            )

            db.session.add(new_hotel)
            db.session.commit()
            
            flash("Hotel added successfully!", "success")
            
            # Redirect based on user role
            user_role = session.get('role')
            if user_role == 'hotel':
                return redirect(url_for('dashboard_hotel'))
            elif user_role == 'travelagency':
                return redirect(url_for('dashboard_agency'))
            else:
                return redirect(url_for('dashboard_traveler'))
                
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding hotel: {str(e)}", "danger")
            return redirect(url_for('add_hotel'))

    return render_template('add_hotel.html')

@app.route("/edit_hotel/<int:hotel_id>", methods=["GET", "POST"])
@owner_required('hotel')
def edit_hotel(hotel_id):
    hotel = Hotel.query.get_or_404(hotel_id)
    if request.method == "POST":
        hotel.name = request.form["name"]
        hotel.location = request.form["location"]
        hotel.description = request.form["description"]
        hotel.status = request.form.get("status", hotel.status)
        db.session.commit()
        flash("Hotel updated!", "success")
        return redirect(url_for("dashboard_hotel"))
    return render_template("edit_hotel.html", hotel=hotel)

@app.route("/delete_hotel/<int:hotel_id>")
@owner_required('hotel')
def delete_hotel(hotel_id):
    hotel = Hotel.query.get_or_404(hotel_id)
    db.session.delete(hotel)
    db.session.commit()
    flash("Hotel deleted!", "success")
    return redirect(url_for("dashboard_hotel"))


# =========================================================
# HOTEL DETAIL PAGE
# =========================================================
@app.route("/hotel/<int:hotel_id>")
def hotel_detail(hotel_id):
    hotel = Hotel.query.get_or_404(hotel_id)
    
    # Get all images for gallery
    images = HotelImage.query.filter_by(hotel_id=hotel_id).all()
    
    # Get amenities grouped by category
    amenities = HotelAmenity.query.filter_by(hotel_id=hotel_id).all()
    amenities_by_category = {}
    for amenity in amenities:
        category = amenity.category or 'General'
        if category not in amenities_by_category:
            amenities_by_category[category] = []
        amenities_by_category[category].append(amenity)
    
    # Get reviews
    reviews = HotelReview.query.filter_by(hotel_id=hotel_id).order_by(HotelReview.created_at.desc()).all()
    
    # Calculate average rating from reviews
    if reviews:
        avg_rating = sum(r.rating for r in reviews) / len(reviews)
    else:
        avg_rating = hotel.rating_score or 0
    
    return render_template('hotel_detail.html', 
                         hotel=hotel, 
                         images=images,
                         amenities_by_category=amenities_by_category,
                         reviews=reviews,
                         avg_rating=avg_rating)


# =========================================================
# HOTEL BOOKING
# =========================================================
# HOTEL BOOKING - REDIRECT TO EXTERNAL PLATFORMS
# =========================================================
@app.route("/hotel/<int:hotel_id>/book", methods=["GET", "POST"])
@login_required
@role_required('traveler')
def book_hotel(hotel_id):
    """Redirect to external booking platforms"""
    hotel = Hotel.query.get_or_404(hotel_id)
    
    # Redirect to MakeMyTrip with hotel details
    search_query = f"{hotel.hotel_name} {hotel.city}"
    makemytrip_url = f"https://www.makemytrip.com/hotels/hotel-listing/?city={hotel.city}&searchText={search_query}"
    
    flash("Redirecting to external booking platform...", "info")
    return redirect(makemytrip_url)


@app.route("/booking/<int:booking_id>/confirmation")
def booking_confirmation(booking_id):
    booking = HotelBooking.query.get_or_404(booking_id)
    
    # Check if user owns this booking
    if booking.user_id != session.get('user_id'):
        flash("Unauthorized access", "danger")
        return redirect(url_for('index'))
    
    return render_template('booking_confirmation.html', booking=booking)


# =========================================================
# HOTEL REVIEWS
# =========================================================
@app.route("/hotel/<int:hotel_id>/review", methods=["POST"])
@login_required
@role_required('traveler', 'admin')
def add_review(hotel_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Please login to leave a review"}), 401
    
    try:
        rating = float(request.form['rating'])
        title = request.form.get('title', '')
        comment = request.form.get('comment', '')
        
        review = HotelReview(
            hotel_id=hotel_id,
            user_id=user_id,
            rating=rating,
            title=title,
            comment=comment
        )
        
        db.session.add(review)
        
        # Update hotel's total reviews count
        hotel = Hotel.query.get(hotel_id)
        hotel.total_reviews = (hotel.total_reviews or 0) + 1
        
        # Recalculate average rating
        all_reviews = HotelReview.query.filter_by(hotel_id=hotel_id).all()
        if all_reviews:
            hotel.rating_score = sum(r.rating for r in all_reviews) / len(all_reviews)
        
        db.session.commit()
        
        flash("Review added successfully!", "success")
        return redirect(url_for('hotel_detail', hotel_id=hotel_id))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding review: {str(e)}", "danger")
        return redirect(url_for('hotel_detail', hotel_id=hotel_id))


# =========================================================
# HOTEL SEARCH & FILTER API
# =========================================================
# HOTEL SEARCH & FILTER API
# =========================================================
@app.route("/api/hotels/search-internal", methods=["GET"])
@app.route("/api/hotels/search", methods=["GET"])
def search_hotels_internal():
    try:
        city = request.args.get('city', '').strip().lower()
        min_price = request.args.get('min_price', type=float)
        max_price = request.args.get('max_price', type=float)
        min_rating = request.args.get('min_rating', type=float)

        query = Hotel.query

        # If city is provided, search for it
        # Otherwise, show all Maharashtra hotels
        if city:
            query = query.filter(
                db.or_(
                    Hotel.city.ilike(f'%{city}%'),
                    Hotel.hotel_name.ilike(f'%{city}%'),
                    Hotel.area.ilike(f'%{city}%')
                )
            )
        # If no city specified, show all hotels (Maharashtra-wide)

        if min_price is not None:
            query = query.filter(
                db.or_(Hotel.discounted_price >= min_price,
                       db.and_(Hotel.discounted_price == None, Hotel.original_price >= min_price))
            )

        if max_price is not None:
            query = query.filter(
                db.or_(Hotel.discounted_price <= max_price,
                       db.and_(Hotel.discounted_price == None, Hotel.original_price <= max_price))
            )

        if min_rating is not None:
            query = query.filter(Hotel.rating_score >= min_rating)

        hotels = query.all()

        return jsonify([{
            "id": h.id,
            "name": h.hotel_name or h.hotel_name,
            "city": h.city,
            "area": h.area,
            "description": h.short_highlight or f"{h.hotel_name} in {h.area}, {h.city}",
            "image": url_for('static', filename=h.main_image) if h.main_image else url_for('static', filename='uploads/default.jpg'),
            "rating": h.rating_score or 4.5,
            "price_per_night": h.discounted_price or h.original_price or 0
        } for h in hotels])
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- ROOM ----------------
@app.route("/add_room/<int:hotel_id>", methods=["GET", "POST"])
@owner_required('hotel')
def add_room(hotel_id):
    hotel = Hotel.query.get_or_404(hotel_id)
    if request.method == "POST":
        room_type = request.form["room_type"]
        price = float(request.form["price"])
        room = Room(hotel_id=hotel.id, room_type=room_type, price=price)
        db.session.add(room)
        db.session.commit()

        files = request.files.getlist("images")
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                img = RoomImage(room_id=room.id, image_url=f"uploads/{filename}")
                db.session.add(img)
        db.session.commit()
        flash("Room added!", "success")
        return redirect(url_for("dashboard_hotel"))
    return render_template("add_room.html", hotel=hotel)

@app.route("/edit_room/<int:room_id>", methods=["GET", "POST"])
@owner_required('hotel')
def edit_room(room_id):
    room = Room.query.get_or_404(room_id)
    if request.method == "POST":
        room.room_type = request.form["room_type"]
        room.price = float(request.form["price"])
        room.availability = request.form.get("availability") == "on"
        db.session.commit()
        flash("Room updated!", "success")
        return redirect(url_for("dashboard_hotel"))
    return render_template("edit_room.html", room=room)

@app.route("/delete_room/<int:room_id>")
@owner_required('hotel')
def delete_room(room_id):
    room = Room.query.get_or_404(room_id)
    db.session.delete(room)
    db.session.commit()
    flash("Room deleted!", "success")
    return redirect(url_for("dashboard_hotel"))

# =========================================================
# ENHANCED ROOM MANAGEMENT API
# =========================================================
@app.route("/api/rooms", methods=["GET"])
@login_required
@role_required('hotel', 'admin')
def api_get_rooms():
    """Get all rooms for the logged-in hotel owner"""
    try:
        user_id = session.get("user_id")
        hotels = Hotel.query.filter_by(owner_id=user_id).all()
        hotel_ids = [h.id for h in hotels]
        
        rooms = Room.query.filter(Room.hotel_id.in_(hotel_ids)).all()
        return jsonify([room.to_dict() for room in rooms])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/rooms/<int:room_id>", methods=["GET"])
@login_required
@role_required('hotel', 'admin')
def api_get_room(room_id):
    """Get specific room details"""
    try:
        room = Room.query.get_or_404(room_id)
        return jsonify(room.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/rooms", methods=["POST"])
@login_required
@role_required('hotel', 'admin')
def api_create_room():
    """Create a new room"""
    try:
        data = request.get_json()
        
        # Validate hotel ownership
        user_id = session.get("user_id")
        hotel = Hotel.query.filter_by(id=data['hotel_id'], owner_id=user_id).first()
        if not hotel:
            return jsonify({"error": "Hotel not found or access denied"}), 403
        
        room = Room(
            hotel_id=data['hotel_id'],
            room_number=data['room_number'],
            room_type=data['room_type'],
            capacity=data.get('capacity', 2),
            price_per_night=data['price_per_night'],
            price_per_day=data.get('price_per_day'),
            description=data.get('description'),
            floor_number=data.get('floor_number', 1),
            size_sqft=data.get('size_sqft'),
            bed_type=data.get('bed_type'),
            view_type=data.get('view_type')
        )
        
        # Set amenities and images if provided
        if data.get('amenities'):
            room.set_amenities(data['amenities'])
        if data.get('images'):
            room.set_images(data['images'])
        
        db.session.add(room)
        db.session.commit()
        
        return jsonify({
            "message": "Room created successfully",
            "room": room.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/api/rooms/<int:room_id>", methods=["PUT"])
@login_required
@role_required('hotel', 'admin')
def api_update_room(room_id):
    """Update room details"""
    try:
        room = Room.query.get_or_404(room_id)
        
        # Validate hotel ownership
        user_id = session.get("user_id")
        hotel = Hotel.query.filter_by(id=room.hotel_id, owner_id=user_id).first()
        if not hotel:
            return jsonify({"error": "Access denied"}), 403
        
        data = request.get_json()
        
        # Update room fields
        if 'room_number' in data:
            room.room_number = data['room_number']
        if 'room_type' in data:
            room.room_type = data['room_type']
        if 'capacity' in data:
            room.capacity = data['capacity']
        if 'price_per_night' in data:
            room.price_per_night = data['price_per_night']
        if 'price_per_day' in data:
            room.price_per_day = data['price_per_day']
        if 'description' in data:
            room.description = data['description']
        if 'status' in data:
            room.status = data['status']
        if 'floor_number' in data:
            room.floor_number = data['floor_number']
        if 'size_sqft' in data:
            room.size_sqft = data['size_sqft']
        if 'bed_type' in data:
            room.bed_type = data['bed_type']
        if 'view_type' in data:
            room.view_type = data['view_type']
        
        # Update amenities and images if provided
        if 'amenities' in data:
            room.set_amenities(data['amenities'])
        if 'images' in data:
            room.set_images(data['images'])
        
        room.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "message": "Room updated successfully",
            "room": room.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/api/rooms/<int:room_id>", methods=["DELETE"])
@login_required
@role_required('hotel', 'admin')
def api_delete_room(room_id):
    """Delete a room"""
    try:
        room = Room.query.get_or_404(room_id)
        
        # Validate hotel ownership
        user_id = session.get("user_id")
        hotel = Hotel.query.filter_by(id=room.hotel_id, owner_id=user_id).first()
        if not hotel:
            return jsonify({"error": "Access denied"}), 403
        
        db.session.delete(room)
        db.session.commit()
        
        return jsonify({"message": "Room deleted successfully"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/api/rooms/<int:room_id>/status", methods=["PUT"])
@login_required
@role_required('hotel', 'admin')
def api_update_room_status(room_id):
    """Update room status"""
    try:
        room = Room.query.get_or_404(room_id)
        
        # Validate hotel ownership
        user_id = session.get("user_id")
        hotel = Hotel.query.filter_by(id=room.hotel_id, owner_id=user_id).first()
        if not hotel:
            return jsonify({"error": "Access denied"}), 403
        
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ['available', 'booked', 'maintenance']:
            return jsonify({"error": "Invalid status"}), 400
        
        room.status = new_status
        room.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            "message": f"Room status updated to {new_status}",
            "room": room.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# =========================================================
# BOOKING MANAGEMENT API
# =========================================================
@app.route("/api/bookings", methods=["GET"])
@login_required
@role_required('hotel', 'admin')
def api_get_bookings():
    """Get all bookings for the logged-in hotel owner"""
    try:
        user_id = session.get("user_id")
        hotels = Hotel.query.filter_by(owner_id=user_id).all()
        hotel_ids = [h.id for h in hotels]
        
        bookings = HotelBooking.query.filter(HotelBooking.hotel_id.in_(hotel_ids)).all()
        
        return jsonify([{
            "id": b.id,
            "hotel_id": b.hotel_id,
            "room_id": b.room_id,
            "user_id": b.user_id,
            "guest_name": b.guest_name,
            "guest_email": b.guest_email,
            "guest_phone": b.guest_phone,
            "check_in": b.check_in.isoformat() if b.check_in else None,
            "check_out": b.check_out.isoformat() if b.check_out else None,
            "guests": b.guests,
            "rooms": b.rooms,
            "total_price": b.total_price,
            "status": b.status,
            "special_requests": b.special_requests,
            "booking_date": b.booking_date.isoformat() if b.booking_date else None
        } for b in bookings])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/bookings/<int:booking_id>/status", methods=["PUT"])
@login_required
@role_required('hotel', 'admin')
def api_update_booking_status(booking_id):
    """Update booking status"""
    try:
        booking = HotelBooking.query.get_or_404(booking_id)
        
        # Validate hotel ownership
        user_id = session.get("user_id")
        hotel = Hotel.query.filter_by(id=booking.hotel_id, owner_id=user_id).first()
        if not hotel:
            return jsonify({"error": "Access denied"}), 403
        
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ['pending', 'confirmed', 'cancelled', 'completed']:
            return jsonify({"error": "Invalid status"}), 400
        
        booking.status = new_status
        db.session.commit()
        
        return jsonify({
            "message": f"Booking status updated to {new_status}",
            "booking": {
                "id": booking.id,
                "status": booking.status
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# --------- TRANSPORT ROUTES ---------
# High-quality online images for each vehicle type from Unsplash
TRANSPORT_IMAGES = {
    "car": "https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?auto=format&fit=crop&w=800&q=80",  # Modern car
    "taxi": "https://images.unsplash.com/photo-1583508915901-b5f84c1dcde1?auto=format&fit=crop&w=800&q=80",  # Yellow taxi
    "bus": "https://images.unsplash.com/photo-1544620347-c4fd4a3d5957?auto=format&fit=crop&w=800&q=80",  # Tourist bus
    "van": "https://images.unsplash.com/photo-1527786356703-4b100091cd2c?auto=format&fit=crop&w=800&q=80",  # White van
    "suv": "https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?auto=format&fit=crop&w=800&q=80",  # Black SUV
    "sedan": "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=800&q=80",  # Luxury sedan
    "tempo": "https://images.unsplash.com/photo-1581291518857-4e27b48ff24e?auto=format&fit=crop&w=800&q=80",  # Tempo traveller
    "mini bus": "https://images.unsplash.com/photo-1570125909232-eb263c188f7e?auto=format&fit=crop&w=800&q=80",  # Mini bus
    "minibus": "https://images.unsplash.com/photo-1570125909232-eb263c188f7e?auto=format&fit=crop&w=800&q=80",  # Mini bus (alternate spelling)
    "luxury car": "https://images.unsplash.com/photo-1563720360172-67b8f3dce741?auto=format&fit=crop&w=800&q=80",  # Luxury sports car
    "hatchback": "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?auto=format&fit=crop&w=800&q=80",  # Hatchback
    "coupe": "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=80",  # Coupe
    "convertible": "https://images.unsplash.com/photo-1544829099-b9a0c07fad1a?auto=format&fit=crop&w=800&q=80",  # Convertible
    "pickup": "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?auto=format&fit=crop&w=800&q=80",  # Pickup truck
    "default": "https://images.unsplash.com/photo-1449965408869-eaa3f722e40d?auto=format&fit=crop&w=800&q=80"  # Generic vehicle
}

@app.route("/transports", methods=["GET"])
def transports():
    """Display all available transport services with static images"""
    # Fetch all transports and close the connection immediately
    transports_list = Transport.query.all()
    
    # Convert to list of dicts with appropriate images
    transports_data = []
    for t in transports_list:
        # Get image based on vehicle type
        vehicle_type_lower = t.vehicle_type.lower()
        image_url = TRANSPORT_IMAGES.get(vehicle_type_lower, TRANSPORT_IMAGES["default"])
        
        transports_data.append({
            "id": t.id,
            "name": t.agency_name,
            "agency_name": t.agency_name,
            "type": t.vehicle_type,
            "vehicle_type": t.vehicle_type,
            "description": getattr(t, 'description', f"{t.vehicle_type} service with {t.seats} seats capacity."),
            "image_url": image_url,
            "seats": t.seats,
            "capacity": t.seats,
            "price_per_km": t.price_per_km,
            "price": t.price_per_km,
            "routes": "All major routes across Maharashtra",
            "features": ["24/7 Service", "Experienced Drivers", "Insurance Covered", "GPS Tracking"]
        })

    return render_template("transports.html", transports=transports_data, transports_data=transports_data)


# --------- PROFILE ROUTES ---------
@app.route("/profile")
@login_required
def profile():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please login first", "warning")
        return redirect(url_for("login"))
    
    user = User.query.get(user_id)
    if not user:
        flash("User not found!", "danger")
        return redirect(url_for("login"))
    
    # Get or create enhanced traveler profile
    profile = TravelerProfile.query.filter_by(user_id=user_id).first()
    
    if not profile:
        # Create default profile with data from registration
        profile = TravelerProfile(
            user_id=user_id,
            full_name=user.username,  # Pre-fill from registration
            mobile=user.mobile if hasattr(user, 'mobile') else None,  # Pre-fill mobile from registration
            profile_completion=25  # Base completion
        )
        db.session.add(profile)
        db.session.commit()
    
    # Get enhanced profile data
    travel_history = TravelHistory.query.filter_by(user_id=user_id).all()
    wishlist_items = Wishlist.query.filter_by(user_id=user_id).all()
    user_reviews = UserReview.query.filter_by(user_id=user_id).all()
    notification_prefs = NotificationPreference.query.filter_by(user_id=user_id).first()
    
    # Create notification preferences if not exist
    if not notification_prefs:
        notification_prefs = NotificationPreference(user_id=user_id)
        db.session.add(notification_prefs)
        db.session.commit()
    
    # Fetch real-time data based on user role
    profile_data = {
        'user': user,
        'profile': profile,
        'travel_history': travel_history,
        'wishlist_items': wishlist_items,
        'user_reviews': user_reviews,
        'notification_preferences': notification_prefs,
        'stats': get_user_stats(user),
        'recent_activity': get_recent_activity(user),
        'bookings': [],
        'itineraries': [],
        'hotels': [],
        'packages': [],
        'transports': []
    }
    
    # Role-specific data
    if user.role == 'traveler':
        profile_data['bookings'] = get_traveler_bookings(user_id)
        profile_data['itineraries'] = get_traveler_itineraries(user_id)
    elif user.role == 'hotel':
        profile_data['hotels'] = get_hotel_owner_hotels(user_id)
    elif user.role == 'transport':
        profile_data['transports'] = get_transport_owner_vehicles(user_id)
    elif user.role == 'travelagency':
        profile_data['packages'] = get_agency_packages(user_id)
    elif user.role == 'admin':
        profile_data['admin_stats'] = get_admin_stats()
    
    return render_template("profile.html", **profile_data)


def get_user_stats(user):
    """Get user statistics based on role"""
    stats = {
        'member_since': user.created_at.strftime('%Y') if hasattr(user, 'created_at') and user.created_at else '2024'
    }
    
    if user.role == 'traveler':
        stats['total_bookings'] = HotelBooking.query.filter_by(user_id=user.id).count() + \
                                 PackageBooking.query.filter_by(user_id=user.id).count() + \
                                 TourBooking.query.filter_by(user_id=user.id).count()
        stats['total_itineraries'] = Itinerary.query.filter_by(user_id=user.id).count()
        stats['total_spent'] = sum(booking.total_price for booking in 
                                 HotelBooking.query.filter_by(user_id=user.id).all()) + \
                               sum(booking.total_price for booking in 
                                 PackageBooking.query.filter_by(user_id=user.id).all()) + \
                               sum(booking.total_price for booking in 
                                 TourBooking.query.filter_by(user_id=user.id).all())
    
    elif user.role == 'hotel':
        hotels = Hotel.query.filter_by(owner_id=user.id).all()
        stats['total_hotels'] = len(hotels)
        stats['total_bookings'] = sum(len(hotel.bookings) for hotel in hotels)
        stats['total_revenue'] = sum(sum(booking.total_price for booking in hotel.bookings) for hotel in hotels)
    
    elif user.role == 'transport':
        transports = Transport.query.filter_by(owner_id=user.id).all()
        stats['total_vehicles'] = len(transports)
        # Add transport booking logic if available
    
    elif user.role == 'travelagency':
        packages = TravelPackage.query.filter_by(agency_id=user.id).all()
        stats['total_packages'] = len(packages)
        stats['total_bookings'] = sum(len(package.bookings) for package in packages)
        stats['total_revenue'] = sum(sum(booking.total_price for booking in package.bookings) for package in packages)
    
    return stats


def get_recent_activity(user):
    """Get recent activity for the user"""
    activities = []
    
    if user.role == 'traveler':
        # Recent hotel bookings
        recent_bookings = HotelBooking.query.filter_by(user_id=user.id)\
                                         .order_by(HotelBooking.booking_date.desc())\
                                         .limit(3).all()
        for booking in recent_bookings:
            activities.append({
                'type': 'hotel_booking',
                'title': f'Booked {booking.hotel.hotel_name}',
                'date': booking.booking_date,
                'status': booking.status,
                'price': booking.total_price
            })
        
        # Recent package bookings
        recent_packages = PackageBooking.query.filter_by(user_id=user.id)\
                                            .order_by(PackageBooking.booking_date.desc())\
                                            .limit(3).all()
        for booking in recent_packages:
            activities.append({
                'type': 'package_booking',
                'title': f'Booked {booking.package.title}',
                'date': booking.booking_date,
                'status': booking.status,
                'price': booking.total_price
            })
        
        # Recent itineraries
        recent_itineraries = Itinerary.query.filter_by(user_id=user.id)\
                                          .order_by(Itinerary.created_at.desc())\
                                          .limit(3).all()
        for itinerary in recent_itineraries:
            activities.append({
                'type': 'itinerary',
                'title': f'Created {itinerary.days}-day itinerary for {itinerary.destination.name}',
                'date': itinerary.created_at,
                'status': 'active'
            })
    
    elif user.role == 'hotel':
        # Recent hotel bookings
        hotels = Hotel.query.filter_by(owner_id=user.id).all()
        for hotel in hotels:
            recent_bookings = HotelBooking.query.filter_by(hotel_id=hotel.id)\
                                             .order_by(HotelBooking.booking_date.desc())\
                                             .limit(2).all()
            for booking in recent_bookings:
                activities.append({
                    'type': 'hotel_booking',
                    'title': f'New booking for {hotel.hotel_name}',
                    'date': booking.booking_date,
                    'status': booking.status,
                    'price': booking.total_price
                })
    
    elif user.role == 'travelagency':
        # Recent package bookings
        packages = TravelPackage.query.filter_by(agency_id=user.id).all()
        for package in packages:
            recent_bookings = PackageBooking.query.filter_by(package_id=package.id)\
                                               .order_by(PackageBooking.booking_date.desc())\
                                               .limit(2).all()
            for booking in recent_bookings:
                activities.append({
                    'type': 'package_booking',
                    'title': f'New booking for {package.title}',
                    'date': booking.booking_date,
                    'status': booking.status,
                    'price': booking.total_price
                })
    
    # Sort by date and return latest 5
    activities.sort(key=lambda x: x['date'], reverse=True)
    return activities[:5]


def get_traveler_bookings(user_id):
    """Get traveler's bookings"""
    bookings = []
    
    # Hotel bookings
    hotel_bookings = HotelBooking.query.filter_by(user_id=user_id)\
                                     .order_by(HotelBooking.booking_date.desc())\
                                     .limit(10).all()
    
    for booking in hotel_bookings:
        bookings.append({
            'type': 'hotel',
            'id': booking.id,
            'hotel_name': booking.hotel.hotel_name,
            'location': f"{booking.hotel.city}, {booking.hotel.area}",
            'check_in': booking.check_in,
            'check_out': booking.check_out,
            'guests': booking.guests,
            'total_price': booking.total_price,
            'status': booking.status,
            'booking_date': booking.booking_date,
            'hotel_image': booking.hotel.main_image
        })
    
    # Package bookings
    package_bookings = PackageBooking.query.filter_by(user_id=user_id)\
                                        .order_by(PackageBooking.booking_date.desc())\
                                        .limit(10).all()
    
    for booking in package_bookings:
        bookings.append({
            'type': 'package',
            'id': booking.id,
            'package_title': booking.package.title,
            'location': booking.package.location,
            'duration': booking.package.duration,
            'travelers': booking.travelers_count,
            'total_price': booking.total_price,
            'status': booking.status,
            'booking_date': booking.booking_date,
            'package_image': booking.package.images[0].image_url if booking.package.images else None
        })
    
    # Tour bookings
    tour_bookings = TourBooking.query.filter_by(user_id=user_id)\
                                   .order_by(TourBooking.booking_date.desc())\
                                   .limit(10).all()
    
    for booking in tour_bookings:
        bookings.append({
            'type': 'tour',
            'id': booking.id,
            'tour_title': booking.tour.title,
            'location': booking.tour.location,
            'tour_date': booking.tour_date,
            'travelers': booking.travelers_count,
            'total_price': booking.total_price,
            'status': booking.status,
            'booking_date': booking.booking_date,
            'tour_image': None  # Add tour image if available
        })
    
    return bookings


def get_traveler_itineraries(user_id):
    """Get traveler's itineraries"""
    itineraries = Itinerary.query.filter_by(user_id=user_id)\
                               .order_by(Itinerary.created_at.desc())\
                               .limit(10).all()
    
    result = []
    for itinerary in itineraries:
        result.append({
            'id': itinerary.id,
            'destination': itinerary.destination.name,
            'city': itinerary.city,
            'days': itinerary.days,
            'created_at': itinerary.created_at,
            'destination_image': itinerary.destination.image_url
        })
    
    return result


def get_hotel_owner_hotels(user_id):
    """Get hotels owned by hotel owner"""
    hotels = Hotel.query.filter_by(owner_id=user_id).all()
    
    result = []
    for hotel in hotels:
        result.append({
            'id': hotel.id,
            'hotel_name': hotel.hotel_name,
            'city': hotel.city,
            'area': hotel.area,
            'rating': hotel.rating_score,
            'total_reviews': hotel.total_reviews,
            'price': hotel.discounted_price,
            'bookings_count': len(hotel.bookings),
            'revenue': sum(booking.total_price for booking in hotel.bookings),
            'main_image': hotel.main_image,
            'status': 'active'  # Add status logic if needed
        })
    
    return result



def get_admin_stats():
    """Get platform statistics for admin"""
    from models import User, Hotel, Transport, TravelPackage, HotelBooking, PackageBooking, HotelReview
    
    stats = {
        'total_users': User.query.count(),
        'total_hotels': Hotel.query.count(),
        'total_transports': Transport.query.count(),
        'total_packages': TravelPackage.query.count(),
        'total_bookings': HotelBooking.query.count() + PackageBooking.query.count(),
        'total_reviews': HotelReview.query.count(),
        'total_agencies': User.query.filter_by(role='travelagency').count(),
        'total_revenue': sum(booking.total_price for booking in HotelBooking.query.all()) + \
                        sum(booking.total_price for booking in PackageBooking.query.all())
    }
    
    return stats


# Profile API endpoints
@app.route("/api/profile/basic", methods=["GET", "POST"])
@login_required
def api_profile_basic():
    """API endpoint for basic profile information"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    user = User.query.get(user_id)
    profile = TravelerProfile.query.filter_by(user_id=user_id).first()
    
    if request.method == "GET":
        # Get data from both User table and TravelerProfile
        data = {
            "email": user.email if user else "",
            "username": user.username if user else "",
            "mobile": user.mobile if (user and hasattr(user, 'mobile')) else "",  # Get mobile from User table (registration data)
        }
        
        if profile:
            data.update({
                "full_name": profile.full_name,
                "gender": profile.gender,
                "date_of_birth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
                "nationality": profile.nationality,
                "language_preference": profile.language_preference,
                "city": profile.city,
                "state": profile.state,
                "country": profile.country
            })
        else:
            # If no profile exists yet, pre-fill with registration data
            data.update({
                "full_name": user.username if user else "",
                "mobile": user.mobile if (user and hasattr(user, 'mobile')) else "",
            })
        
        return jsonify({"success": True, "data": data})
    
    elif request.method == "POST":
        data = request.get_json()
        
        if not profile:
            # Create profile with registration data pre-filled
            profile = TravelerProfile(
                user_id=user_id,
                full_name=user.username if user else '',
                mobile=user.mobile if (user and hasattr(user, 'mobile')) else None
            )
            db.session.add(profile)
        
        # Update profile fields
        profile.full_name = data.get('full_name', profile.full_name)
        profile.mobile = data.get('mobile', profile.mobile)
        profile.gender = data.get('gender')
        profile.nationality = data.get('nationality')
        profile.language_preference = data.get('language_preference')
        profile.city = data.get('city')
        profile.state = data.get('state')
        profile.country = data.get('country')
        
        # Also update mobile in User table if provided
        if user and data.get('mobile'):
            user.mobile = data.get('mobile')
        
        # Handle date of birth
        if data.get('date_of_birth'):
            try:
                from datetime import datetime
                profile.date_of_birth = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Calculate profile completion
        completion = calculate_profile_completion(profile)
        profile.profile_completion = completion
        profile.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": "Profile updated successfully",
            "completion": completion
        })

@app.route("/api/profile/preferences", methods=["GET", "POST"])
@login_required
def api_profile_preferences():
    """API endpoint for travel preferences"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    profile = TravelerProfile.query.filter_by(user_id=user_id).first()
    
    if request.method == "GET":
        if profile:
            return jsonify({
                "success": True,
                "data": {
                    "travel_type": profile.travel_type,
                    "budget_range": profile.budget_range,
                    "travel_frequency": profile.travel_frequency,
                    "preferred_destinations": profile.preferred_destinations
                }
            })
        else:
            return jsonify({"success": True, "data": {}})
    
    elif request.method == "POST":
        data = request.get_json()
        
        if not profile:
            profile = TravelerProfile(user_id=user_id)
            db.session.add(profile)
        
        # Update preferences
        profile.travel_type = data.get('travel_type')
        profile.budget_range = data.get('budget_range')
        profile.travel_frequency = data.get('travel_frequency')
        profile.preferred_destinations = data.get('preferred_destinations')
        
        # Calculate profile completion
        completion = calculate_profile_completion(profile)
        profile.profile_completion = completion
        profile.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": "Preferences updated successfully",
            "completion": completion
        })

@app.route("/api/profile/trips")
@login_required
def api_profile_trips():
    """API endpoint for user trips"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    # Get real user's bookings from database
    user = User.query.get(user_id)
    trips = []
    
    if user:
        # Get hotel bookings
        hotel_bookings = HotelBooking.query.filter_by(user_id=user_id).all()
        for booking in hotel_bookings:
            hotel = Hotel.query.get(booking.hotel_id)
            if hotel:
                trips.append({
                    "id": booking.id,
                    "title": f"{hotel.name}",
                    "description": f"Hotel Stay • {booking.check_in} to {booking.check_out}",
                    "dates": f"{booking.check_in} - {booking.check_out}",
                    "cost": f"₹{booking.total_price} for {booking.guests} guests",
                    "status": "upcoming" if datetime.strptime(booking.check_in, '%Y-%m-%d').date() > datetime.now().date() else "completed",
                    "image": "https://picsum.photos/seed/hotel/300/200"
                })
        
        # Get package bookings
        package_bookings = PackageBooking.query.filter_by(user_id=user_id).all()
        for booking in package_bookings:
            package = TravelPackage.query.get(booking.package_id)
            if package:
                trips.append({
                    "id": booking.id,
                    "title": f"{package.name}",
                    "description": f"Travel Package • {booking.booking_date}",
                    "dates": f"{booking.booking_date}",
                    "cost": f"₹{booking.total_price} for {booking.travelers} travelers",
                    "status": "upcoming",
                    "image": "https://picsum.photos/seed/package/300/200"
                })
        
        # Get tour bookings
        tour_bookings = TourBooking.query.filter_by(user_id=user_id).all()
        for booking in tour_bookings:
            tour = Tour.query.get(booking.tour_id)
            if tour:
                trips.append({
                    "id": booking.id,
                    "title": f"{tour.name}",
                    "description": f"Tour • {tour.duration}",
                    "dates": f"{booking.booking_date}",
                    "cost": f"₹{booking.total_price} for {booking.travelers} travelers",
                    "status": "completed",
                    "rating": 4.5,
                    "review": "Amazing tour experience!",
                    "image": "https://picsum.photos/seed/tour/300/200"
                })
    
    return jsonify({"success": True, "data": trips})

@app.route("/api/profile/wishlist", methods=["GET", "POST", "DELETE"])
@login_required
def api_profile_wishlist():
    """API endpoint for wishlist"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    if request.method == "GET":
        # Get real user's wishlist items from database
        profile = TravelerProfile.query.filter_by(user_id=user_id).first()
        wishlist = []
        
        if profile and profile.preferred_destinations:
            # Convert preferred destinations to wishlist items
            destinations = profile.preferred_destinations.split(',')
            for dest in destinations:
                dest = dest.strip()
                if dest:
                    wishlist.append({
                        "id": len(wishlist) + 1,
                        "title": dest,
                        "description": f"Saved destination • Explore {dest}",
                        "image": f"https://picsum.photos/seed/{dest.lower().replace(' ', '')}/300/200"
                    })
        
        # If no wishlist items, show some popular destinations
        if not wishlist:
            wishlist = [
                {
                    "id": 1,
                    "title": "Maldives Paradise",
                    "description": "Luxury beach resort • 7 Days Package",
                    "image": "https://picsum.photos/seed/maldives/300/200"
                },
                {
                    "id": 2,
                    "title": "Rajasthan Heritage Tour",
                    "description": "Historical monuments • 5 Days Package",
                    "image": "https://picsum.photos/seed/rajasthan/300/200"
                }
            ]
        
        return jsonify({"success": True, "data": wishlist})
    
    elif request.method == "POST":
        # Add item to wishlist
        data = request.get_json()
        profile = TravelerProfile.query.filter_by(user_id=user_id).first()
        
        if not profile:
            profile = TravelerProfile(user_id=user_id)
            db.session.add(profile)
        
        # Add to preferred destinations
        item_title = data.get('title', '')
        if item_title:
            current_destinations = profile.preferred_destinations or ''
            destinations_list = current_destinations.split(',') if current_destinations else []
            
            if item_title not in destinations_list:
                destinations_list.append(item_title)
                profile.preferred_destinations = ', '.join(destinations_list)
                db.session.commit()
        
        return jsonify({"success": True, "message": "Added to wishlist"})
    
    elif request.method == "DELETE":
        # Remove item from wishlist
        data = request.get_json()
        item_id = data.get('item_id')
        profile = TravelerProfile.query.filter_by(user_id=user_id).first()
        
        if profile and profile.preferred_destinations:
            destinations_list = profile.preferred_destinations.split(',')
            if 0 <= item_id - 1 < len(destinations_list):
                destinations_list.pop(item_id - 1)
                profile.preferred_destinations = ', '.join(destinations_list)
                db.session.commit()
        
        return jsonify({"success": True, "message": "Removed from wishlist"})

@app.route("/api/profile/reviews", methods=["GET", "POST"])
@login_required
def api_profile_reviews():
    """API endpoint for reviews"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    if request.method == "GET":
        # Get real user's reviews from database
        reviews = []
        
        # Get hotel reviews by this user
        hotel_reviews = HotelReview.query.filter_by(user_id=user_id).all()
        for review in hotel_reviews:
            hotel = Hotel.query.get(review.hotel_id)
            if hotel:
                reviews.append({
                    "id": review.id,
                    "trip_title": f"{hotel.name}",
                    "rating": review.rating,
                    "review_text": review.comment,
                    "review_date": review.created_at.strftime('%b %d, %Y') if review.created_at else 'Recent'
                })
        
        # Get travel history reviews
        travel_history = TravelHistory.query.filter_by(user_id=user_id).all()
        for history in travel_history:
            if history.rating and history.review:
                reviews.append({
                    "id": history.id,
                    "trip_title": history.destination or f"Trip to {history.destination}",
                    "rating": history.rating,
                    "review_text": history.review,
                    "review_date": history.travel_date.strftime('%b %d, %Y') if history.travel_date else 'Recent'
                })
        
        # If no reviews, show sample reviews
        if not reviews:
            reviews = [
                {
                    "id": 1,
                    "trip_title": "Your First Trip",
                    "rating": 5.0,
                    "review_text": "Write your first review after completing a trip!",
                    "review_date": "Recent"
                }
            ]
        
        return jsonify({"success": True, "data": reviews})
    
    elif request.method == "POST":
        # Add new review
        data = request.get_json()
        profile = TravelerProfile.query.filter_by(user_id=user_id).first()
        
        if not profile:
            profile = TravelerProfile(user_id=user_id)
            db.session.add(profile)
        
        # Create travel history with review
        travel_history = TravelHistory(
            user_id=user_id,
            destination=data.get('trip_title', 'Unknown Destination'),
            rating=data.get('rating'),
            review=data.get('review_text'),
            travel_date=datetime.now()
        )
        
        db.session.add(travel_history)
        db.session.commit()
        
        return jsonify({"success": True, "message": "Review added successfully"})

@app.route("/api/profile/notifications", methods=["GET", "POST"])
@login_required
def api_profile_notifications():
    """API endpoint for notification preferences"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    if request.method == "GET":
        # Get real user's notification preferences from database
        notification_prefs = NotificationPreference.query.filter_by(user_id=user_id).first()
        
        if notification_prefs:
            preferences = {
                "trip_reminders": notification_prefs.trip_reminders,
                "offers_discounts": notification_prefs.offers_discounts,
                "booking_confirmations": notification_prefs.booking_confirmations,
                "travel_recommendations": notification_prefs.travel_recommendations
            }
        else:
            # Default preferences if none exist
            preferences = {
                "trip_reminders": True,
                "offers_discounts": True,
                "booking_confirmations": True,
                "travel_recommendations": False
            }
        
        return jsonify({"success": True, "data": preferences})
    
    elif request.method == "POST":
        # Update notification preferences
        data = request.get_json()
        notification_prefs = NotificationPreference.query.filter_by(user_id=user_id).first()
        
        if not notification_prefs:
            notification_prefs = NotificationPreference(user_id=user_id)
            db.session.add(notification_prefs)
        
        # Update preferences
        notification_prefs.trip_reminders = data.get('trip_reminders', True)
        notification_prefs.offers_discounts = data.get('offers_discounts', True)
        notification_prefs.booking_confirmations = data.get('booking_confirmations', True)
        notification_prefs.travel_recommendations = data.get('travel_recommendations', False)
        
        db.session.commit()
        
        return jsonify({"success": True, "message": "Notification preferences updated"})

@app.route("/api/profile/upload-photo", methods=["POST"])
@login_required
def api_upload_photo():
    """API endpoint for profile photo upload"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    
    if 'photo' not in request.files:
        return jsonify({"success": False, "message": "No photo uploaded"}), 400
    
    file = request.files['photo']
    if file.filename == '':
        return jsonify({"success": False, "message": "No photo selected"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Save file and update profile
        # Implementation would save file and update database
        return jsonify({"success": True, "message": "Photo uploaded successfully"})
    
    return jsonify({"success": False, "message": "Invalid file type"}), 400

def calculate_profile_completion(profile):
    """Calculate profile completion percentage"""
    completion = 25  # Base completion
    
    if profile.full_name: completion += 5
    if profile.mobile: completion += 5
    if profile.gender: completion += 5
    if profile.date_of_birth: completion += 5
    if profile.nationality: completion += 5
    if profile.city: completion += 5
    if profile.state: completion += 5
    if profile.country: completion += 5
    if profile.travel_type: completion += 15
    if profile.budget_range: completion += 15
    if profile.travel_frequency: completion += 10
    
    return min(completion, 100)

def allowed_file(filename):
    """Check if file is allowed for upload"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Profile API endpoints
@app.route("/api/profile/stats")
@login_required
def api_profile_stats():
    """API endpoint for profile statistics"""
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify(get_user_stats(user))


@app.route("/api/profile/activity")
@login_required
def api_profile_activity():
    """API endpoint for recent activity"""
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify(get_recent_activity(user))


@app.route("/api/profile/bookings")
@login_required
def api_profile_bookings():
    """API endpoint for user bookings"""
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    if user.role != 'traveler':
        return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify(get_traveler_bookings(user_id))


@app.route("/api/profile/itineraries")
@login_required
def api_profile_itineraries():
    """API endpoint for user itineraries"""
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    if user.role != 'traveler':
        return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify(get_traveler_itineraries(user_id))


@app.route("/update_profile", methods=["POST"])
def update_profile():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please login first", "warning")
        return redirect(url_for("login"))

    user = User.query.get(user_id)
    if user:
        # Update basic info
        user.username = request.form.get("username", user.username)
        user.email = request.form.get("email", user.email)
        user.role = request.form.get("role", user.role)

        # Handle profile picture
        file = request.files.get("profile_pic")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            user.profile_pic = f"uploads/{filename}"  # store relative path

        db.session.commit()
        flash("Profile updated successfully!", "success")
    else:
        flash("User not found!", "danger")

    return redirect(url_for("profile"))

# ---------------- CONTACT FORM ----------------
EMAIL_ADDRESS = Config.EMAIL_ADDRESS
EMAIL_PASSWORD = Config.EMAIL_PASSWORD
TO_EMAIL = Config.TO_EMAIL

@app.route("/contact")
def contact_page():
    # Use template rendering instead of static file
    return render_template("contact.html")

@app.route("/api/contact", methods=["POST","GET"])
def contact():
    if request.method == "GET":
        return jsonify({"message":"Contact API ready. Use POST to send messages."})
    
    try:
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', 'Contact Form Submission').strip()
        message = request.form.get('message', '').strip()
        consent = request.form.get('consent', '').lower() in ('true', 'on', '1', 'yes')

        if not name or not email or not message or not consent:
            return jsonify({"error": "Please fill all required fields and consent."}), 400

        # Handle attachment
        file_url = None
        save_path = None
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(save_path)
                file_url = f"uploads/{filename}"

        # Save to DB
        contact_msg = ContactMessage(
            name=name,
            email=email,
            subject=subject,
            message=message,
            consent=consent,
            attachment=file_url
        )
        db.session.add(contact_msg)
        db.session.commit()

        # Send email
        try:
            msg = MIMEMultipart()
            msg['From'] = EMAIL_ADDRESS
            msg['To'] = TO_EMAIL
            msg['Subject'] = subject
            body = f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}"
            msg.attach(MIMEText(body, 'plain'))

            if file_url and save_path:
                part = MIMEBase('application', 'octet-stream')
                with open(save_path, 'rb') as f:
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename={filename}')
                msg.attach(part)

            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()
        except Exception as e:
            print(f"Email sending failed: {e}")

        return jsonify({"message": f"Thanks {name}, your message was received!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- BOOKING EMAIL FUNCTION ----------------------
def send_booking_confirmation_email(booking_data, item_details, item_type):
    """Send booking confirmation email to customer"""
    try:
        print(f"🔍 Debug: Sending email to {booking_data['email']}")
        print(f"🔍 Debug: Email config - ADDRESS: {EMAIL_ADDRESS}, PASSWORD: {'SET' if EMAIL_PASSWORD and EMAIL_PASSWORD != 'your_gmail_app_password' else 'NOT SET'}")
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = booking_data['email']
        msg['Subject'] = f"🎉 {item_type.title()} Booking Confirmation - Tripoora"
        
        # Create HTML email body
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 30px; border-radius: 10px; text-align: center;">
                <h1 style="margin: 0; font-size: 2.5em;">🎉 Booking Confirmed!</h1>
                <p style="margin: 10px 0 0 0; font-size: 1.2em;">Thank you for choosing Tripoora</p>
            </div>
            
            <div style="background: white; padding: 30px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-top: 0;">Booking Details</h2>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #667eea; margin-top: 0;">{item_type.title()} Information</h3>
                    <p><strong>{item_type.title()}:</strong> {item_details['title']}</p>
                    <p><strong>Location:</strong> {item_details.get('location', 'N/A')}</p>
                    <p><strong>Duration:</strong> {item_details.get('duration', 'N/A')}</p>
                    <p><strong>Price per Person:</strong> ₹{item_details.get('price_per_person', item_details.get('price', 0))}</p>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #667eea; margin-top: 0;">Traveler Information</h3>
                    <p><strong>Name:</strong> {booking_data['name']}</p>
                    <p><strong>Email:</strong> {booking_data['email']}</p>
                    <p><strong>Phone:</strong> {booking_data['phone']}</p>
                    <p><strong>Travel Date:</strong> {booking_data['date']}</p>
                    <p><strong>Number of Travelers:</strong> {booking_data['travelers']}</p>
                    <p><strong>Total Amount:</strong> ₹{item_details.get('price_per_person', item_details.get('price', 0)) * int(booking_data['travelers'])}</p>
                    {f"<p><strong>Special Requests:</strong> {booking_data['requests']}</p>" if booking_data.get('requests') else ""}
                </div>
                
                <div style="background: #e8f5e8; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #28a745;">
                    <h3 style="color: #28a745; margin-top: 0;">What's Next?</h3>
                    <ul style="margin: 0; padding-left: 20px;">
                        <li>Our team will contact you within 24 hours</li>
                        <li>Payment details and further instructions will be shared</li>
                        <li>You can modify or cancel your booking up to 48 hours before travel</li>
                    </ul>
                </div>
            </div>
            
            <div style="text-align: center; padding: 20px; color: #666;">
                <p>For any queries, contact us at: <a href="mailto:support@tripoora.com">support@tripoora.com</a></p>
                <p>Follow us on: <a href="#">Facebook</a> | <a href="#">Instagram</a> | <a href="#">Twitter</a></p>
                <p style="margin-top: 20px; font-size: 0.8em;">© 2024 Tripoora. All rights reserved.</p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        print(f"🔍 Debug: Attempting login to Gmail...")
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        print(f"🔍 Debug: Login successful, sending email...")
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Booking confirmation email sent to {booking_data['email']}")
        return True
        
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        print(f"❌ Email config: ADDRESS={EMAIL_ADDRESS}, PASSWORD_SET={EMAIL_PASSWORD and EMAIL_PASSWORD != 'your_gmail_app_password'}")
        return False


# ---------------------- ABOUT PAGE ----------------------
@app.route("/about")
def about():
    # Fetch all team members from DB
    team_members = TeamMember.query.all()
    return render_template("about.html", team_members=team_members)


# ---------------- TOURS ----------------

_place_image_cache = {}  # { "location|title": image_url }
FALLBACK_IMAGE = "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&fit=crop&w=800&q=80"

def fetch_place_image(location: str, title: str = "") -> str:
    """Fetch a real place image — Wikipedia first, then Google Places, then Unsplash."""
    cache_key = f"{location}|{title}"
    if cache_key in _place_image_cache:
        return _place_image_cache[cache_key]

    image_data = get_unsplash_image_api(title, location)
    url = image_data["url"]
    _place_image_cache[cache_key] = url
    return url


@app.route("/tours")
def tours():
    """Show only day trips (1D/0N) - Tours are single-day experiences"""
    try:
        # Get search/filter parameters
        search_location = request.args.get('location', '').strip()
        
        # Query TravelPackage - only day trips (1 Day / 0 Nights)
        query = TravelPackage.query.filter_by(status="active")
        
        # Filter for day trips only (duration contains "1 Day" and "0 Night")
        query = query.filter(
            db.or_(
                TravelPackage.duration.ilike('%1 Day%0 Night%'),
                TravelPackage.duration.ilike('%1D/0N%')
            )
        )
        
        # Apply location filter if provided
        if search_location:
            query = query.filter(TravelPackage.location.ilike(f'%{search_location}%'))
        
        # Get all matching tours (limit to 100 for performance)
        packages = query.limit(100).all()
        
        tours_data = []
        for pkg in packages:
            # Get image URL
            image_url = "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&fit=crop&w=800&q=80"
            if pkg.images and len(pkg.images) > 0:
                image_url = pkg.images[0].image_url
            
            tour_dict = {
                'id': pkg.id,
                'title': pkg.title,
                'description': f"{pkg.duration} - {pkg.activities or 'Explore local attractions'}",
                'location': pkg.location,
                'price': float(pkg.price_per_person) if pkg.price_per_person else 0,
                'active': True,
                'image_url': image_url,
                'image_alt_text': pkg.title,
                'duration': pkg.duration,
                'hotel': pkg.hotel,
                'meals': pkg.meals,
                'activities': pkg.activities,
                'complimentary': pkg.complimentary
            }
            tours_data.append(tour_dict)

        return render_template("tours.html", tours=tours_data, search_location=search_location)
    except Exception as e:
        db.session.rollback()
        print(f"Error in tours route: {e}")
        import traceback
        traceback.print_exc()
        return render_template("tours.html", tours=[])
    finally:
        db.session.close()

@app.route("/api/tours", methods=["GET"])
def get_tours():
    """API endpoint to get all tours"""
    try:
        tours = Tour.query.filter_by(active=True).all()
        tours_data = [tour.to_dict() for tour in tours]
        return jsonify({
            "success": True,
            "tours": tours_data,
            "count": len(tours_data)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/packages")
def packages():
    """Show multi-day packages (2D/1N and above) - Complete travel packages with accommodation"""
    # Get search/filter parameters
    search_location = request.args.get('location', '').strip()
    
    # Build query - only multi-day packages (2+ days)
    query = TravelPackage.query.filter_by(status="active")
    
    # Filter for multi-day packages (NOT 1D/0N)
    query = query.filter(
        db.and_(
            ~TravelPackage.duration.ilike('%1 Day%0 Night%'),
            ~TravelPackage.duration.ilike('%1D/0N%')
        )
    )
    
    # Apply location filter if provided
    if search_location:
        query = query.filter(TravelPackage.location.ilike(f'%{search_location}%'))
    
    # Get all matching packages (or limit to 100 for performance)
    travel_packages = query.limit(100).all()
    
    # Build packages data efficiently
    packages_data = []
    for pkg in travel_packages:
        packages_data.append({
            'id': pkg.id,
            'title': pkg.title,
            'location': pkg.location,
            'duration': pkg.duration,
            'hotel': pkg.hotel,
            'meals': pkg.meals,
            'activities': pkg.activities,
            'complimentary': pkg.complimentary,
            'price_per_person': pkg.price_per_person,
            'status': pkg.status,
            'created_at': pkg.created_at.isoformat() if pkg.created_at else None,
            'image_url': pkg.images[0].image_url if pkg.images else None
        })
    
    return render_template("packages.html", packages=packages_data, search_location=search_location)


# ---------------- BOOKING API ENDPOINTS ----------------------
@app.route("/api/book-tour", methods=["POST"])
@login_required
@role_required('traveler', 'admin')
def book_tour():
    try:
        data = request.get_json()
        
        # Get tour details
        tour = Tour.query.get(data['tourId'])
        if not tour:
            return jsonify({"error": "Tour not found"}), 404
        
        # Create tour booking in database
        user_id = session.get('user_id')
        
        # Parse date string to date object
        from datetime import datetime
        tour_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        
        booking = TourBooking(
            tour_id=tour.id,
            user_id=user_id,
            tour_date=tour_date,
            travelers_count=int(data['travelers']),
            total_price=tour.price * int(data['travelers']),
            guest_name=data['name'],
            guest_email=data['email'],
            guest_phone=data['phone'],
            special_requests=data.get('requests', '')
        )
        
        db.session.add(booking)
        db.session.commit()
        
        booking_data = {
            'name': data['name'],
            'email': data['email'],
            'phone': data['phone'],
            'date': data['date'],
            'travelers': data['travelers'],
            'requests': data.get('requests', ''),
            'booking_id': f"TOUR_{booking.id}"
        }
        
        # Send booking confirmation email
        email_sent = send_booking_confirmation_email(
            booking_data, 
            tour.to_dict(), 
            'tour'
        )
        
        if email_sent:
            return jsonify({
                "message": "Tour booking confirmed! Check your email for details.",
                "booking_id": f"TOUR_{booking.id}"
            }), 200
        else:
            return jsonify({
                "message": "Tour booking confirmed, but email failed to send. Please contact support.",
                "booking_id": f"TOUR_{booking.id}"
            }), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/book-package", methods=["POST"])
@login_required
@role_required('traveler')
def book_package():
    """Only travelers can book packages"""
    try:
        data = request.get_json()
        
        # Get package details
        package = TravelPackage.query.get(data['packageId'])
        if not package:
            return jsonify({"error": "Package not found"}), 404
        
        booking_data = {
            'name': data['name'],
            'email': data['email'],
            'phone': data['phone'],
            'date': data['date'],
            'travelers': data['travelers'],
            'requests': data.get('requests', '')
        }
        
        # Send booking confirmation email
        email_sent = send_booking_confirmation_email(
            booking_data, 
            package.to_dict(), 
            'package'
        )
        
        if email_sent:
            return jsonify({
                "message": "Package booking confirmed! Check your email for details.",
                "booking_id": f"PKG_{package.id}_{int(datetime.utcnow().timestamp())}"
            }), 200
        else:
            return jsonify({
                "message": "Package booking confirmed, but email failed to send. Please contact support.",
                "booking_id": f"PKG_{package.id}_{int(datetime.utcnow().timestamp())}"
            }), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/add_tour", methods=["GET", "POST"])
@login_required
@role_required('travelagency', 'admin')
def add_tour():
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        location = request.form["location"]
        price = float(request.form["price"])

        tour = Tour(title=title, description=description, location=location, price=price)
        db.session.add(tour)
        db.session.commit()
        flash("Tour added successfully!", "success")
        return redirect(url_for("tours"))

    return render_template("add_tour.html")









#-------------Itinerary-----------------------------------------------------------------------------------------------------------------------------------


genai.configure(api_key=os.getenv("ITINERARY_API_KEY"))

# Sample destinations data
destinations_data = [
    {
        "name": "Mumbai",
        "state": "Maharashtra",
        "description": "The financial capital of India, known for Bollywood, vibrant nightlife, and iconic landmarks like Gateway of India.",
        "image": "uploads/Mumbai.jpg",
        "category": "Metropolitan",
        "rating": 4.5,
        "price": "₹5,000 - ₹15,000",
        "reviews": 1250
    },
    {
        "name": "Pune",
        "state": "Maharashtra",
        "description": "Oxford of the East, blend of traditional culture and modern lifestyle, surrounded by hills and forts.",
        "image": "uploads/Pune.jpg",
        "category": "Cultural",
        "rating": 4.3,
        "price": "₹3,000 - ₹10,000",
        "reviews": 890
    },
    {
        "name": "Nashik",
        "state": "Maharashtra",
        "description": "Wine capital of India, ancient pilgrimage center on the banks of Godavari river.",
        "image": "uploads/Nashik.jpg",
        "category": "Religious",
        "rating": 4.2,
        "price": "₹2,500 - ₹8,000",
        "reviews": 567
    },
    {
        "name": "Aurangabad",
        "state": "Maharashtra",
        "description": "Historic city famous for Ajanta and Ellora caves, UNESCO World Heritage sites.",
        "image": "uploads/Aurangabad.jpg",
        "category": "Historical",
        "rating": 4.4,
        "price": "₹3,500 - ₹12,000",
        "reviews": 743
    },
    {
        "name": "Nagpur",
        "state": "Maharashtra",
        "description": "Orange capital of India, major trade center, gateway to tiger reserves.",
        "image": "uploads/Nagpur.jpg",
        "category": "Urban",
        "rating": 4.1,
        "price": "₹2,000 - ₹7,000",
        "reviews": 445
    },
    {
        "name": "Lonavala",
        "state": "Maharashtra",
        "description": "Hill station known for scenic valleys, forts, and monsoon beauty.",
        "image": "uploads/Lonavala.jpg",
        "category": "Hill Station",
        "rating": 4.6,
        "price": "₹4,000 - ₹12,000",
        "reviews": 1102
    },
    {
        "name": "Mahabaleshwar",
        "state": "Maharashtra",
        "description": "Strawberry garden of Maharashtra, highest hill station with stunning viewpoints.",
        "image": "uploads/Mahabaleshwar.jpg",
        "category": "Hill Station",
        "rating": 4.7,
        "price": "₹5,000 - ₹15,000",
        "reviews": 1289
    },
    {
        "name": "Shirdi",
        "state": "Maharashtra",
        "description": "Sacred pilgrimage site of Sai Baba, spiritual destination attracting millions.",
        "image": "uploads/Shirdi.jpg",
        "category": "Religious",
        "rating": 4.8,
        "price": "₹1,500 - ₹6,000",
        "reviews": 2156
    },
    {
        "name": "Ganapatipule",
        "state": "Maharashtra",
        "description": "Beach destination with ancient Ganesh temple, pristine coastline.",
        "image": "uploads/Ganapatipule.jpg",
        "category": "Beach",
        "rating": 4.5,
        "price": "₹3,000 - ₹10,000",
        "reviews": 678
    },
    {
        "name": "Tarkarli",
        "state": "Maharashtra",
        "description": "Crystal clear waters, water sports paradise, and coral beaches.",
        "image": "uploads/Tarkarli.jpg",
        "category": "Beach",
        "rating": 4.6,
        "price": "₹4,000 - ₹12,000",
        "reviews": 534
    }
]

# ----------- Show Generate Itinerary Page ----------
@app.route("/generate_itinerary_page")
@login_required
@role_required('traveler', 'admin')
def generate_itinerary_page():
    return render_template("generate_itinerary.html")


# ----------- Generate Itinerary (POST) ----------
@app.route("/generate_itinerary", methods=["POST"])
@login_required
@role_required('traveler', 'admin')
def generate_itinerary():
    city = request.form.get("city")
    days = int(request.form.get("days"))
    preference = request.form.get("preference")

    # Use Gemini to generate trip plan
    model = genai.GenerativeModel("gemini-flash-latest")
    prompt = f"Create a {days}-day travel itinerary for {city} focusing on {preference}. Include daily activities."
    response = model.generate_content(prompt)

    # Extract text response
    itinerary_text = response.text if response and response.text else "No response from Gemini."

    # --- Save to DB ---
    user_id = session.get('user_id')
    destination = Destination.query.filter_by(name=city).first()
    if not destination:
        destination = Destination(name=city, state="Maharashtra", description="")
        db.session.add(destination)
        db.session.commit()

    new_itinerary = Itinerary(
        city=city,
        user_id=user_id,
        destination_id=destination.id,
        days=days,
        plan=itinerary_text
    )
    db.session.add(new_itinerary)
    db.session.commit()

    # Show result
    return render_template(
        "result.html",
        city=city,
        days=days,
        preference=preference,
        itinerary=itinerary_text
    )

# ----------- Save User ----------
@app.route("/save_user", methods=["POST"])
def save_user():
    username = request.form.get("username")
    email = request.form.get("email")

    user = User(username=username, email=email)
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "User saved successfully!"})


# ----------- Get Users ----------
@app.route("/users", methods=["GET"])
def get_users():
    users = User.query.all()
    return jsonify([{"id": u.id, "username": u.username, "email": u.email} for u in users])


# ----------- List Itineraries (JSON) ----------
@app.route("/itineraries", methods=["GET"])
@login_required
@role_required('traveler', 'admin')
def itineraries():
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    # Admin can see all itineraries, others only see their own
    if user_role == 'admin':
        itineraries = Itinerary.query.order_by(Itinerary.created_at.desc()).all()
    else:
        itineraries = Itinerary.query.filter_by(user_id=user_id).order_by(Itinerary.created_at.desc()).all()
    
    # Convert SQLAlchemy objects to JSON-serializable dictionaries
    itineraries_data = []
    for itinerary in itineraries:
        itineraries_data.append({
            "id": itinerary.id,
            "city": itinerary.city,
            "days": itinerary.days,
            "plan": itinerary.plan,
            "created_at": itinerary.created_at.isoformat() if itinerary.created_at else None,
            "user_id": itinerary.user_id,
            "destination_id": itinerary.destination_id
        })
    
    return render_template("itinerary.html", itineraries=itineraries_data)



# ----------- Show Itinerary Page ----------
@app.route("/itinerary")
def show_itinerary():
    itinerary = Itinerary.query.order_by(Itinerary.created_at.desc()).first()
    if itinerary:
        return render_template(
            "itinerary.html",
            city=itinerary.city,
            days=itinerary.days,
            preference="N/A",  # Add preference column if you want to save it
            itinerary=itinerary.plan
        )
    else:
        return render_template(
            "itinerary.html",
            city="",
            days=0,
            preference="",
            itinerary="No itinerary found yet. Start planning your dream trip!"
        )


# ----------- API: Get All Destinations ----------
@app.route("/api/destinations", methods=["GET"])
def get_destinations():
    category = request.args.get("category", None)
    search = request.args.get("search", "").lower()
    
    query = Destination.query
    
    if category and category != "All":
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(
            (Destination.name.ilike(f"%{search}%")) |
            (Destination.description.ilike(f"%{search}%")) |
            (Destination.category.ilike(f"%{search}%"))
        )
    
    destinations = query.all()
    return jsonify([{
        "id": d.id,
        "name": d.name,
        "state": d.state,
        "description": d.description,
        "image": url_for('static', filename=d.image_url) if d.image_url else url_for('static', filename='uploads/default.jpg'),
        "category": d.category,
        "rating": d.rating,
        "price": d.price,
        "reviews": d.reviews
    } for d in destinations])


# ----------- API: Get Best Selling Destinations ----------
@app.route("/api/best-selling", methods=["GET"])
def get_best_selling():
    destinations = Destination.query.order_by(Destination.reviews.desc()).limit(10).all()
    return jsonify([{
        "id": d.id,
        "name": d.name,
        "state": d.state,
        "desc": d.description,
        "image": url_for('static', filename=d.image_url) if d.image_url else url_for('static', filename='uploads/default.jpg'),
        "category": d.category,
        "rating": d.rating,
        "price": d.price,
        "reviews": d.reviews
    } for d in destinations])


# ----------- API: Get Hotels ----------
@app.route("/api/hotels", methods=["GET"])
def api_get_hotels():
    try:
        # Check cache first
        cache_key = 'hotels_list'
        if cache_key in _api_cache:
            cache_data, cache_time = _api_cache[cache_key]
            if (datetime.now() - cache_time).seconds < _cache_timeout:
                return jsonify(cache_data)
        
        # Limit to 50 hotels for faster loading
        hotels = Hotel.query.limit(50).all()
        result = []
        for h in hotels:
            # Use existing image or default, don't fetch from Unsplash
            image_url = h.main_image if h.main_image else 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80'
            
            result.append({
                "id": h.id,
                "name": h.hotel_name,
                "city": h.city,
                "description": h.short_highlight or f"{h.hotel_name} in {h.area}, {h.city}",
                "image": image_url,
                "rating": h.rating_score or 4.5,
                "price_per_night": h.discounted_price or h.original_price or 0
            })
        
        # Cache the result
        _api_cache[cache_key] = (result, datetime.now())
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in api_get_hotels: {e}")
        return jsonify({"error": str(e)}), 500


# ----------- API: Get Transports ----------
@app.route("/api/transports", methods=["GET"])
def api_get_transports():
    try:
        # Limit to 50 transports for faster loading
        transports = Transport.query.limit(50).all()
        result = []
        for t in transports:
            # Use default image instead of fetching from Unsplash
            image_url = 'https://images.unsplash.com/photo-1544620347-c4fd4a3d5957?auto=format&fit=crop&w=800&q=80'
            
            result.append({
                "id": t.id,
                "name": t.agency_name,
                "type": t.vehicle_type,
                "description": getattr(t, 'description', f"{t.vehicle_type} with {t.seats} seats"),
                "image": image_url,
                "capacity": t.seats,
                "price": t.price_per_km
            })
        return jsonify(result)
    except Exception as e:
        print(f"Error in api_get_transports: {e}")
        return jsonify({"error": str(e)}), 500


# ----------- API: Get Packages as Destinations ----------
@app.route("/api/packages-destinations", methods=["GET"])
def get_packages_as_destinations():
    """API endpoint for packages page - returns multi-day packages only"""
    try:
        # Get filter parameter
        package_type = request.args.get('type', 'packages')  # 'tours' or 'packages'
        
        query = TravelPackage.query.filter_by(status='active')
        
        # Filter based on type
        if package_type == 'tours':
            # Day trips only (1D/0N)
            query = query.filter(
                db.or_(
                    TravelPackage.duration.ilike('%1 Day%0 Night%'),
                    TravelPackage.duration.ilike('%1D/0N%')
                )
            )
        else:
            # Multi-day packages (NOT 1D/0N)
            query = query.filter(
                db.and_(
                    ~TravelPackage.duration.ilike('%1 Day%0 Night%'),
                    ~TravelPackage.duration.ilike('%1D/0N%')
                )
            )
        
        packages = query.all()
        result = []
        for pkg in packages:
            # Default image
            image_url = url_for('static', filename='uploads/default.jpg', _external=True)
            
            # Get package image
            if pkg.images:
                img_path = pkg.images[0].image_url
                # Check if it's an external URL (Unsplash, etc.)
                if img_path.startswith('http://') or img_path.startswith('https://'):
                    image_url = img_path
                else:
                    # Local file
                    if img_path.startswith('/'):
                        img_path = img_path[1:]
                    image_url = url_for('static', filename=img_path, _external=True)
            
            # Get agency name
            agency_name = pkg.agency.username if pkg.agency else "Unknown Agency"
            
            result.append({
                "id": pkg.id,
                "title": pkg.title,  # Changed from "name"
                "name": pkg.title,   # Keep for compatibility
                "location": pkg.location,  # Changed from "state"
                "state": pkg.location,     # Keep for compatibility
                "description": f"{pkg.duration} package with {pkg.hotel or 'accommodation'}, {pkg.meals or 'meals'}, and {pkg.activities or 'activities'}",
                "image": image_url,
                "image_url": image_url,  # Added for compatibility
                "category": "Package",
                "rating": 4.8,
                "price": f"₹{pkg.price_per_person}",
                "price_per_person": pkg.price_per_person,  # Added numeric value
                "reviews": 0,
                "type": "package",
                "agency_name": agency_name,
                "hotel": pkg.hotel,
                "meals": pkg.meals,
                "activities": pkg.activities,
                "complimentary": pkg.complimentary,
                "duration": pkg.duration
            })
        return jsonify(result)
    except Exception as e:
        print(f"Error getting packages as destinations: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        return jsonify({"error": str(e)}), 500


# ----------- ADMIN API ENDPOINTS ----------
@app.route("/api/admin/stats", methods=["GET"])
@login_required
@role_required('admin')
def admin_stats():
    try:
        total_users = User.query.count()
        total_hotels = Hotel.query.count()
        total_transports = Transport.query.count()
        total_bookings = HotelBooking.query.count()
        total_packages = TravelPackage.query.count()
        total_reviews = HotelReview.query.count()
        total_agencies = User.query.filter_by(role='travelagency').count()
        
        # Calculate total revenue from bookings
        bookings = HotelBooking.query.all()
        total_revenue = sum(b.total_price for b in bookings)
        
        return jsonify({
            "total_users": total_users,
            "total_hotels": total_hotels,
            "total_transports": total_transports,
            "total_bookings": total_bookings,
            "total_packages": total_packages,
            "total_reviews": total_reviews,
            "total_agencies": total_agencies,
            "total_revenue": total_revenue
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/users", methods=["GET"])
@login_required
@role_required('admin')
def admin_users():
    try:
        users = User.query.all()
        return jsonify([{
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role
        } for u in users]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/hotels", methods=["GET"])
@login_required
@role_required('admin')
def admin_hotels():
    try:
        hotels = Hotel.query.all()
        return jsonify([{
            "id": h.id,
            "hotel_name": h.hotel_name,
            "city": h.city,
            "area": h.area,
            "rating_score": h.rating_score,
            "original_price": h.original_price,
            "discounted_price": h.discounted_price,
            "owner_id": h.owner_id,
            "owner_username": h.owner.username if h.owner else None
        } for h in hotels]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/transports", methods=["GET"])
@login_required
@role_required('admin')
def admin_transports():
    try:
        transports = Transport.query.all()
        return jsonify([{
            "id": t.id,
            "agency_name": t.agency_name,
            "vehicle_type": t.vehicle_type,
            "seats": t.seats,
            "price_per_km": t.price_per_km,
            "owner_id": t.owner_id,
            "owner_username": t.owner.username if t.owner else None
        } for t in transports]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/agencies", methods=["GET"])
@login_required
@role_required('admin')
def admin_agencies():
    try:
        agencies = User.query.filter_by(role='travelagency').all()
        result = []
        
        for agency in agencies:
            try:
                packages = TravelPackage.query.filter_by(agency_id=agency.id).all()
                package_bookings = PackageBooking.query.join(TravelPackage).filter(
                    TravelPackage.agency_id == agency.id
                ).all()
                
                total_revenue = sum(b.total_price for b in package_bookings)
                
                result.append({
                    "id": agency.id,
                    "username": agency.username,
                    "email": agency.email,
                    "total_packages": len(packages),
                    "total_bookings": len(package_bookings),
                    "total_revenue": total_revenue
                })
            except Exception as e:
                print(f"Error processing agency {agency.id}: {str(e)}")
                result.append({
                    "id": agency.id,
                    "username": agency.username,
                    "email": agency.email,
                    "total_packages": 0,
                    "total_bookings": 0,
                    "total_revenue": 0,
                    "error": str(e)
                })
        
        return jsonify(result), 200
    except Exception as e:
        print(f"Error in admin_agencies endpoint: {str(e)}")
        return jsonify({"error": f"Failed to load agencies: {str(e)}"}), 500


@app.route("/api/admin/bookings", methods=["GET"])
@login_required
@role_required('admin')
def admin_bookings():
    try:
        bookings = HotelBooking.query.all()
        return jsonify([{
            "id": b.id,
            "hotel_id": b.hotel_id,
            "hotel_name": b.hotel.hotel_name if b.hotel else "N/A",
            "user_id": b.user_id,
            "guest_name": b.guest_name,
            "check_in": b.check_in.strftime('%Y-%m-%d') if b.check_in else None,
            "check_out": b.check_out.strftime('%Y-%m-%d') if b.check_out else None,
            "guests": b.guests,
            "rooms": b.rooms,
            "total_price": b.total_price,
            "status": b.status
        } for b in bookings]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/reviews", methods=["GET"])
def admin_reviews():
    try:
        reviews = HotelReview.query.all()
        return jsonify([{
            "id": r.id,
            "hotel_id": r.hotel_id,
            "hotel_name": r.hotel.hotel_name if r.hotel else "N/A",
            "user_id": r.user_id,
            "username": r.user.username if r.user else "N/A",
            "rating": r.rating,
            "title": r.title,
            "comment": r.comment,
            "created_at": r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else None
        } for r in reviews]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/packages", methods=["GET"])
def admin_packages():
    try:
        packages = TravelPackage.query.all()
        return jsonify([{
            "id": p.id,
            "title": p.title,
            "location": p.location,
            "duration": p.duration,
            "price_per_person": p.price_per_person,
            "status": p.status,
            "agency_id": p.agency_id,
            "agency_name": p.agency.username if p.agency else "N/A"
        } for p in packages]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# DELETE endpoints
@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@role_required('admin')
def delete_user_admin(user_id):
    """Delete user and all related data with proper cascade handling"""
    try:
        user = User.query.get_or_404(user_id)
        
        print(f"Starting deletion of user {user_id}: {user.username}")
        
        # Delete related data in order (most dependent first)
        
        # 1. Delete bookings (depend on user)
        try:
            count = HotelBooking.query.filter_by(user_id=user_id).delete()
            print(f"Deleted {count} hotel bookings")
        except Exception as e:
            print(f"Error deleting hotel bookings: {e}")
            
        try:
            count = PackageBooking.query.filter_by(user_id=user_id).delete()
            print(f"Deleted {count} package bookings")
        except Exception as e:
            print(f"Error deleting package bookings: {e}")
            
        try:
            count = TourBooking.query.filter_by(user_id=user_id).delete()
            print(f"Deleted {count} tour bookings")
        except Exception as e:
            print(f"Error deleting tour bookings: {e}")
        
        # 2. Delete reviews
        try:
            count = HotelReview.query.filter_by(user_id=user_id).delete()
            print(f"Deleted {count} hotel reviews")
        except Exception as e:
            print(f"Error deleting hotel reviews: {e}")
            
        try:
            count = UserReview.query.filter_by(user_id=user_id).delete()
            print(f"Deleted {count} user reviews")
        except Exception as e:
            print(f"Error deleting user reviews: {e}")
        
        # 3. Delete itineraries with their day plans and activities
        try:
            itineraries = Itinerary.query.filter_by(user_id=user_id).all()
            print(f"Found {len(itineraries)} itineraries to delete")
            for itinerary in itineraries:
                # Delete activities for each day plan
                for day_plan in itinerary.day_plans:
                    Activity.query.filter_by(day_plan_id=day_plan.id).delete()
                # Delete day plans
                DayPlan.query.filter_by(itinerary_id=itinerary.id).delete()
            # Delete itineraries
            Itinerary.query.filter_by(user_id=user_id).delete()
            print(f"Deleted itineraries and related data")
        except Exception as e:
            print(f"Error deleting itineraries: {e}")
        
        # 4. Delete profile data
        try:
            TravelerProfile.query.filter_by(user_id=user_id).delete()
            print(f"Deleted traveler profile")
        except Exception as e:
            print(f"Error deleting traveler profile: {e}")
            
        try:
            TravelHistory.query.filter_by(user_id=user_id).delete()
            print(f"Deleted travel history")
        except Exception as e:
            print(f"Error deleting travel history: {e}")
            
        try:
            Wishlist.query.filter_by(user_id=user_id).delete()
            print(f"Deleted wishlist")
        except Exception as e:
            print(f"Error deleting wishlist: {e}")
            
        try:
            NotificationPreference.query.filter_by(user_id=user_id).delete()
            print(f"Deleted notification preferences")
        except Exception as e:
            print(f"Error deleting notification preferences: {e}")
        
        # 5. Delete user preferences
        try:
            count = UserPreference.query.filter_by(user_id=user_id).delete()
            print(f"Deleted {count} user preferences")
        except Exception as e:
            print(f"Error deleting user preferences: {e}")
        
        # 6. Delete owned entities (hotels, transports, packages)
        try:
            hotels = Hotel.query.filter_by(owner_id=user_id).all()
            print(f"Found {len(hotels)} hotels to delete")
            for hotel in hotels:
                # Delete hotel-related data first
                HotelImage.query.filter_by(hotel_id=hotel.id).delete()
                HotelAmenity.query.filter_by(hotel_id=hotel.id).delete()
                # Reviews and bookings already deleted above
            Hotel.query.filter_by(owner_id=user_id).delete()
            print(f"Deleted hotels and related data")
        except Exception as e:
            print(f"Error deleting hotels: {e}")
        
        try:
            count = Transport.query.filter_by(owner_id=user_id).delete()
            print(f"Deleted {count} transports")
        except Exception as e:
            print(f"Error deleting transports: {e}")
        
        try:
            packages = TravelPackage.query.filter_by(agency_id=user_id).all()
            print(f"Found {len(packages)} packages to delete")
            for package in packages:
                # Delete package images first
                PackageImage.query.filter_by(package_id=package.id).delete()
                # Bookings already deleted above
            TravelPackage.query.filter_by(agency_id=user_id).delete()
            print(f"Deleted packages and related data")
        except Exception as e:
            print(f"Error deleting packages: {e}")
        
        # 7. Finally delete the user
        print(f"Deleting user {user_id}")
        db.session.delete(user)
        db.session.commit()
        
        print(f"✅ Successfully deleted user {user_id} and all related data")
        return jsonify({"success": True, "message": "User and all related data deleted successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ CRITICAL ERROR in delete_user_admin: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Failed to delete user: {str(e)}"}), 500


@app.route("/api/admin/hotels/<int:hotel_id>", methods=["DELETE"])
@login_required
@role_required('admin')
def delete_hotel_admin(hotel_id):
    try:
        hotel = Hotel.query.get_or_404(hotel_id)
        
        # Delete related data first
        # Delete hotel images
        HotelImage.query.filter_by(hotel_id=hotel_id).delete()
        
        # Delete hotel amenities
        HotelAmenity.query.filter_by(hotel_id=hotel_id).delete()
        
        # Delete hotel reviews
        HotelReview.query.filter_by(hotel_id=hotel_id).delete()
        
        # Delete hotel bookings
        HotelBooking.query.filter_by(hotel_id=hotel_id).delete()
        
        # Finally delete the hotel
        db.session.delete(hotel)
        db.session.commit()
        
        return jsonify({"success": True, "message": "Hotel and all related data deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Failed to delete hotel: {str(e)}"}), 500


@app.route("/api/admin/transports/<int:transport_id>", methods=["DELETE"])
@login_required
@role_required('admin')
def delete_transport_admin(transport_id):
    try:
        transport = Transport.query.get_or_404(transport_id)
        db.session.delete(transport)
        db.session.commit()
        return jsonify({"success": True, "message": "Transport deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Failed to delete transport: {str(e)}"}), 500


@app.route("/api/admin/reviews/<int:review_id>", methods=["DELETE"])
@login_required
@role_required('admin')
def delete_review_admin(review_id):
    try:
        review = HotelReview.query.get_or_404(review_id)
        db.session.delete(review)
        db.session.commit()
        return jsonify({"success": True, "message": "Review deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Failed to delete review: {str(e)}"}), 500


@app.route("/api/admin/packages/<int:package_id>", methods=["DELETE"])
@login_required
@role_required('admin')
def delete_package_admin(package_id):
    try:
        package = TravelPackage.query.get_or_404(package_id)
        
        # Delete related data first
        # Delete package images
        PackageImage.query.filter_by(package_id=package_id).delete()
        
        # Delete package bookings
        PackageBooking.query.filter_by(package_id=package_id).delete()
        
        # Finally delete the package
        db.session.delete(package)
        db.session.commit()
        
        return jsonify({"success": True, "message": "Package and all related data deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Failed to delete package: {str(e)}"}), 500


@app.route("/api/admin/contacts", methods=["GET"])
def admin_contacts():
    try:
        contacts = ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(50).all()
        return jsonify([{
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "subject": c.subject,
            "message": c.message[:100],
            "date": c.created_at.strftime("%Y-%m-%d %H:%M")
        } for c in contacts]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/delete-user/<int:user_id>", methods=["DELETE"])
def admin_delete_user(user_id):
    try:
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            return jsonify({"message": "User deleted"}), 200
        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/delete-hotel/<int:hotel_id>", methods=["DELETE"])
def admin_delete_hotel(hotel_id):
    try:
        hotel = Hotel.query.get(hotel_id)
        if hotel:
            db.session.delete(hotel)
            db.session.commit()
            return jsonify({"message": "Hotel deleted"}), 200
        return jsonify({"error": "Hotel not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/delete-transport/<int:transport_id>", methods=["DELETE"])
def admin_delete_transport(transport_id):
    try:
        transport = Transport.query.get(transport_id)
        if transport:
            db.session.delete(transport)
            db.session.commit()
            return jsonify({"message": "Transport deleted"}), 200
        return jsonify({"error": "Transport not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/packages/<int:package_id>", methods=["DELETE"])
def delete_package(package_id):
    try:
        package = TravelPackage.query.get(package_id)
        if package:
            # Delete associated images first
            for img in package.images:
                db.session.delete(img)
            db.session.delete(package)
            db.session.commit()
            return jsonify({"message": "Package deleted"}), 200
        return jsonify({"error": "Package not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/destinations", methods=["GET"])
def admin_destinations():
    try:
        destinations = Destination.query.all()
        return jsonify([{
            "id": d.id,
            "name": d.name,
            "state": d.state,
            "description": d.description,
            "image": url_for('static', filename=d.image_url) if d.image_url else url_for('static', filename='uploads/default.jpg'),
            "category": d.category,
            "rating": d.rating,
            "price": d.price,
            "reviews": d.reviews
        } for d in destinations]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/add-destination", methods=["POST"])
def admin_add_destination():
    try:
        data = request.get_json()
        
        name = data.get('name', '').strip()
        state = data.get('state', 'Maharashtra').strip()
        description = data.get('description', '').strip()
        image_url = data.get('image', '').strip()
        category = data.get('category', '').strip()
        rating = float(data.get('rating', 4.5))
        price = data.get('price', '').strip()
        reviews = int(data.get('reviews', 0))
        
        if not name or not category:
            return jsonify({"error": "Name and category are required"}), 400
        
        existing = Destination.query.filter_by(name=name).first()
        if existing:
            return jsonify({"error": "Destination already exists"}), 409
        
        dest = Destination(
            name=name,
            state=state,
            description=description,
            image_url=image_url,
            category=category,
            rating=rating,
            price=price,
            reviews=reviews
        )
        db.session.add(dest)
        db.session.commit()
        
        return jsonify({
            "message": "Destination added successfully",
            "id": dest.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/update-destination/<int:dest_id>", methods=["PUT"])
def admin_update_destination(dest_id):
    try:
        dest = Destination.query.get(dest_id)
        if not dest:
            return jsonify({"error": "Destination not found"}), 404
        
        data = request.get_json()
        
        dest.name = data.get('name', dest.name)
        dest.state = data.get('state', dest.state)
        dest.description = data.get('description', dest.description)
        dest.image_url = data.get('image', dest.image_url)
        dest.category = data.get('category', dest.category)
        dest.rating = float(data.get('rating', dest.rating))
        dest.price = data.get('price', dest.price)
        dest.reviews = int(data.get('reviews', dest.reviews))
        
        db.session.commit()
        return jsonify({"message": "Destination updated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/delete-destination/<int:dest_id>", methods=["DELETE"])
def admin_delete_destination(dest_id):
    try:
        dest = Destination.query.get(dest_id)
        if dest:
            db.session.delete(dest)
            db.session.commit()
            return jsonify({"message": "Destination deleted"}), 200
        return jsonify({"error": "Destination not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/fix-destinations-schema', methods=['POST'])
def fix_destinations_schema():
    """Attempt to add missing columns to the destinations table (safe for local dev).
    This uses IF NOT EXISTS where supported by the DB.
    """
    try:
        # Add 'state' column if missing
        db.session.execute(text("ALTER TABLE destinations ADD COLUMN IF NOT EXISTS state VARCHAR(100) DEFAULT 'Maharashtra';"))
        db.session.commit()
        return jsonify({"message": "Destinations schema verified/updated."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ----------- Initialize Destinations Database ----------
@app.route("/api/init-destinations", methods=["POST"])
def init_destinations():    
    try:
        for dest_data in destinations_data:
            existing = Destination.query.filter_by(name=dest_data["name"]).first()
            if not existing:
                dest = Destination(
                    name=dest_data["name"],
                    state=dest_data["state"],
                    description=dest_data["description"],
                    image_url=dest_data["image"],
                    category=dest_data["category"],
                    rating=dest_data["rating"],
                    price=dest_data["price"],
                    reviews=dest_data["reviews"]
                )
                db.session.add(dest)
        
        db.session.commit()
        return jsonify({"message": f"Successfully initialized {len(destinations_data)} destinations"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ----------- HOTEL IMPORT API ENDPOINTS ----------
# Note: External hotel search functionality moved to external APIs section

@app.route('/api/hotels/import', methods=['POST'])
@login_required
@role_required('admin', 'hotel', 'travelagency')
def import_hotel():
    """Import a specific hotel into the database"""
    data = request.get_json()
    hotel_data = data.get('hotel_data')
    
    if not hotel_data:
        return jsonify({"error": "Hotel data is required"}), 400
    
    try:
        hotel = hotel_import_service.import_hotel_to_database(hotel_data, session['user_id'])
        if hotel:
            return jsonify({
                "message": "Hotel imported successfully",
                "hotel_id": hotel.id,
                "hotel_name": hotel.hotel_name
            }), 200
        else:
            return jsonify({"error": "Failed to import hotel"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/hotels/import-sample', methods=['POST'])
@login_required
@role_required('admin', 'hotel', 'travelagency')
def import_sample_hotels():
    """Import sample hotels for demonstration"""
    try:
        count = hotel_import_service.import_sample_hotels()
        return jsonify({
            "message": f"Successfully imported {count} sample hotels",
            "count": count
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ==================== ADDITIONAL ADMIN API ENDPOINTS ====================

# Tours Management
@app.route("/api/admin/tours/<int:tour_id>", methods=["DELETE"])
@login_required
@role_required('admin')
def delete_tour_admin(tour_id):
    try:
        tour = Tour.query.get(tour_id)
        if tour:
            db.session.delete(tour)
            db.session.commit()
            return jsonify({"success": True, "message": "Tour deleted successfully"}), 200
        return jsonify({"success": False, "message": "Tour not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/tours/<int:tour_id>/status", methods=["PUT"])
@login_required
@role_required('admin')
def toggle_tour_status_admin(tour_id):
    try:
        tour = Tour.query.get(tour_id)
        if tour:
            data = request.get_json()
            tour.active = data.get('active', not tour.active)
            db.session.commit()
            return jsonify({"success": True, "message": "Tour status updated successfully"}), 200
        return jsonify({"success": False, "message": "Tour not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

# Hidden Gems Management
@app.route("/api/admin/hidden-gems/<int:gem_id>", methods=["DELETE"])
@login_required
@role_required('admin')
def delete_hidden_gem_admin(gem_id):
    try:
        gem = HiddenGem.query.get(gem_id)
        if gem:
            db.session.delete(gem)
            db.session.commit()
            return jsonify({"success": True, "message": "Hidden gem deleted successfully"}), 200
        return jsonify({"success": False, "message": "Hidden gem not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

# Itineraries Management
@app.route("/api/admin/itineraries/<int:itinerary_id>", methods=["DELETE"])
@login_required
@role_required('admin')
def delete_itinerary_admin(itinerary_id):
    try:
        itinerary = Itinerary.query.get(itinerary_id)
        if itinerary:
            # 1. Delete ItineraryHiddenGem references
            ItineraryHiddenGem.query.filter_by(itinerary_id=itinerary_id).delete()

            # 2. Delete activities inside each day plan
            for day_plan in itinerary.day_plans:
                Activity.query.filter_by(day_plan_id=day_plan.id).delete()

            # 3. Delete day plans
            DayPlan.query.filter_by(itinerary_id=itinerary_id).delete()

            # 4. Delete the itinerary itself
            db.session.delete(itinerary)
            db.session.commit()
            return jsonify({"success": True, "message": "Itinerary deleted successfully"}), 200
        return jsonify({"success": False, "message": "Itinerary not found"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

# Messages Management
@app.route("/api/admin/messages/<int:message_id>", methods=["DELETE"])
@login_required
@role_required('admin')
def delete_message_admin(message_id):
    try:
        message = ContactMessage.query.get(message_id)
        if message:
            db.session.delete(message)
            db.session.commit()
            return jsonify({"success": True, "message": "Message deleted successfully"}), 200
        return jsonify({"success": False, "message": f"Message {message_id} not found"}), 404
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] delete_message_admin({message_id}): {e}")
        return jsonify({"success": False, "message": str(e)}), 500



@app.route('/admin/hotel-import', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'hotel', 'travelagency')
def admin_hotel_import():
    """Admin interface for hotel import management"""
    if request.method == 'POST':
        location = request.form.get('location')
        if location:
            try:
                hotels = hotel_import_service.search_booking_com_hotels(location)
                return render_template('admin_hotel_import.html', hotels=hotels, location=location)
            except Exception as e:
                flash(f'Error searching hotels: {str(e)}', 'danger')
        else:
            flash('Please enter a location to search', 'warning')
    
    return render_template('admin_hotel_import.html', hotels=[])





# =========================================================
# HIDDEN GEMS SYSTEM
# =========================================================

def _needs_real_image(url):
    """Returns True if the stored URL is missing or a known generic/fallback image."""
    if not url:
        return True
    if "source.unsplash.com" in url:
        return True
    # The generic mountain fallback photo
    if "photo-1506905925346-21bda4d32df4" in url:
        return True
    return False


def fetch_and_save_gem_image(gem):
    """Fetch a real place image for a gem using the same source as tours, and persist it."""
    url = fetch_place_image(gem.location, gem.name)
    gem.image_url = url
    gem.image_alt_text = gem.name
    gem.image_source = "google_places"
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return url


def search_existing_gems(destination, category="", broad_search=False):
    """Search existing gems in database by destination and category"""
    try:
        query = HiddenGem.query.filter_by(is_active=True)

        if destination:
            query = query.filter(
                db.or_(
                    HiddenGem.location.ilike(f"%{destination}%"),
                    HiddenGem.name.ilike(f"%{destination}%")
                )
            )

        if category and not broad_search:
            query = query.filter(HiddenGem.category == category)

        gems = query.order_by(HiddenGem.created_at.desc()).limit(10).all()

        result = []
        for gem in gems:
            if _needs_real_image(gem.image_url):
                fetch_and_save_gem_image(gem)
            result.append(gem.to_dict())

        return result

    except Exception as e:
        print(f"Error searching existing gems: {str(e)}")
        return []

@app.route("/travel-search")
def travel_search():
    """Travel search page for hotels, trains, flights, buses"""
    return render_template("travel_search.html")

@app.route("/hidden-gems")
def hidden_gems():
    """Main hidden gems page with search and categories"""
    # Load initial gems to display on page load
    try:
        gems = HiddenGem.query.filter_by(is_active=True).limit(12).all()
        gems_data = [gem.to_dict() for gem in gems]
    except Exception as e:
        print(f"Error loading initial gems: {e}")
        gems_data = []
    
    return render_template("hidden_gems.html", initial_gems=gems_data)

@app.route("/api/hidden-gems/search", methods=["POST"])
def search_hidden_gems():
    """Search hidden gems using Gemini API based on destination"""
    try:
        data = request.get_json()
        destination = data.get("destination", "").strip()
        category = data.get("category", "").strip()
        
        if not destination:
            return jsonify({"success": False, "message": "Destination is required"})
        
        # Try to search existing database first
        existing_gems = search_existing_gems(destination, category)
        if existing_gems:
            return jsonify({
                "success": True,
                "gems": existing_gems,
                "message": f"Found {len(existing_gems)} hidden gems around {destination} (from database)"
            })
        
        # If no existing gems found, try Gemini API
        try:
            # Configure Gemini API
            genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
            model = genai.GenerativeModel("gemini-2.0-flash")
            
            # Create prompt based on category
            category_filter = ""
            if category:
                category_map = {
                    "Nature": "hidden waterfalls, secret beaches, forest trails, hills",
                    "Cultural": "local festivals, traditional villages, heritage spots",
                    "Food Spots": "street food gems, local dhabas, authentic restaurants",
                    "Unique Experiences": "sunrise points, stargazing spots, boat rides"
                }
                category_filter = f"Focus on {category_map.get(category, category)}. "
            
            prompt = f"""
            Find 5-7 hidden/offbeat tourist places in and around {destination}, India. {category_filter}
            
            For each place, provide:
            1. Name of the place
            2. Short description (1-2 sentences)
            3. Exact location (area/city)
            4. Best time to visit
            5. Nearby transport options
            6. Category (Nature/Cultural/Food Spots/Unique Experiences)
            7. Subcategory (e.g., Hidden Waterfalls, Local Festival, Street Food, Sunrise Point)
            
            Format as JSON array like:
            [
                {{
                    "name": "Place Name",
                    "description": "Description",
                    "location": "Exact Location",
                    "best_time_to_visit": "Best time",
                    "nearby_transport": "Transport details",
                    "category": "Nature",
                    "subcategory": "Hidden Waterfalls"
                }}
            ]
            """
            
            # Get response from Gemini
            response = model.generate_content(prompt)
            response_text = response.text
            
            # Try to extract JSON from response
            import json
            import re
            
            # Look for JSON array in the response
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                gems_data = json.loads(json_str)
            else:
                # Fallback: create structured data manually
                gems_data = []
            
            # Save to database and return
            saved_gems = []
            for gem_data in gems_data:
                # Check if gem already exists
                existing_gem = HiddenGem.query.filter_by(
                    name=gem_data.get("name"),
                    location=gem_data.get("location")
                ).first()
                
                if not existing_gem:
                    # Get high-quality image with Google/Unsplash
                    image_data = get_unsplash_image_api(
                        gem_data.get("name", ""),
                        gem_data.get("location", ""),
                        gem_data.get("category", "")
                    )

                    new_gem = HiddenGem(
                        name=gem_data.get("name"),
                        description=gem_data.get("description"),
                        location=gem_data.get("location"),
                        category=gem_data.get("category", "Unique Experiences"),
                        subcategory=gem_data.get("subcategory", "Hidden Gem"),
                        best_time_to_visit=gem_data.get("best_time_to_visit"),
                        nearby_transport=gem_data.get("nearby_transport"),
                        image_url=image_data["url"],
                        image_alt_text=image_data["alt_text"],
                        image_source="google_places",
                        image_hash=f"{gem_data.get('name', '')}_{abs(hash(gem_data.get('name', ''))) % 1000}",
                        photographer=image_data["photographer"],
                        photographer_url=image_data["photographer_url"],
                        unsplash_url=image_data["unsplash_url"]
                    )
                    db.session.add(new_gem)
                    db.session.commit()
                    saved_gems.append(new_gem.to_dict())
                else:
                    if _needs_real_image(existing_gem.image_url):
                        fetch_and_save_gem_image(existing_gem)
                    saved_gems.append(existing_gem.to_dict())
            
            return jsonify({
                "success": True,
                "gems": saved_gems,
                "message": f"Found {len(saved_gems)} hidden gems around {destination}"
            })
            
        except Exception as api_error:
            # Handle API quota exceeded or other API errors
            print(f"Gemini API error: {str(api_error)}")
            
            # Fallback to database search with broader criteria
            fallback_gems = search_existing_gems(destination, "", True)  # Search all categories
            if fallback_gems:
                return jsonify({
                    "success": True,
                    "gems": fallback_gems,
                    "message": f"Found {len(fallback_gems)} hidden gems around {destination} (from database - API unavailable)"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": "Unable to search hidden gems right now. Please try again later or browse existing gems."
                })
        
    except Exception as e:
        print(f"Error searching hidden gems: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error searching hidden gems: {str(e)}"
        })

@app.route("/api/hidden-gems/get", methods=["GET"])
def get_hidden_gems():
    """Get all hidden gems with optional filtering"""
    try:
        category = request.args.get("category", "").strip()
        location = request.args.get("location", "").strip()

        query = HiddenGem.query.filter_by(is_active=True)

        if category:
            query = query.filter(HiddenGem.category == category)
        if location:
            query = query.filter(HiddenGem.location.ilike(f"%{location}%"))

        gems = query.all()

        gems_list = []
        for gem in gems:
            if _needs_real_image(gem.image_url):
                fetch_and_save_gem_image(gem)
            gems_list.append(gem.to_dict())

        return jsonify({
            "success": True,
            "gems": gems_list
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error getting hidden gems: {str(e)}"
        })

@app.route("/api/hidden-gems/<int:gem_id>/rate", methods=["POST"])
@login_required
def rate_hidden_gem(gem_id):
    """Rate a hidden gem"""
    try:
        data = request.get_json()
        rating = float(data.get("rating", 0))
        review = data.get("review", "").strip()
        
        if rating < 1 or rating > 5:
            return jsonify({"success": False, "message": "Rating must be between 1 and 5"})
        
        user_id = session.get("user_id")
        gem = HiddenGem.query.get_or_404(gem_id)
        
        # Check if user already rated this gem
        existing_rating = HiddenGemRating.query.filter_by(
            gem_id=gem_id,
            user_id=user_id
        ).first()
        
        if existing_rating:
            existing_rating.rating = rating
            existing_rating.review = review
        else:
            new_rating = HiddenGemRating(
                gem_id=gem_id,
                user_id=user_id,
                rating=rating,
                review=review
            )
            db.session.add(new_rating)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Rating submitted successfully",
            "average_rating": gem.average_rating(),
            "total_ratings": len(gem.ratings)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error rating hidden gem: {str(e)}"
        })

@app.route("/api/hidden-gems/<int:gem_id>/add-itinerary", methods=["POST"])
@login_required
def add_gem_to_itinerary(gem_id):
    """Add hidden gem to user's itinerary"""
    try:
        data = request.get_json()
        itinerary_id = data.get("itinerary_id")
        day_number = data.get("day_number", 1)
        
        user_id = session.get("user_id")
        gem = HiddenGem.query.get_or_404(gem_id)
        
        # If no itinerary_id provided, create a new itinerary
        if not itinerary_id:
            # Create a new itinerary for this user
            new_itinerary = Itinerary(
                city=gem.location,
                user_id=user_id,
                destination_id=1,  # Default destination
                days=1
            )
            db.session.add(new_itinerary)
            db.session.commit()
            itinerary_id = new_itinerary.id
        
        # Check if itinerary belongs to user
        itinerary = Itinerary.query.filter_by(id=itinerary_id, user_id=user_id).first()
        if not itinerary:
            return jsonify({"success": False, "message": "Invalid itinerary"})
        
        # Add gem to itinerary
        existing_item = ItineraryHiddenGem.query.filter_by(
            itinerary_id=itinerary_id,
            gem_id=gem_id
        ).first()
        
        if existing_item:
            return jsonify({"success": False, "message": "Gem already in itinerary"})
        
        itinerary_gem = ItineraryHiddenGem(
            itinerary_id=itinerary_id,
            gem_id=gem_id,
            day_number=day_number
        )
        db.session.add(itinerary_gem)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"{gem.name} added to your itinerary!"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error adding to itinerary: {str(e)}"
        })

@app.route("/api/hidden-gems/refresh-images", methods=["POST"])
def refresh_gem_images():
    """Refresh images for existing hidden gems"""
    try:
        gems = HiddenGem.query.all()
        updated_count = 0
        
        for gem in gems:
            # Get high-quality Unsplash image for this specific place
            new_image_url = get_unsplash_image(gem.name, gem.location, gem.category)
            
            # Update if different
            if gem.image_url != new_image_url:
                gem.image_url = new_image_url
                updated_count += 1
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Updated images for {updated_count} hidden gems"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error refreshing images: {str(e)}"
        })

@app.route("/api/hidden-gems/recommendations", methods=["GET"])
@login_required
def get_gem_recommendations():
    """Get personalized hidden gem recommendations based on user preferences"""
    try:
        user_id = session.get("user_id")
        
        # Get user preferences (simplified - in real app, this would be more sophisticated)
        user_preferences = UserPreference.query.filter_by(user_id=user_id).all()
        preference_categories = [pref.preference_value for pref in user_preferences 
                               if pref.preference_type == "interest"]
        
        # If no preferences, return popular gems
        if not preference_categories:
            popular_gems = HiddenGem.query.filter_by(is_active=True).limit(6).all()
            return jsonify({
                "success": True,
                "gems": [gem.to_dict() for gem in popular_gems],
                "message": "Popular hidden gems"
            })
        
        # Map preferences to gem categories
        category_mapping = {
            "nature": "Nature",
            "adventure": "Unique Experiences", 
            "food": "Food Spots",
            "culture": "Cultural",
            "photography": "Nature"
        }
        
        recommended_categories = []
        for pref in preference_categories:
            pref_lower = pref.lower()
            for key, value in category_mapping.items():
                if key in pref_lower:
                    recommended_categories.append(value)
        
        # Get gems from recommended categories
        if recommended_categories:
            gems = HiddenGem.query.filter(
                HiddenGem.category.in_(recommended_categories),
                HiddenGem.is_active == True
            ).limit(8).all()
        else:
            gems = HiddenGem.query.filter_by(is_active=True).limit(6).all()
        
        return jsonify({
            "success": True,
            "gems": [gem.to_dict() for gem in gems],
            "message": "Recommended based on your interests"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error getting recommendations: {str(e)}"
        })


# ===================== MAIN =====================
if __name__ == "__main__":
    if app.config.get("AUTO_CREATE_TABLES", False):
        with app.app_context():
            db.create_all()  # Create tables if they do not exist
    app.run(
        debug=app.config.get("DEBUG", False),
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
    )

