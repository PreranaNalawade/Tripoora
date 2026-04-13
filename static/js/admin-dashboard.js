/**
 * Admin Dashboard Complete Functionality
 * Tripoora - Maharashtra Travel Planning Platform
 */

(function() {
    'use strict';
    
    console.log('🚀 Initializing Admin Dashboard Functionality...');

    // Section Switching
    window.showSection = function(sectionName) {
        document.querySelectorAll('.dashboard-section').forEach(section => {
            section.classList.remove('active');
        });
        
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
        });
        
        const targetSection = document.getElementById(sectionName + '-section');
        if (targetSection) {
            targetSection.classList.add('active');
        }
        
        event.target.classList.add('active');
        
        // Update page header
        const headers = {
            'overview': 'Dashboard Overview',
            'users': 'User Management',
            'hotels': 'Hotel Management',
            'tours': 'Tour Management',
            'transports': 'Transport Management',
            'packages': 'Package Management',
            'hidden-gems': 'Hidden Gems Management',
            'itineraries': 'AI Itineraries',
            'messages': 'Contact Messages'
        };
        const headerElement = document.querySelector('.page-header h1');
        if (headerElement) {
            headerElement.textContent = headers[sectionName] || 'Dashboard';
        }
    };

    // Delete User
    window.deleteUser = function(userId, username) {
        if (!confirm(`Are you sure you want to delete user "${username}"? This action cannot be undone.`)) {
            return;
        }
        
        fetch(`/api/admin/users/${userId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('User deleted successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.message || 'Failed to delete user'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to delete user. Please try again.');
        });
    };

    // Delete Hotel
    window.deleteHotel = function(hotelId, hotelName) {
        if (!confirm(`Are you sure you want to delete hotel "${hotelName}"? This action cannot be undone.`)) {
            return;
        }
        
        fetch(`/api/admin/hotels/${hotelId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Hotel deleted successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.message || 'Failed to delete hotel'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to delete hotel. Please try again.');
        });
    };

    // Delete Transport
    window.deleteTransport = function(transportId, agencyName) {
        if (!confirm(`Are you sure you want to delete transport "${agencyName}"? This action cannot be undone.`)) {
            return;
        }
        
        fetch(`/api/admin/transports/${transportId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Transport deleted successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.message || 'Failed to delete transport'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to delete transport. Please try again.');
        });
    };

    // Delete Package
    window.deletePackage = function(packageId, packageTitle) {
        if (!confirm(`Are you sure you want to delete package "${packageTitle}"? This action cannot be undone.`)) {
            return;
        }
        
        fetch(`/api/admin/packages/${packageId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Package deleted successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.message || 'Failed to delete package'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to delete package. Please try again.');
        });
    };

    // Delete Tour
    window.deleteTour = function(tourId, tourTitle) {
        if (!confirm(`Are you sure you want to delete tour "${tourTitle}"? This action cannot be undone.`)) {
            return;
        }
        
        fetch(`/api/admin/tours/${tourId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Tour deleted successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.message || 'Failed to delete tour'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to delete tour. Please try again.');
        });
    };

    // Delete Hidden Gem
    window.deleteHiddenGem = function(gemId, gemName) {
        if (!confirm(`Are you sure you want to delete hidden gem "${gemName}"? This action cannot be undone.`)) {
            return;
        }
        
        fetch(`/api/admin/hidden-gems/${gemId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Hidden gem deleted successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.message || 'Failed to delete hidden gem'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to delete hidden gem. Please try again.');
        });
    };

    // Delete Itinerary
    window.deleteItinerary = function(itineraryId, city) {
        if (!confirm(`Are you sure you want to delete itinerary for "${city}"? This action cannot be undone.`)) {
            return;
        }
        
        fetch(`/api/admin/itineraries/${itineraryId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Itinerary deleted successfully!');
                location.reload();
            } else {
                alert('Error: ' + (data.message || 'Failed to delete itinerary'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to delete itinerary. Please try again.');
        });
    };

    // Delete Message
    window.deleteMessage = function(messageId) {
        if (!confirm('Are you sure you want to delete this message? This action cannot be undone.')) {
            return;
        }
        
        fetch(`/api/admin/messages/${messageId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (!response.ok && response.status === 401) {
                alert('Session expired. Please login again.');
                window.location.href = '/login';
                return null;
            }
            if (!response.ok && response.status === 403) {
                alert('Access denied. Admin privileges required.');
                return null;
            }
            return response.json();
        })
        .then(data => {
            if (!data) return;
            if (data.success) {
                // Remove the row from the table without full reload
                const btn = document.querySelector(`button[onclick="deleteMessage(${messageId})"]`);
                if (btn) {
                    const row = btn.closest('tr');
                    if (row) row.remove();
                }
                alert('Message deleted successfully!');
            } else {
                alert('Error: ' + (data.message || 'Failed to delete message'));
            }
        })
        .catch(error => {
            console.error('Delete message error:', error);
            alert('Failed to delete message. Please try again.');
        });
    };

    // View Details Functions
    window.viewUser = function(userId) {
        alert('User details view - Feature coming soon!');
    };

    window.viewHotel = function(hotelId) {
        window.open(`/hotels/${hotelId}`, '_blank');
    };

    window.viewItinerary = function(itineraryId) {
        alert('Itinerary details view - Feature coming soon!');
    };

    window.viewMessage = function(messageId, name, email, subject, message) {
        const modal = `
            <div style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 9999;" onclick="this.remove()">
                <div style="background: white; padding: 2rem; border-radius: 15px; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto;" onclick="event.stopPropagation()">
                    <h3 style="margin-bottom: 1rem; color: #333;">Message Details</h3>
                    <div style="margin-bottom: 1rem;">
                        <p style="margin: 0.5rem 0;"><strong>From:</strong> ${name}</p>
                        <p style="margin: 0.5rem 0;"><strong>Email:</strong> <a href="mailto:${email}">${email}</a></p>
                        <p style="margin: 0.5rem 0;"><strong>Subject:</strong> ${subject}</p>
                    </div>
                    <div style="margin-top: 1rem;">
                        <p style="margin-bottom: 0.5rem;"><strong>Message:</strong></p>
                        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; white-space: pre-wrap;">${message}</div>
                    </div>
                    <button onclick="this.closest('div[style*=fixed]').remove()" style="margin-top: 1.5rem; padding: 0.75rem 1.5rem; background: #dc3545; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">Close</button>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modal);
    };

    // Toggle Tour Status
    window.toggleTourStatus = function(tourId, currentStatus) {
        const newStatus = !currentStatus;
        fetch(`/api/admin/tours/${tourId}/status`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ active: newStatus })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`Tour ${newStatus ? 'activated' : 'deactivated'} successfully!`);
                location.reload();
            } else {
                alert('Error: ' + (data.message || 'Failed to update tour status'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to update tour status. Please try again.');
        });
    };

    // Search functionality
    window.searchTable = function(sectionId, searchTerm) {
        const table = document.querySelector(`#${sectionId}-section table tbody`);
        if (!table) return;
        
        const rows = table.getElementsByTagName('tr');
        
        for (let row of rows) {
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(searchTerm.toLowerCase()) ? '' : 'none';
        }
    };

    // Export data to CSV
    window.exportToCSV = function(sectionName) {
        alert(`Exporting ${sectionName} data to CSV - Feature coming soon!`);
    };

    // Refresh dashboard data
    window.refreshDashboard = function() {
        location.reload();
    };

    console.log('✅ Admin Dashboard Functionality Loaded Successfully');
    console.log('📊 Available Functions:');
    console.log('  - showSection(name)');
    console.log('  - deleteUser(id, username)');
    console.log('  - deleteHotel(id, name)');
    console.log('  - deleteTransport(id, name)');
    console.log('  - deletePackage(id, title)');
    console.log('  - deleteTour(id, title)');
    console.log('  - deleteHiddenGem(id, name)');
    console.log('  - deleteItinerary(id, city)');
    console.log('  - deleteMessage(id)');
    console.log('  - viewMessage(id, name, email, subject, message)');
    console.log('  - toggleTourStatus(id, currentStatus)');
})();
