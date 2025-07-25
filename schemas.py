from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, date

# --- V2.3 Pydantic Models (Restored & Complete with Descriptions) ---

# --- Core Creative & Product Models ---

class DeliveryOptions(BaseModel):
    """Describes how a creative can be delivered."""
    hosted: Optional[Dict[str, Any]] = Field(None, description="Publisher-hosted creative assets.")
    vast: Optional[Dict[str, Any]] = Field(None, description="VAST XML-based delivery.")

class Format(BaseModel):
    """A detailed, structured model for creative formats."""
    format_id: str = Field(..., description="The unique identifier for the format, e.g., 'video_standard_1080p'.")
    name: str = Field(..., description="A human-readable name for the format.")
    type: Literal["video", "audio", "display", "native", "dooh"] = Field(..., description="The general category of the format.")
    description: str = Field(..., description="A brief description of the format.")
    specs: Dict[str, Any] = Field(..., description="A dictionary of technical specifications, e.g., resolution, duration.")
    delivery_options: DeliveryOptions = Field(..., description="The supported delivery methods for this format.")

class Targeting(BaseModel):
    """A unified and expressive targeting model."""
    geography: Optional[List[str]] = Field(None, description="List of targeted geographies (e.g., ['USA', 'UK-London']).")
    exclude_geography: Optional[List[str]] = Field(None, description="List of excluded geographies.")
    day_parts: Optional[List[str]] = Field(None, description="Human-readable strings for dayparting (e.g., ['weekdays-daytime']).")
    technology: Optional[List[str]] = Field(None, description="Technology-based targeting (e.g., ['device-mobile']).")
    content_categories_include: Optional[List[str]] = Field(None, description="List of content categories to target (e.g., ['news', 'sports']).")
    content_categories_exclude: Optional[List[str]] = Field(None, description="List of content categories to avoid.")

class PriceGuidance(BaseModel):
    """Guidance for non-fixed price, auction-based products."""
    floor: float = Field(..., description="The minimum bid required to be considered in the auction.")
    p25: Optional[float] = Field(None, description="The 25th percentile winning bid for this inventory.")
    p50: Optional[float] = Field(None, description="The median (50th percentile) winning bid.")
    p75: Optional[float] = Field(None, description="The 75th percentile winning bid.")
    p90: Optional[float] = Field(None, description="The 90th percentile winning bid.")

class Product(BaseModel):
    """Represents a sellable unit of inventory."""
    product_id: str = Field(..., description="The unique identifier for this product.")
    name: str = Field(..., description="A human-readable name for the product.")
    description: str = Field(..., description="A detailed description of the product.")
    formats: List[Format] = Field(..., description="A list of creative formats supported by this product.")
    targeting_template: Targeting = Field(..., description="The base targeting profile for this product.")
    delivery_type: Literal["guaranteed", "non_guaranteed"] = Field(..., description="The delivery commitment.")
    is_fixed_price: bool = Field(..., description="True if the price is fixed, False if auction-based.")
    cpm: Optional[float] = Field(None, description="The fixed Cost Per Mille. Required if is_fixed_price is True.")
    price_guidance: Optional[PriceGuidance] = Field(None, description="Pricing guidance for auction-based products. Required if is_fixed_price is False.")
    is_custom: bool = Field(default=False, description="Indicates if the product was custom-generated for a brief.")
    expires_at: Optional[datetime] = Field(None, description="If custom, the time at which this product is no longer valid.")

    @model_validator(mode='after')
    def check_pricing_model(self) -> 'Product':
        if self.is_fixed_price and self.cpm is None:
            raise ValueError("cpm is required for fixed-price products.")
        if not self.is_fixed_price and self.price_guidance is None:
            raise ValueError("price_guidance is required for non-fixed-price products.")
        return self

# --- Discovery ---
class ListProductsRequest(BaseModel):
    brief: str = Field(..., description="A natural language description of the campaign goals.")
    principal_id: Optional[str] = Field(None, description="An identifier for the client, allowing for principal-specific products.")

class ListProductsResponse(BaseModel):
    products: List[Product]

# --- Creative Lifecycle ---
class Creative(BaseModel):
    creative_id: str = Field(..., description="A user-defined ID for this creative.")
    format_id: str = Field(..., description="The ID of the format this creative adheres to.")
    content_uri: str = Field(..., description="URI to the creative asset (e.g., VAST XML, image URL).")

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
    po_number: Optional[str] = Field(None, description="Optional purchase order number for billing.")
    pacing: Literal["even", "asap", "daily_budget"] = Field("even", description="The pacing strategy for the budget.")
    daily_budget: Optional[float] = Field(None, description="Required if pacing is 'daily_budget'.")
    creatives: Optional[List[Creative]] = Field(None, description="Optional list of creatives to submit immediately.")

    @model_validator(mode='after')
    def check_pacing(self) -> 'CreateMediaBuyRequest':
        if self.pacing == "daily_budget" and self.daily_budget is None:
            raise ValueError("daily_budget is required when pacing is 'daily_budget'.")
        return self

class CreateMediaBuyResponse(BaseModel):
    media_buy_id: str
    status: str
    detail: str

class UpdateMediaBuyRequest(BaseModel):
    media_buy_id: str
    new_total_budget: Optional[float] = None
    new_targeting_overlay: Optional[Targeting] = None
    creative_assignments: Optional[Dict[str, List[str]]] = Field(None, description="Assigns creatives to products.")

class GetMediaBuyDeliveryResponse(BaseModel):
    media_buy_id: str
    status: str
    spend: float
    impressions: int
    pacing: str
    days_elapsed: int
    total_days: int
