from typing import List, Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, Field
from datetime import datetime

# --- V2.2 Pydantic Models ---

# --- Creative Format Discovery ---

class CreativeFormat(BaseModel):
    format_id: str
    format_type: Literal["standard", "custom"]
    spec: Dict[str, Any]

class GetPublisherCreativeFormatsResponse(BaseModel):
    formats: List[CreativeFormat]

# --- Package Discovery (get_packages) ---

class BudgetRange(BaseModel):
    min: float
    max: float

class GetPackagesRequest(BaseModel):
    brief: Optional[str] = None
    media_types: Optional[List[str]] = None
    budget_range: Optional[BudgetRange] = None

class MediaPackage(BaseModel):
    package_id: str
    name: str
    description: str
    type: Literal["custom", "catalog"]
    delivery_type: Literal["guaranteed", "non_guaranteed"]
    cpm: Optional[float] = None
    pricing: Optional[Dict[str, Any]] = None # Simplified for now

class GetPackagesResponse(BaseModel):
    query_id: str
    packages: List[MediaPackage]

# --- Media Buy Creation (create_media_buy) ---

class GeoTargeting(BaseModel):
    countries: Optional[List[str]] = None
    exclude_regions: Optional[List[str]] = None

class ScheduleTargeting(BaseModel):
    days: Optional[List[str]] = None # e.g., ["mon-fri"]
    hours: Optional[str] = None # e.g., "6am-11pm"

class ContentPreferences(BaseModel):
    avoid: Optional[List[str]] = None

class TargetingOverlay(BaseModel):
    geo: Optional[GeoTargeting] = None
    schedule: Optional[ScheduleTargeting] = None
    content_preferences: Optional[ContentPreferences] = None

class CreativeAssignment(BaseModel):
    package_id: str
    creative_id: str

class CreateMediaBuyRequest(BaseModel):
    query_id: str
    selected_packages: List[Dict[str, Any]] # e.g., [{"package_id": "pkg_1"}]
    po_number: str
    targeting: Optional[TargetingOverlay] = None
    creatives: List[Dict[str, Any]] # Full creative specs
    creative_assignments: List[CreativeAssignment]

class CreateMediaBuyResponse(BaseModel):
    media_buy_id: str
    status: str

# --- Status and Reporting ---

class CheckMediaBuyStatusResponse(BaseModel):
    media_buy_id: str
    status: str
    packages: List[Dict[str, Any]]