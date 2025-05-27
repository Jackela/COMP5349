"""
Simple WSGI Entry Point for Flask Application
Works with conditional imports to handle both development and production environments
"""
import sys
import os

# Ensure current directory is in Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import the Flask application using conditional imports
try:
    from app import app as application
    print("✅ Flask application loaded successfully")
except ImportError as e:
    print(f"❌ Failed to import Flask application: {e}")
    raise

if __name__ == "__main__":
    application.run(debug=True, host='0.0.0.0', port=5000) 