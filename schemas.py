from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, date

# --- V2.3 Pydantic Models (Bearer Auth, Restored & Complete) ---

# --- Core Models ---
class DeliveryOptions(BaseModel):
    hosted: Optional[Dict[str, Any]] = None
    vast: Optional[Dict[str, Any]] = None

class Format(BaseModel):
    format_id: str
    name: str
    type: Literal["video", "audio", "display", "native", "dooh"]
    description: str
    specs: Dict[str, Any]
    delivery_options: DeliveryOptions

class Targeting(BaseModel):
    geography: Optional[List[str]] = None
    exclude_geography: Optional[List[str]] = None
    day_parts: Optional[List[str]] = None
    technology: Optional[List[str]] = None
    content_categories_include: Optional[List[str]] = None
    content_categories_exclude: Optional[List[str]] = None

class PriceGuidance(BaseModel):
    floor: float
    p25: Optional[float] = None
    p50: Optional[float] = None
    p75: Optional[float] = None
    p90: Optional[float] = None

class Product(BaseModel):
    product_id: str
    name: str
    description: str
    formats: List[Format]
    targeting_template: Targeting
    delivery_type: Literal["guaranteed", "non_guaranteed"]
    is_fixed_price: bool
    cpm: Optional[float] = None
    price_guidance: Optional[PriceGuidance] = None
    is_custom: bool = Field(default=False)
    expires_at: Optional[datetime] = None

# --- Admin Tool Schemas ---
class PrincipalSummary(BaseModel):
    principal_id: str
    name: str
    platform_mappings: Dict[str, Any]
    live_media_buys: int
    total_spend: float

class GetPrincipalSummaryResponse(BaseModel):
    principals: List[PrincipalSummary]

# --- Performance Index ---
class ProductPerformance(BaseModel):
    product_id: str
    performance_index: float  # 1.0 = baseline, 1.2 = 20% better, 0.8 = 20% worse
    confidence_score: Optional[float] = None  # 0.0 to 1.0

class UpdatePerformanceIndexRequest(BaseModel):
    media_buy_id: str
    performance_data: List[ProductPerformance]

class UpdatePerformanceIndexResponse(BaseModel):
    status: str
    detail: str

# --- Discovery ---
class ListProductsRequest(BaseModel):
    brief: str

class ListProductsResponse(BaseModel):
    products: List[Product]

# --- Creative Lifecycle ---
class Creative(BaseModel):
    creative_id: str
    format_id: str
    content_uri: str

class CreativeStatus(BaseModel):
    creative_id: str
    status: Literal["pending_review", "approved", "rejected", "adaptation_required"]
    detail: str
    estimated_approval_time: Optional[datetime] = None

class SubmitCreativesRequest(BaseModel):
    media_buy_id: str
    creatives: List[Creative]

class SubmitCreativesResponse(BaseModel):
    statuses: List[CreativeStatus]

class CheckCreativeStatusRequest(BaseModel):
    creative_ids: List[str]

class CheckCreativeStatusResponse(BaseModel):
    statuses: List[CreativeStatus]

class AdaptCreativeRequest(BaseModel):
    media_buy_id: str
    original_creative_id: str
    target_format_id: str
    new_creative_id: str
    instructions: Optional[str] = None

# --- Media Buy Lifecycle ---
class CreateMediaBuyRequest(BaseModel):
    product_ids: List[str]
    flight_start_date: date
    flight_end_date: date
    total_budget: float
    targeting_overlay: Targeting
    po_number: Optional[str] = None
    pacing: Literal["even", "asap", "daily_budget"] = "even"
    daily_budget: Optional[float] = None
    creatives: Optional[List[Creative]] = None

class CreateMediaBuyResponse(BaseModel):
    media_buy_id: str
    status: str
    detail: str

class UpdateMediaBuyRequest(BaseModel):
    media_buy_id: str
    new_total_budget: Optional[float] = None
    new_targeting_overlay: Optional[Targeting] = None
    creative_assignments: Optional[Dict[str, List[str]]] = None

class GetMediaBuyDeliveryRequest(BaseModel):
    media_buy_id: str
    today: date

class GetMediaBuyDeliveryResponse(BaseModel):
    media_buy_id: str
    status: str
    spend: float
    impressions: int
    pacing: str
    days_elapsed: int
    total_days: int
