"""
AEE (Ad Execution Engine) signal definitions and processing.

Defines the three categories of signals provided by AEE:
1. Targeting signals - for ad decisioning
2. Pricing signals - for bid optimization
3. Creative macros - for dynamic creative customization
"""

from typing import Dict, List, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime

class SignalCategory(str, Enum):
    """Categories of signals provided by AEE."""
    TARGETING = "targeting"
    PRICING = "pricing"
    CREATIVE_MACROS = "creative_macros"

class CreativeMacroSignal(BaseModel):
    """A creative macro signal provided by AEE for dynamic content."""
    macro_name: str
    value: str
    description: Optional[str] = None
    
class AEESignals(BaseModel):
    """Complete set of signals provided by AEE in real-time."""
    
    # Targeting signals for decisioning
    targeting: Dict[str, Any] = Field(
        default_factory=dict,
        description="Signals for ad decisioning (geo, device, context, etc.)"
    )
    
    # Pricing signals for bid optimization
    pricing: Dict[str, Any] = Field(
        default_factory=dict,
        description="Signals for bid optimization (floor prices, competition, etc.)"
    )
    
    # Creative macros for dynamic content
    creative_macros: Dict[str, str] = Field(
        default_factory=dict,
        description="Key-value pairs for creative customization"
    )

class CreativeMacroDefinition(BaseModel):
    """Definition of a creative macro that can be provided by AEE."""
    macro_name: str
    description: str
    example_value: str
    category: str  # DCO, measurement, etc.
    data_source: str  # Where the publisher gets this data

# Standard creative macro definitions that publishers can provide
STANDARD_CREATIVE_MACROS = {
    # Dynamic Creative Optimization (DCO)
    "user_segment": CreativeMacroDefinition(
        macro_name="user_segment",
        description="User segment for personalization",
        example_value="sports_enthusiast",
        category="dco",
        data_source="First-party data"
    ),
    "local_weather": CreativeMacroDefinition(
        macro_name="local_weather",
        description="Current weather condition",
        example_value="sunny",
        category="dco",
        data_source="Weather API"
    ),
    "time_of_day": CreativeMacroDefinition(
        macro_name="time_of_day",
        description="Part of day (morning/afternoon/evening)",
        example_value="evening",
        category="dco",
        data_source="User timezone"
    ),
    "content_context": CreativeMacroDefinition(
        macro_name="content_context",
        description="Context of adjacent content",
        example_value="technology_news",
        category="dco",
        data_source="Content analysis"
    ),
    "device_context": CreativeMacroDefinition(
        macro_name="device_context",
        description="Device usage context",
        example_value="commuting",
        category="dco",
        data_source="Device sensors"
    ),
    
    # Measurement & Attribution
    "impression_id": CreativeMacroDefinition(
        macro_name="impression_id",
        description="Unique impression identifier",
        example_value="imp_abc123def456",
        category="measurement",
        data_source="Publisher-generated"
    ),
    "content_id": CreativeMacroDefinition(
        macro_name="content_id",
        description="ID of adjacent content",
        example_value="article_789xyz",
        category="measurement",
        data_source="CMS"
    ),
    "placement_id": CreativeMacroDefinition(
        macro_name="placement_id",
        description="Ad placement identifier",
        example_value="homepage_top_banner",
        category="measurement",
        data_source="Ad server"
    ),
    "session_id": CreativeMacroDefinition(
        macro_name="session_id",
        description="User session identifier",
        example_value="sess_456def789",
        category="measurement",
        data_source="Publisher session management"
    ),
    
    # Publisher-specific
    "publisher_segment": CreativeMacroDefinition(
        macro_name="publisher_segment",
        description="Publisher's audience segment",
        example_value="premium_subscriber",
        category="publisher",
        data_source="Publisher CRM"
    ),
    "content_sentiment": CreativeMacroDefinition(
        macro_name="content_sentiment",
        description="Sentiment of adjacent content",
        example_value="positive",
        category="publisher",
        data_source="Content analysis"
    )
}

class CreativeMacroRequest(BaseModel):
    """Request for specific creative macros from AEE."""
    requested_macros: List[str] = Field(
        description="List of macro names requested by the buyer"
    )
    required_macros: List[str] = Field(
        default_factory=list,
        description="Macros that must be provided or the ad won't serve"
    )

class CreativeMacroCapabilities(BaseModel):
    """Publisher's creative macro capabilities."""
    supported_macros: List[str] = Field(
        description="List of macro names this publisher can provide"
    )
    macro_definitions: Dict[str, CreativeMacroDefinition] = Field(
        default_factory=dict,
        description="Detailed definitions of supported macros"
    )
    
def validate_macro_request(
    request: CreativeMacroRequest, 
    capabilities: CreativeMacroCapabilities
) -> Dict[str, Any]:
    """Validate if publisher can fulfill macro request."""
    
    missing_required = [
        macro for macro in request.required_macros 
        if macro not in capabilities.supported_macros
    ]
    
    available_requested = [
        macro for macro in request.requested_macros
        if macro in capabilities.supported_macros
    ]
    
    return {
        "can_fulfill": len(missing_required) == 0,
        "missing_required_macros": missing_required,
        "available_macros": available_requested,
        "total_requested": len(request.requested_macros),
        "total_available": len(available_requested)
    }

def process_creative_with_macros(
    creative_content: str,
    macro_values: Dict[str, str]
) -> str:
    """Process creative content by replacing macro placeholders with values.
    
    This is called by the publisher's ad server when serving the creative.
    Macros use the format: ${macro_name}
    """
    processed = creative_content
    
    for macro_name, value in macro_values.items():
        placeholder = f"${{{macro_name}}}"
        processed = processed.replace(placeholder, str(value))
    
    return processed

# Example of how this would be used in a media buy request
class MediaBuyAEERequirements(BaseModel):
    """AEE requirements for a media buy."""
    
    # Existing targeting requirements
    required_targeting_signals: List[str] = Field(
        default_factory=list,
        description="Required targeting signals (e.g., geo.city, device.type)"
    )
    
    # New creative macro requirements
    creative_macro_request: Optional[CreativeMacroRequest] = Field(
        default=None,
        description="Requested creative macros for dynamic content"
    )

# Example AEE response with all three signal types
class AEEResponse(BaseModel):
    """Complete AEE response with all signal categories."""
    
    # Decision on whether to bid/serve
    should_bid: bool
    bid_price: Optional[float] = None
    
    # Three categories of provided signals
    provided_signals: AEESignals
    
    # Additional metadata
    decision_id: str
    timestamp: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }