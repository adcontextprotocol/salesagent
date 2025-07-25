from typing import List, Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

# --- V2.1 Pydantic Models ---

# --- Creative Format Discovery ---

class CreativeFormat(BaseModel):
    format_id: str
    format_type: Literal["standard", "custom"]
    spec: Dict[str, Any]

class GetPublisherCreativeFormatsResponse(BaseModel):
    formats: List[CreativeFormat]

# --- Creative Specifications ---

class StandardCreative(BaseModel):
    format_type: Literal["standard"]
    media_type: Literal["video", "audio", "display", "dooh"]
    mime: str
    w: Optional[int] = None
    h: Optional[int] = None
    dur: Optional[int] = None
    protocols: Optional[List[int]] = None
    api: Optional[List[int]] = None

class CustomCreative(BaseModel):
    format_type: Literal["custom"]
    assets: Dict[str, Any]

class CreativeAsset(BaseModel):
    id: str
    format_id: str
    spec: Union[StandardCreative, CustomCreative] = Field(..., discriminator='format_type')

# --- Package Discovery (get_packages) ---

class GetPackagesRequest(BaseModel):
    budget: float
    currency: str
    start_time: datetime
    end_time: datetime
    creatives: List[CreativeAsset]
    targeting: Dict[str, Any]

class CreativeCompatibility(BaseModel):
    compatible: bool
    requires_approval: bool
    reason: Optional[str] = None

class PricingGuidance(BaseModel):
    floor_cpm: Optional[float] = None
    suggested_cpm: float
    p25: float
    p50: float
    p75: float
    p90: float

class DeliveryEstimate(BaseModel):
    impressions: int
    win_rate: float

class MediaPackage(BaseModel):
    package_id: str
    name: str
    description: str
    type: Literal["custom", "catalog"]
    delivery_type: Literal["guaranteed", "non_guaranteed"]
    creative_compatibility: Dict[str, CreativeCompatibility]
    cpm: Optional[float] = None
    budget: Optional[float] = None
    pricing: Optional[PricingGuidance] = None
    delivery_estimates: Optional[Dict[str, DeliveryEstimate]] = None

class GetPackagesResponse(BaseModel):
    query_id: str
    packages: List[MediaPackage]

# --- Media Buy Creation (create_media_buy) ---

class SelectedPackage(BaseModel):
    package_id: str
    max_cpm: Optional[float] = None

class CreateMediaBuyRequest(BaseModel):
    selected_packages: List[SelectedPackage]
    billing_entity: str
    po_number: str

class CreateMediaBuyResponse(BaseModel):
    media_buy_id: str
    status: str
    creative_deadline: Optional[datetime] = None

# --- Status and Reporting ---
# (These models remain largely the same as V2)

class AssetStatus(BaseModel):
    creative_id: str
    status: str
    estimated_approval_time: Optional[datetime] = None

class AddCreativeAssetsResponse(BaseModel):
    status: str
    assets: List[AssetStatus]

class CheckMediaBuyStatusResponse(BaseModel):
    media_buy_id: str
    status: str
    last_updated: Optional[datetime] = None
