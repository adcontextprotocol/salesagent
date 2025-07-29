"""Server-side validation utilities for form inputs."""

import re
import json
from urllib.parse import urlparse
from typing import Dict, List, Optional, Any

class ValidationError(Exception):
    """Raised when validation fails."""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

class FormValidator:
    """Form validation utility class."""
    
    @staticmethod
    def validate_email(email: str) -> Optional[str]:
        """Validate email address format."""
        if not email:
            return "Email is required"
        
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return "Invalid email address format"
        
        return None
    
    @staticmethod
    def validate_url(url: str, required: bool = False) -> Optional[str]:
        """Validate URL format."""
        if not url and required:
            return "URL is required"
        
        if not url:
            return None
            
        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                return "Invalid URL format"
            
            if result.scheme not in ['http', 'https']:
                return "URL must use http or https protocol"
                
            return None
        except Exception:
            return "Invalid URL format"
    
    @staticmethod
    def validate_webhook_url(url: str) -> Optional[str]:
        """Validate webhook URL (more specific than general URL)."""
        if not url:
            return None  # Webhooks are optional
            
        # First do general URL validation
        url_error = FormValidator.validate_url(url)
        if url_error:
            return url_error
        
        # Check for known webhook patterns
        if 'hooks.slack.com/services/' in url:
            # Validate Slack webhook format
            parts = url.split('/')
            if len(parts) < 7:
                return "Invalid Slack webhook URL format"
        
        return None
    
    @staticmethod
    def validate_json(json_str: str, required: bool = True) -> Optional[str]:
        """Validate JSON string."""
        if not json_str and required:
            return "JSON configuration is required"
            
        if not json_str:
            return None
            
        try:
            json.loads(json_str)
            return None
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {str(e)}"
    
    @staticmethod
    def validate_principal_id(principal_id: str) -> Optional[str]:
        """Validate principal ID format."""
        if not principal_id:
            return "Principal ID is required"
            
        if not re.match(r'^[a-zA-Z0-9_-]+$', principal_id):
            return "Principal ID can only contain letters, numbers, underscores, and hyphens"
            
        if len(principal_id) < 3:
            return "Principal ID must be at least 3 characters long"
            
        if len(principal_id) > 50:
            return "Principal ID must be less than 50 characters"
            
        return None
    
    @staticmethod
    def validate_network_id(network_id: str) -> Optional[str]:
        """Validate network ID (should be numeric)."""
        if not network_id:
            return "Network ID is required"
            
        if not network_id.isdigit():
            return "Network ID must be numeric"
            
        return None
    
    @staticmethod
    def validate_required(value: str, field_name: str = "Field") -> Optional[str]:
        """Validate that a field is not empty."""
        if not value or not value.strip():
            return f"{field_name} is required"
        return None
    
    @staticmethod
    def validate_length(value: str, min_length: Optional[int] = None, 
                       max_length: Optional[int] = None, field_name: str = "Field") -> Optional[str]:
        """Validate string length."""
        if not value:
            return None
            
        if min_length and len(value) < min_length:
            return f"{field_name} must be at least {min_length} characters"
            
        if max_length and len(value) > max_length:
            return f"{field_name} must be less than {max_length} characters"
            
        return None
    
    @staticmethod
    def validate_tenant_name(name: str) -> Optional[str]:
        """Validate tenant name."""
        if error := FormValidator.validate_required(name, "Tenant name"):
            return error
            
        if error := FormValidator.validate_length(name, min_length=3, max_length=100, field_name="Tenant name"):
            return error
            
        return None
    
    @staticmethod
    def validate_subdomain(subdomain: str) -> Optional[str]:
        """Validate subdomain format."""
        if not subdomain:
            return "Subdomain is required"
            
        # Allow localhost for development
        if subdomain == "localhost":
            return None
            
        if not re.match(r'^[a-z0-9-]+$', subdomain):
            return "Subdomain can only contain lowercase letters, numbers, and hyphens"
            
        if subdomain.startswith('-') or subdomain.endswith('-'):
            return "Subdomain cannot start or end with a hyphen"
            
        if len(subdomain) < 3:
            return "Subdomain must be at least 3 characters long"
            
        if len(subdomain) > 63:
            return "Subdomain must be less than 63 characters"
            
        return None
    
    @staticmethod
    def validate_role(role: str) -> Optional[str]:
        """Validate user role."""
        valid_roles = ['admin', 'manager', 'viewer']
        if role not in valid_roles:
            return f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        return None

def validate_form_data(data: Dict[str, Any], validators: Dict[str, List]) -> Dict[str, str]:
    """
    Validate form data using specified validators.
    
    Args:
        data: Form data dictionary
        validators: Dictionary mapping field names to list of validator functions
        
    Returns:
        Dictionary of field names to error messages (empty if no errors)
    """
    errors = {}
    
    for field, field_validators in validators.items():
        value = data.get(field, '')
        
        for validator in field_validators:
            if callable(validator):
                error = validator(value)
                if error:
                    errors[field] = error
                    break  # Stop on first error for this field
    
    return errors

def sanitize_json(json_str: str) -> str:
    """Sanitize and format JSON string."""
    try:
        # Parse and re-serialize to ensure valid JSON
        parsed = json.loads(json_str)
        return json.dumps(parsed, indent=2)
    except json.JSONDecodeError:
        return json_str  # Return as-is if not valid JSON

def sanitize_url(url: str) -> str:
    """Sanitize URL by ensuring proper format."""
    if not url:
        return url
        
    # Ensure URL has a scheme
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        
    # Remove trailing slashes
    return url.rstrip('/')

def sanitize_form_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize form data before saving."""
    sanitized = {}
    
    for key, value in data.items():
        if isinstance(value, str):
            # Trim whitespace
            value = value.strip()
            
            # Sanitize specific field types
            if 'url' in key.lower():
                value = sanitize_url(value)
            elif key == 'config' or 'json' in key.lower():
                value = sanitize_json(value)
                
        sanitized[key] = value
        
    return sanitized