"""Pytest configuration file."""
import os
import sys
from unittest.mock import Mock

# Set testing mode before any imports
os.environ['ADCP_TESTING'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite:///test.db'

# Mock the init_db function to prevent database initialization during tests
sys.modules['init_database'] = Mock()
sys.modules['init_database'].init_db = Mock()

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))