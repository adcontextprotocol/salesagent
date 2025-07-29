"""
Creative macros processor for AEE signals.

Supports dynamic creative optimization (DCO) and measurement macros
that can be filled out by publishers based on AEE context.
"""

import re
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Standard macro definitions
MACRO_DEFINITIONS = {
    # DCO (Dynamic Creative Optimization) macros
    "DCO_USER_SEGMENT": {
        "name": "User Segment",
        "description": "User segment identifier for personalization",
        "example": "${DCO_USER_SEGMENT}",
        "aee_field": "user_segment",
        "fallback": "default"
    },
    "DCO_GEO_CITY": {
        "name": "City Name",
        "description": "User's city for localized messaging",
        "example": "${DCO_GEO_CITY}",
        "aee_field": "geo.city",
        "fallback": "your area"
    },
    "DCO_GEO_REGION": {
        "name": "Region/State",
        "description": "User's state or region",
        "example": "${DCO_GEO_REGION}",
        "aee_field": "geo.region",
        "fallback": "your region"
    },
    "DCO_WEATHER": {
        "name": "Weather Condition",
        "description": "Current weather condition",
        "example": "${DCO_WEATHER}",
        "aee_field": "context.weather",
        "fallback": "today"
    },
    "DCO_TIME_OF_DAY": {
        "name": "Time of Day",
        "description": "Morning, afternoon, evening, night",
        "example": "${DCO_TIME_OF_DAY}",
        "aee_field": "context.time_of_day",
        "fallback": "now"
    },
    "DCO_DEVICE_TYPE": {
        "name": "Device Type",
        "description": "Device category (mobile, desktop, tablet)",
        "example": "${DCO_DEVICE_TYPE}",
        "aee_field": "device.type",
        "fallback": "device"
    },
    "DCO_CONTENT_CATEGORY": {
        "name": "Content Category",
        "description": "Category of adjacent content",
        "example": "${DCO_CONTENT_CATEGORY}",
        "aee_field": "content.category",
        "fallback": "content"
    },
    
    # Measurement macros
    "MEASURE_IMPRESSION_ID": {
        "name": "Impression ID",
        "description": "Unique impression identifier",
        "example": "${MEASURE_IMPRESSION_ID}",
        "aee_field": "impression_id",
        "fallback": None  # Generated if not provided
    },
    "MEASURE_TIMESTAMP": {
        "name": "Timestamp",
        "description": "Unix timestamp of impression",
        "example": "${MEASURE_TIMESTAMP}",
        "aee_field": "timestamp",
        "fallback": None  # Generated if not provided
    },
    "MEASURE_PAGE_URL": {
        "name": "Page URL",
        "description": "Current page URL (web only)",
        "example": "${MEASURE_PAGE_URL}",
        "aee_field": "page_url",
        "fallback": ""
    },
    "MEASURE_APP_BUNDLE": {
        "name": "App Bundle",
        "description": "Mobile app bundle ID",
        "example": "${MEASURE_APP_BUNDLE}",
        "aee_field": "app.bundle",
        "fallback": ""
    },
    "MEASURE_USER_ID": {
        "name": "User ID",
        "description": "Hashed user identifier",
        "example": "${MEASURE_USER_ID}",
        "aee_field": "user.id",
        "fallback": ""
    },
    "MEASURE_LAT_LONG": {
        "name": "Latitude/Longitude",
        "description": "Geo coordinates for location attribution",
        "example": "${MEASURE_LAT_LONG}",
        "aee_field": "geo.lat_long",
        "fallback": ""
    },
    "MEASURE_POSTAL_CODE": {
        "name": "Postal Code",
        "description": "Postal/ZIP code",
        "example": "${MEASURE_POSTAL_CODE}",
        "aee_field": "geo.postal_code",
        "fallback": ""
    },
    "MEASURE_CONTENT_ID": {
        "name": "Content ID",
        "description": "Adjacent content identifier",
        "example": "${MEASURE_CONTENT_ID}",
        "aee_field": "content.id",
        "fallback": ""
    },
    "MEASURE_AD_SLOT": {
        "name": "Ad Slot",
        "description": "Ad slot or placement ID",
        "example": "${MEASURE_AD_SLOT}",
        "aee_field": "ad_slot",
        "fallback": ""
    },
    
    # Privacy-safe macros
    "PRIVACY_CONSENT": {
        "name": "Privacy Consent",
        "description": "User consent status",
        "example": "${PRIVACY_CONSENT}",
        "aee_field": "privacy.consent",
        "fallback": "unknown"
    },
    "PRIVACY_DO_NOT_TRACK": {
        "name": "Do Not Track",
        "description": "DNT signal status",
        "example": "${PRIVACY_DO_NOT_TRACK}",
        "aee_field": "privacy.dnt",
        "fallback": "0"
    }
}

class CreativeMacroProcessor:
    """Processes creative macros for AEE integration."""
    
    def __init__(self):
        self.macro_pattern = re.compile(r'\$\{([A-Z_]+)\}')
    
    def get_available_macros(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of available macros, optionally filtered by category."""
        macros = []
        
        for macro_key, macro_def in MACRO_DEFINITIONS.items():
            if category:
                if category.upper() == "DCO" and not macro_key.startswith("DCO_"):
                    continue
                elif category.upper() == "MEASUREMENT" and not macro_key.startswith("MEASURE_"):
                    continue
                elif category.upper() == "PRIVACY" and not macro_key.startswith("PRIVACY_"):
                    continue
            
            macros.append({
                "macro": macro_key,
                "syntax": macro_def["example"],
                "name": macro_def["name"],
                "description": macro_def["description"],
                "category": macro_key.split("_")[0].lower()
            })
        
        return macros
    
    def extract_macros(self, creative_content: str) -> List[str]:
        """Extract all macro placeholders from creative content."""
        matches = self.macro_pattern.findall(creative_content)
        return list(set(matches))  # Remove duplicates
    
    def get_required_aee_fields(self, macros: List[str]) -> List[str]:
        """Get list of AEE fields required for the given macros."""
        required_fields = []
        
        for macro in macros:
            if macro in MACRO_DEFINITIONS:
                aee_field = MACRO_DEFINITIONS[macro]["aee_field"]
                if aee_field:
                    required_fields.append(aee_field)
        
        return list(set(required_fields))  # Remove duplicates
    
    def process_macros(self, creative_content: str, aee_context: Dict[str, Any]) -> str:
        """Replace macros in creative content with values from AEE context."""
        processed_content = creative_content
        
        # Find all macros in the content
        macros = self.extract_macros(creative_content)
        
        for macro in macros:
            if macro not in MACRO_DEFINITIONS:
                logger.warning(f"Unknown macro: {macro}")
                continue
            
            macro_def = MACRO_DEFINITIONS[macro]
            value = self._get_value_from_context(aee_context, macro_def["aee_field"])
            
            # Use fallback if no value found
            if value is None:
                if macro_def["fallback"] is not None:
                    value = macro_def["fallback"]
                elif macro == "MEASURE_IMPRESSION_ID":
                    # Generate impression ID if not provided
                    import uuid
                    value = str(uuid.uuid4())
                elif macro == "MEASURE_TIMESTAMP":
                    # Generate timestamp if not provided
                    value = str(int(datetime.utcnow().timestamp()))
                else:
                    value = ""
            
            # Replace macro with value
            macro_placeholder = f"${{{macro}}}"
            processed_content = processed_content.replace(macro_placeholder, str(value))
        
        return processed_content
    
    def _get_value_from_context(self, context: Dict[str, Any], field_path: str) -> Any:
        """Extract value from nested context using dot notation."""
        if not field_path:
            return None
        
        parts = field_path.split(".")
        value = context
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        
        return value
    
    def validate_creative_macros(self, creative_content: str) -> Dict[str, Any]:
        """Validate macros in creative content."""
        macros = self.extract_macros(creative_content)
        
        validation_result = {
            "valid": True,
            "macros_found": macros,
            "unknown_macros": [],
            "required_aee_fields": [],
            "warnings": []
        }
        
        for macro in macros:
            if macro not in MACRO_DEFINITIONS:
                validation_result["unknown_macros"].append(macro)
                validation_result["warnings"].append(f"Unknown macro: ${{{macro}}}")
                validation_result["valid"] = False
        
        # Get required AEE fields
        validation_result["required_aee_fields"] = self.get_required_aee_fields(macros)
        
        # Add warnings for measurement macros without privacy macros
        if any(m.startswith("MEASURE_") for m in macros):
            if not any(m.startswith("PRIVACY_") for m in macros):
                validation_result["warnings"].append(
                    "Measurement macros used without privacy consent macros"
                )
        
        return validation_result
    
    def generate_macro_documentation(self) -> str:
        """Generate markdown documentation for all available macros."""
        doc = "# Creative Macro Reference\n\n"
        
        categories = {
            "DCO": "Dynamic Creative Optimization",
            "MEASURE": "Measurement & Attribution",
            "PRIVACY": "Privacy & Consent"
        }
        
        for category_prefix, category_name in categories.items():
            doc += f"## {category_name}\n\n"
            
            for macro_key, macro_def in MACRO_DEFINITIONS.items():
                if macro_key.startswith(category_prefix):
                    doc += f"### {macro_def['name']}\n"
                    doc += f"- **Syntax**: `{macro_def['example']}`\n"
                    doc += f"- **Description**: {macro_def['description']}\n"
                    doc += f"- **AEE Field**: `{macro_def['aee_field']}`\n"
                    if macro_def['fallback'] is not None:
                        doc += f"- **Fallback**: `{macro_def['fallback']}`\n"
                    doc += "\n"
        
        return doc


# Example usage
if __name__ == "__main__":
    processor = CreativeMacroProcessor()
    
    # Example creative with macros
    creative_html = """
    <div class="ad-container">
        <h1>Great deals in ${DCO_GEO_CITY}!</h1>
        <p>Perfect for your ${DCO_DEVICE_TYPE} this ${DCO_TIME_OF_DAY}</p>
        <img src="https://track.example.com/imp?id=${MEASURE_IMPRESSION_ID}&ts=${MEASURE_TIMESTAMP}&loc=${MEASURE_LAT_LONG}">
    </div>
    """
    
    # Example AEE context
    aee_context = {
        "geo": {
            "city": "San Francisco",
            "region": "CA",
            "lat_long": "37.7749,-122.4194"
        },
        "device": {
            "type": "mobile"
        },
        "context": {
            "time_of_day": "evening"
        },
        "impression_id": "imp_12345"
    }
    
    # Process macros
    processed = processor.process_macros(creative_html, aee_context)
    print("Processed creative:")
    print(processed)
    
    # Validate macros
    validation = processor.validate_creative_macros(creative_html)
    print("\nValidation result:")
    print(validation)