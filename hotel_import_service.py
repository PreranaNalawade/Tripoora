"""
Hotel Import Service for External Websites
Supports importing hotels from booking.com, expedia.com, and other travel sites
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urljoin, urlparse
from models import db, Hotel, HotelImage, HotelAmenity, User
from sqlalchemy.exc import IntegrityError
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HotelImportService:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def search_booking_com_hotels(self, location, check_in=None, check_out=None, guests=2):
        """
        Search for hotels on booking.com
        Note: This is a simplified example - real implementation would need to handle anti-bot measures
        """
        try:
            # Build search URL
            base_url = "https://www.booking.com/searchresults.html"
            params = {
                'ss': location,
                'checkin': check_in or '2024-12-15',
                'checkout': check_out or '2024-12-16',
                'group_adults': guests,
                'no_rooms': 1,
                'from_sf': 1
            }
            
            response = self.session.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            hotels = []
            
            # Parse hotel listings (simplified - real selectors would need updates)
            hotel_cards = soup.find_all('div', {'data-testid': 'property-card'})
            
            for card in hotel_cards[:10]:  # Limit to 10 hotels for demo
                try:
                    hotel_data = self._parse_booking_com_hotel(card)
                    if hotel_data:
                        hotels.append(hotel_data)
                except Exception as e:
                    logger.error(f"Error parsing hotel card: {e}")
                    continue
                    
            return hotels
            
        except requests.RequestException as e:
            logger.error(f"Error searching booking.com: {e}")
            return []
    
    def _parse_booking_com_hotel(self, card):
        """Parse individual hotel card from booking.com"""
        try:
            # Extract hotel name
            name_elem = card.find('div', {'data-testid': 'title'})
            name = name_elem.get_text(strip=True) if name_elem else "Unknown Hotel"
            
            # Extract price
            price_elem = card.find('span', {'data-testid': 'price-and-discounted-price'})
            price_text = price_elem.get_text(strip=True) if price_elem else ""
            price = self._extract_price(price_text)
            
            # Extract rating
            rating_elem = card.find('div', {'data-testid': 'review-score'})
            rating = self._extract_rating(rating_elem) if rating_elem else 0.0
            
            # Extract location/area
            location_elem = card.find('span', {'data-testid': 'address'})
            area = location_elem.get_text(strip=True) if location_elem else ""
            
            # Extract image
            img_elem = card.find('img', {'data-testid': 'image'})
            image_url = img_elem.get('src') if img_elem else ""
            
            # Extract description/highlights
            desc_elem = card.find('div', {'data-testid': 'description'})
            description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            return {
                'name': name,
                'area': area,
                'city': self._extract_city(area),
                'price': price,
                'rating': rating,
                'image_url': image_url,
                'description': description,
                'source': 'booking.com'
            }
            
        except Exception as e:
            logger.error(f"Error parsing hotel data: {e}")
            return None
    
    def _extract_price(self, price_text):
        """Extract numeric price from price text"""
        if not price_text:
            return 0.0
        
        # Remove currency symbols and convert to number
        price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
        if price_match:
            try:
                return float(price_match.group())
            except ValueError:
                return 0.0
        return 0.0
    
    def _extract_rating(self, rating_elem):
        """Extract numeric rating from rating element"""
        if not rating_elem:
            return 0.0
        
        rating_text = rating_elem.get_text(strip=True)
        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
        if rating_match:
            try:
                return float(rating_match.group())
            except ValueError:
                return 0.0
        return 0.0
    
    def _extract_city(self, area_text):
        """Extract city name from area text"""
        if not area_text:
            return "Unknown"
        
        # Simple extraction - could be enhanced with regex
        parts = area_text.split(',')
        if len(parts) > 1:
            return parts[-1].strip()
        return parts[0].strip()
    
    def import_hotel_to_database(self, hotel_data, owner_id=None):
        """Import hotel data into database"""
        try:
            # Check if hotel already exists (deduplication)
            existing_hotel = Hotel.query.filter_by(hotel_name=hotel_data['name']).first()
            if existing_hotel:
                logger.info(f"Hotel '{hotel_data['name']}' already exists")
                return existing_hotel
            
            # Create new hotel
            hotel = Hotel(
                hotel_name=hotel_data['name'],
                area=hotel_data.get('area', ''),
                city=hotel_data.get('city', ''),
                discounted_price=hotel_data.get('price', 0.0),
                rating_score=hotel_data.get('rating', 0.0),
                full_description=hotel_data.get('description', ''),
                main_image=hotel_data.get('image_url', ''),
                owner_id=owner_id or self._get_default_owner_id(),
                price_per='night',
                free_cancellation=True,  # Default values
                zero_payment_available=False
            )
            
            db.session.add(hotel)
            db.session.commit()
            
            # Add hotel image if available
            if hotel_data.get('image_url'):
                self._add_hotel_image(hotel.id, hotel_data['image_url'])
            
            # Add default amenities
            self._add_default_amenities(hotel.id)
            
            logger.info(f"Successfully imported hotel: {hotel.hotel_name}")
            return hotel
            
        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Error importing hotel (integrity): {e}")
            return None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error importing hotel: {e}")
            return None
    
    def _add_hotel_image(self, hotel_id, image_url, caption=""):
        """Add hotel image to database"""
        try:
            image = HotelImage(
                hotel_id=hotel_id,
                image_url=image_url,
                caption=caption,
                is_primary=True
            )
            db.session.add(image)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error adding hotel image: {e}")
    
    def _add_default_amenities(self, hotel_id):
        """Add default amenities to imported hotel"""
        default_amenities = [
            {'name': 'WiFi', 'icon': 'wifi', 'category': 'General'},
            {'name': 'Air Conditioning', 'icon': 'ac', 'category': 'Room'},
            {'name': 'Parking', 'icon': 'parking', 'category': 'General'},
            {'name': '24/7 Front Desk', 'icon': 'reception', 'category': 'Services'},
            {'name': 'Housekeeping', 'icon': 'cleaning', 'category': 'Services'}
        ]
        
        for amenity_data in default_amenities:
            try:
                amenity = HotelAmenity(
                    hotel_id=hotel_id,
                    name=amenity_data['name'],
                    icon=amenity_data['icon'],
                    category=amenity_data['category']
                )
                db.session.add(amenity)
            except Exception as e:
                logger.error(f"Error adding amenity {amenity_data['name']}: {e}")
        
        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Error committing amenities: {e}")
    
    def _get_default_owner_id(self):
        """Get default owner ID for imported hotels (admin user)"""
        try:
            # Try to find an admin user
            admin_user = User.query.filter_by(role='admin').first()
            if admin_user:
                return admin_user.id
            
            # If no admin, create one
            admin_user = User(
                username='admin_import',
                email='admin@tripoora.com',
                role='admin'
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            return admin_user.id
            
        except Exception as e:
            logger.error(f"Error getting default owner: {e}")
            return 1  # Fallback to user ID 1
    
    def import_sample_hotels(self):
        """Import sample hotels for demonstration"""
        sample_hotels = [
            {
                'name': 'Taj Mahal Palace Mumbai',
                'area': 'Colaba, Mumbai',
                'city': 'Mumbai',
                'price': 15000.0,
                'rating': 4.8,
                'image_url': '/static/uploads/MUMBAI.jpg',
                'description': 'Luxury heritage hotel with stunning views of the Gateway of India',
                'source': 'sample'
            },
            {
                'name': 'The Oberoi Mumbai',
                'area': 'Nariman Point, Mumbai',
                'city': 'Mumbai',
                'price': 12000.0,
                'rating': 4.7,
                'image_url': '/static/uploads/mumbai.avif',
                'description': 'Five-star luxury hotel with panoramic sea views',
                'source': 'sample'
            },
            {
                'name': 'ITC Grand Central Mumbai',
                'area': 'Parel, Mumbai',
                'city': 'Mumbai',
                'price': 10000.0,
                'rating': 4.5,
                'image_url': '/static/uploads/mahabaleshvar.jpg',
                'description': 'Modern luxury hotel in heart of Mumbai business district',
                'source': 'sample'
            },
            {
                'name': 'The Leela Palace Mumbai',
                'area': 'Bandra, Mumbai',
                'city': 'Mumbai',
                'price': 18000.0,
                'rating': 4.9,
                'image_url': '/static/uploads/mahadev.jpg',
                'description': 'Palatial hotel with world-class amenities and service',
                'source': 'sample'
            },
            {
                'name': 'Taj Lands End Mumbai',
                'area': 'Bandra Kurla, Mumbai',
                'city': 'Mumbai',
                'price': 8000.0,
                'rating': 4.3,
                'image_url': '/static/uploads/vittala temple stone chariot, hampi.jpg',
                'description': 'Contemporary hotel with stunning Arabian Sea views',
                'source': 'sample'
            },
            {
                'name': 'ITC Grand Central Mumbai',
                'area': 'Parel, Mumbai',
                'city': 'Mumbai',
                'price': 8000.0,
                'rating': 4.5,
                'image_url': '/static/uploads/itc-grand-central.jpg',
                'description': 'Premium business hotel with world-class amenities',
                'source': 'sample'
            }
        ]
        
        imported_count = 0
        for hotel_data in sample_hotels:
            hotel = self.import_hotel_to_database(hotel_data)
            if hotel:
                imported_count += 1
        
        logger.info(f"Imported {imported_count} sample hotels")
        return imported_count

# Global instance
hotel_import_service = HotelImportService()
