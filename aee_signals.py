"""
AEE (Ad Execution Engine) signal definitions.

Defines the three types of provided signals from AEE:
1. May Include - Signals to include for targeting
2. Must Exclude - Signals that must be excluded  
3. Creative Macro - Arbitrary string to inject into creative
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class AEEProvidedSignals(BaseModel):
    """Signals provided by AEE for ad decisioning and customization."""
    
    # Existing signal types
    may_include: Optional[List[str]] = Field(
        default=None,
        description="Signals that may be included for targeting"
    )
    
    must_exclude: Optional[List[str]] = Field(
        default=None,
        description="Signals that must be excluded"
    )
    
    # New third signal type
    creative_macro: Optional[str] = Field(
        default=None,
        description="Arbitrary string to be injected into creative by ad server"
    )

class AEEResponse(BaseModel):
    """Complete AEE response with decision and signals."""
    
    # Decision
    should_bid: bool
    bid_price: Optional[float] = None
    
    # Provided signals (all three types)
    provided_signals: AEEProvidedSignals
    
    # Metadata
    decision_id: str
    timestamp: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# Example of how the creative_macro might be used
"""
The creative_macro field allows AEE to pass an arbitrary string that the ad server
can inject into the creative. This enables dynamic content without predefined
macro substitution.

Example AEE Response:
{
    "should_bid": true,
    "bid_price": 5.50,
    "provided_signals": {
        "may_include": ["sports", "premium_user"],
        "must_exclude": ["competitor_xyz"],
        "creative_macro": "city:San Francisco|weather:sunny|segment:tech_professional"
    }
}

The ad server (e.g., GAM) can then inject this creative_macro string into the 
creative where a placeholder exists, enabling dynamic customization based on
real-time AEE data.
"""