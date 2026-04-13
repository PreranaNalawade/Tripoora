/**
 * Admin Dashboard Security Features
 * Tripoora - Maharashtra Travel Planning Platform
 */

(function() {
    'use strict';
    
    console.log('🔒 Initializing Admin Security Features...');
    
    // 1. Prevent browser back button and auto-logout
    history.pushState(null, null, location.href);
    window.onpopstate = function() {
        history.go(1);
        alert('For security reasons, you will be logged out when navigating back.');
        window.location.href = '/logout';
    };
    
    // 2. Disable right-click context menu
    document.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        return false;
    });
    
    // 3. Disable certain keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Disable F5 refresh
        if (e.key === 'F5') {
            e.preventDefault();
        }
        // Disable Ctrl+R refresh
        if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
            e.preventDefault();
        }
        // Disable Ctrl+W close tab
        if ((e.ctrlKey || e.metaKey) && e.key === 'w') {
            e.preventDefault();
        }
        // Disable Backspace navigation
        if (e.key === 'Backspace' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
        }
    });
    
    // 4. Session timeout - auto logout after 30 minutes of inactivity
    let inactivityTimer;
    const INACTIVITY_TIMEOUT = 30 * 60 * 1000; // 30 minutes
    
    function resetInactivityTimer() {
        clearTimeout(inactivityTimer);
        inactivityTimer = setTimeout(function() {
            alert('Session expired due to inactivity. You will be logged out.');
            window.location.href = '/logout';
        }, INACTIVITY_TIMEOUT);
    }
    
    // Reset timer on user activity
    ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'].forEach(function(event) {
        document.addEventListener(event, resetInactivityTimer, true);
    });
    
    // Initialize timer
    resetInactivityTimer();
    
    // 5. Prevent opening links in new tab/window
    window.addEventListener('click', function(e) {
        if (e.target.tagName === 'A' && e.target.href && !e.target.href.includes('logout')) {
            if (e.ctrlKey || e.metaKey || e.button === 1) {
                e.preventDefault();
                alert('Opening links in new tabs is disabled for security.');
            }
        }
    });
    
    // 6. Clear history on load
    if (window.history && window.history.pushState) {
        window.history.pushState(null, null, window.location.href);
    }
    
    // 7. Warn before leaving page
    window.addEventListener('beforeunload', function(e) {
        e.preventDefault();
        e.returnValue = '';
    });
    
    // 8. Prevent navigation to other pages
    document.addEventListener('click', function(e) {
        const target = e.target.closest('a');
        if (target && target.href) {
            const url = new URL(target.href);
            const allowedPaths = ['/dashboard/admin', '/logout', '/api/admin'];
            const isAllowed = allowedPaths.some(path => url.pathname.startsWith(path));
            
            if (!isAllowed && !target.href.includes('logout')) {
                e.preventDefault();
                alert('Admin users can only access the admin dashboard.');
                return false;
            }
        }
    });
    
    console.log('✅ Admin Security Features Activated');
    console.log('- Back button disabled → Auto logout');
    console.log('- Right-click disabled');
    console.log('- Keyboard shortcuts restricted');
    console.log('- 30-minute inactivity timeout enabled');
    console.log('- Navigation restricted to admin dashboard only');
})();
