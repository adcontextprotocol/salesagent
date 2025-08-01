#!/usr/bin/env python3
"""
Add test authentication endpoint to admin_ui.py for UI testing.
This script adds a test-only authentication endpoint that bypasses OAuth.
"""

import os
import sys

TEST_AUTH_CODE = '''
# Test authentication endpoint (added for UI testing)
if os.environ.get('ENABLE_TEST_AUTH') == 'true':
    @app.route('/test/auth/login', methods=['POST'])
    def test_auth_login():
        """Test-only authentication endpoint for UI testing."""
        if os.environ.get('FLASK_ENV') != 'development':
            return jsonify({"error": "Test auth only available in development"}), 403
        
        data = request.get_json() or request.form
        email = data.get('email', 'test@example.com')
        role = data.get('role', 'super_admin')
        username = data.get('username', email.split('@')[0])
        tenant_id = data.get('tenant_id')
        
        # Set session as if user logged in via OAuth
        session['authenticated'] = True
        session['role'] = role
        session['email'] = email
        session['username'] = username
        if tenant_id:
            session['tenant_id'] = tenant_id
        
        return jsonify({
            "success": True,
            "email": email,
            "role": role
        })
    
    @app.route('/test/auth/logout', methods=['POST'])
    def test_auth_logout():
        """Test-only logout endpoint."""
        session.clear()
        return jsonify({"success": True})
    
    @app.route('/test/auth/status', methods=['GET'])
    def test_auth_status():
        """Check current authentication status."""
        return jsonify({
            "authenticated": session.get('authenticated', False),
            "email": session.get('email'),
            "role": session.get('role'),
            "tenant_id": session.get('tenant_id')
        })
'''

def add_test_auth_to_admin_ui():
    """Add test authentication endpoints to admin_ui.py."""
    admin_ui_path = os.path.join(os.path.dirname(__file__), '..', 'admin_ui.py')
    
    # Read the current content
    with open(admin_ui_path, 'r') as f:
        content = f.read()
    
    # Check if test auth already added
    if '/test/auth/login' in content:
        print("Test authentication endpoints already present in admin_ui.py")
        return True
    
    # Find a good place to insert - after the last route definition
    # Look for the if __name__ == '__main__': block
    insert_position = content.rfind("if __name__ == '__main__':")
    
    if insert_position == -1:
        print("Could not find appropriate insertion point in admin_ui.py")
        return False
    
    # Insert the test auth code before the main block
    new_content = (
        content[:insert_position] + 
        "\n" + TEST_AUTH_CODE + "\n\n" + 
        content[insert_position:]
    )
    
    # Create backup
    backup_path = admin_ui_path + '.backup'
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"Created backup at {backup_path}")
    
    # Write the modified content
    with open(admin_ui_path, 'w') as f:
        f.write(new_content)
    
    print("Successfully added test authentication endpoints to admin_ui.py")
    print("\nTo use test authentication:")
    print("1. Set environment variable: ENABLE_TEST_AUTH=true")
    print("2. Ensure FLASK_ENV=development")
    print("3. Restart the admin UI server")
    print("\nTest endpoints added:")
    print("- POST /test/auth/login - Login with test credentials")
    print("- POST /test/auth/logout - Logout")
    print("- GET /test/auth/status - Check auth status")
    
    return True

if __name__ == '__main__':
    if '--remove' in sys.argv:
        # TODO: Add removal functionality
        print("Removal not implemented yet")
    else:
        add_test_auth_to_admin_ui()