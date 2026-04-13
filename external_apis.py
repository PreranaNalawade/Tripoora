"""
External API Integration for Hotels and Transport
"""

import requests
import os
import json
from datetime import datetime, timedelta

class ExternalAPIs:
    """Integration with Booking.com, Indian Railways, and other travel services"""
    
    def __init__(self):
        self.booking_api_key = os.getenv('BOOKING_API_KEY', '')
        self.railway_api_key = os.getenv('RAILWAY_API_KEY', '')
    
    # ==================== HOTELS ===================
    
    def search_hotels_booking(self, location, check_in, check_out, guests=1, rooms=1):
        """Search hotels using Booking.com API"""
        try:
            # Booking.com API endpoint
            url = "https://distribution-xml.booking.com/json/bookings.getHotelAvailability"
            
            params = {
                'city': location,
                'checkin': check_in,
                'checkout': check_out,
                'guests': guests,
                'rooms': rooms,
                'order_by': 'review_score',
                'language': 'en',
                'currency': 'INR'
            }
            
            headers = {
                'Authorization': f'Bearer {self.booking_api_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self.format_booking_hotels(data)
            else:
                return self.get_mock_hotels(location)
                
        except Exception as e:
            print(f"Booking.com API error: {str(e)}")
            return self.get_mock_hotels(location)
    
    def get_mock_hotels(self, location):
        """Mock hotel data when API fails"""
        return [
            {
                'name': f'Taj Hotel {location}',
                'rating': 4.5,
                'price': 8000,
                'location': location,
                'amenities': ['WiFi', 'Pool', 'Restaurant', 'Spa'],
                'image': f'https://source.unsplash.com/400x300/?hotel-{location.lower()}',
                'booking_url': f'https://www.booking.com/searchresults.html?ss={location}',
                'source': 'mock'
            },
            {
                'name': f'Oberoi {location}',
                'rating': 4.7,
                'price': 12000,
                'location': location,
                'amenities': ['WiFi', 'Gym', 'Bar', 'Business Center'],
                'image': f'https://source.unsplash.com/400x300/?luxury-hotel-{location.lower()}',
                'booking_url': f'https://www.booking.com/searchresults.html?ss={location}',
                'source': 'mock'
            }
        ]
    
    def format_booking_hotels(self, data):
        """Format Booking.com response"""
        hotels = []
        
        for hotel in data.get('hotels', []):
            hotels.append({
                'name': hotel.get('name', ''),
                'rating': hotel.get('review_score', 0),
                'price': hotel.get('price', 0),
                'location': hotel.get('city', ''),
                'amenities': hotel.get('facilities', []),
                'image': hotel.get('photo_url', ''),
                'booking_url': hotel.get('deep_link', ''),
                'source': 'booking.com'
            })
        
        return hotels
    
    # ==================== TRANSPORT ===================
    
    def search_trains_indian_railway(self, from_station, to_station, travel_date, class_type='1A'):
        """Search trains using Indian Railway API"""
        try:
            # Indian Railway API endpoint (using IRCTC or third-party)
            url = "https://api.railwayapi.com/v2/trains-between-stations"
            
            params = {
                'from_station_code': from_station,
                'to_station_code': to_station,
                'date_of_journey': travel_date,
                'class_type': class_type,
                'quota': 'GN'
            }
            
            headers = {
                'Authorization': f'Bearer {self.railway_api_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self.format_railway_trains(data)
            else:
                return self.get_mock_trains(from_station, to_station)
                
        except Exception as e:
            print(f"Indian Railway API error: {str(e)}")
            return self.get_mock_trains(from_station, to_station)
    
    def get_mock_trains(self, from_station, to_station):
        """Mock train data when API fails"""
        return [
            {
                'train_number': '12123',
                'train_name': 'Deccan Queen',
                'from_station': from_station,
                'to_station': to_station,
                'departure_time': '06:30',
                'arrival_time': '10:45',
                'duration': '4h 15m',
                'classes': ['1A', '2A', '3A', 'SL'],
                'available_seats': {'1A': 12, '2A': 28, '3A': 45, 'SL': 120},
                'price': {'1A': 1500, '2A': 900, '3A': 600, 'SL': 250},
                'running_days': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                'booking_url': 'https://www.yatra.com/trains',
                'source': 'mock'
            },
            {
                'train_number': '11007',
                'train_name': 'Deccan Express',
                'from_station': from_station,
                'to_station': to_station,
                'departure_time': '14:15',
                'arrival_time': '18:30',
                'duration': '4h 15m',
                'classes': ['1A', '2A', '3A', 'SL'],
                'available_seats': {'1A': 8, '2A': 15, '3A': 32, 'SL': 89},
                'price': {'1A': 1450, '2A': 850, '3A': 580, 'SL': 240},
                'running_days': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                'booking_url': 'https://www.makemytrip.com/railways',
                'source': 'mock'
            }
        ]
    
    def format_railway_trains(self, data):
        """Format Indian Railway response"""
        trains = []
        
        for train in data.get('trains', []):
            trains.append({
                'train_number': train.get('train_number', ''),
                'train_name': train.get('train_name', ''),
                'from_station': train.get('from_station_name', ''),
                'to_station': train.get('to_station_name', ''),
                'departure_time': train.get('departure_time', ''),
                'arrival_time': train.get('arrival_time', ''),
                'duration': train.get('duration', ''),
                'classes': train.get('class_types', []),
                'available_seats': train.get('availability', {}),
                'price': train.get('fare', {}),
                'running_days': train.get('running_days', []),
                'source': 'indian_railway'
            })
        
        return trains
    
    # ==================== FLIGHTS ===================
    
    def search_flights(self, from_city, to_city, departure_date, passengers=1):
        """Search flights using external API"""
        try:
            # Using Skyscanner or similar API
            url = "https://partners.api.skyscanner.net/apiservices/pricing/v1.0/flights"
            
            params = {
                'originPlace': from_city,
                'destinationPlace': to_city,
                'outboundDate': departure_date,
                'adults': passengers,
                'currency': 'INR',
                'locale': 'en-IN'
            }
            
            headers = {
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self.format_flights(data)
            else:
                return self.get_mock_flights(from_city, to_city)
                
        except Exception as e:
            print(f"Flight API error: {str(e)}")
            return self.get_mock_flights(from_city, to_city)
    
    def get_mock_flights(self, from_city, to_city):
        """Mock flight data when API fails"""
        return [
            {
                'airline': 'Air India',
                'flight_number': 'AI620',
                'from_city': from_city,
                'to_city': to_city,
                'departure_time': '08:00',
                'arrival_time': '10:30',
                'duration': '2h 30m',
                'price': 4500,
                'class': 'Economy',
                'stops': 0,
                'booking_url': 'https://www.makemytrip.com/flights',
                'source': 'mock'
            },
            {
                'airline': 'IndiGo',
                'flight_number': '6E2341',
                'from_city': from_city,
                'to_city': to_city,
                'departure_time': '14:15',
                'arrival_time': '16:45',
                'duration': '2h 30m',
                'price': 3800,
                'class': 'Economy',
                'stops': 0,
                'booking_url': 'https://www.goibibo.com/flights',
                'source': 'mock'
            }
        ]
    
    def format_flights(self, data):
        """Format flight API response"""
        flights = []
        
        for flight in data.get('flights', []):
            flights.append({
                'airline': flight.get('airline', ''),
                'flight_number': flight.get('flight_number', ''),
                'from_city': flight.get('origin', ''),
                'to_city': flight.get('destination', ''),
                'departure_time': flight.get('departure_time', ''),
                'arrival_time': flight.get('arrival_time', ''),
                'duration': flight.get('duration', ''),
                'price': flight.get('price', 0),
                'class': flight.get('class', 'Economy'),
                'stops': flight.get('stops', 0),
                'booking_url': flight.get('booking_link', ''),
                'source': 'flight_api'
            })
        
        return flights
    
    # ==================== BUSES ===================
    
    def search_buses(self, from_city, to_city, travel_date, passengers=1):
        """Search buses using external API"""
        try:
            # Using RedBus or similar API
            url = "https://api.redbus.in/search"
            
            params = {
                'from': from_city,
                'to': to_city,
                'date': travel_date,
                'passengers': passengers
            }
            
            headers = {
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self.format_buses(data)
            else:
                return self.get_mock_buses(from_city, to_city)
                
        except Exception as e:
            print(f"Bus API error: {str(e)}")
            return self.get_mock_buses(from_city, to_city)
    
    def get_mock_buses(self, from_city, to_city):
        """Mock bus data when API fails"""
        return [
            {
                'operator': 'MSRTC',
                'bus_type': 'Volvo A/C',
                'from_city': from_city,
                'to_city': to_city,
                'departure_time': '07:00',
                'arrival_time': '11:30',
                'duration': '4h 30m',
                'price': 450,
                'seats_available': 28,
                'amenities': ['WiFi', 'Charging Point', 'A/C', 'Reclining Seats'],
                'booking_url': 'https://www.redbus.in',
                'source': 'mock'
            },
            {
                'operator': 'Neeta Travels',
                'bus_type': 'Sleeper A/C',
                'from_city': from_city,
                'to_city': to_city,
                'departure_time': '21:00',
                'arrival_time': '01:30',
                'duration': '4h 30m',
                'price': 380,
                'seats_available': 32,
                'amenities': ['A/C', 'Blankets', 'Water Bottle'],
                'booking_url': 'https://www.makemytrip.com/bus-tickets',
                'source': 'mock'
            }
        ]
    
    def format_buses(self, data):
        """Format bus API response"""
        buses = []
        
        for bus in data.get('buses', []):
            buses.append({
                'operator': bus.get('operator_name', ''),
                'bus_type': bus.get('bus_type', ''),
                'from_city': bus.get('origin', ''),
                'to_city': bus.get('destination', ''),
                'departure_time': bus.get('departure_time', ''),
                'arrival_time': bus.get('arrival_time', ''),
                'duration': bus.get('duration', ''),
                'price': bus.get('fare', 0),
                'seats_available': bus.get('available_seats', 0),
                'amenities': bus.get('amenities', []),
                'booking_url': bus.get('booking_link', ''),
                'source': 'bus_api'
            })
        
        return buses

# Initialize external APIs
external_apis = ExternalAPIs()
