"""
Broadsign Implementation Config Schema

Defines the structure of implementation_config for Broadsign products.
Covers DOOH-specific settings like screen networks, venue targeting, and buying modes.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class FrequencySettings(BaseModel):
    """Settings for frequency-based buying mode."""

    plays_per_hour: int = Field(4, description="Number of times ad plays per hour", ge=1, le=60)
    min_spot_length_seconds: int = Field(15, description="Minimum spot duration", ge=5, le=120)
    max_spot_length_seconds: int = Field(30, description="Maximum spot duration", ge=5, le=120)


class ShareOfVoiceSettings(BaseModel):
    """Settings for share-of-voice buying mode."""

    min_sov_percentage: float = Field(10.0, description="Minimum share of voice", ge=1.0, le=100.0)
    max_sov_percentage: float = Field(100.0, description="Maximum share of voice", ge=1.0, le=100.0)


class CreativeSpecification(BaseModel):
    """Creative format specifications for DOOH."""

    resolution: str = Field(..., description="Screen resolution (e.g., '1920x1080')")
    aspect_ratio: str = Field(..., description="Aspect ratio (e.g., '16:9', '9:16')")
    orientation: Literal["landscape", "portrait", "square"] = Field("landscape", description="Screen orientation")


class BroadsignImplementationConfig(BaseModel):
    """
    Complete configuration for creating Broadsign campaigns.
    This config is stored in the products table implementation_config field.
    """

    # Campaign Settings
    campaign_name_template: str = Field(
        "{promoted_offering} - {date_range}",
        description="Template for campaign names. Variables: {promoted_offering}, {date_range}, {po_number}, {principal_name}",
    )

    default_hold_duration_hours: int = Field(
        48, description="How long to hold inventory before requiring booking", ge=1, le=168
    )

    auto_book_on_availability: bool = Field(
        False, description="Automatically book campaigns when inventory is available"
    )

    # Screen Network Configuration
    default_screen_networks: list[str] = Field(
        default_factory=list, description="Default screen network IDs to target (e.g., ['network_transit'])"
    )

    preferred_venue_categories: list[int] = Field(
        default_factory=list, description="Broadsign category IDs for preferred venues"
    )

    excluded_screen_ids: list[str] = Field(default_factory=list, description="Specific screens to always exclude")

    min_screens_per_campaign: int = Field(
        10, description="Minimum number of screens required for a campaign", ge=1, le=10000
    )

    max_screens_per_campaign: int = Field(1000, description="Maximum number of screens per campaign", ge=1, le=10000)

    # Geographic Preferences
    preferred_geos: list[dict[str, str]] = Field(
        default_factory=list,
        description="Preferred geographic markets. Format: [{'type': 'city', 'code': 'NYC'}, ...]",
    )

    # Buying Strategy
    default_buying_mode: Literal["frequency", "share_of_voice", "impressions"] = Field(
        "frequency", description="Default buying mode for campaigns"
    )

    frequency_settings: FrequencySettings = Field(
        default_factory=FrequencySettings, description="Settings for frequency-based campaigns"
    )

    share_of_voice_settings: ShareOfVoiceSettings = Field(
        default_factory=ShareOfVoiceSettings, description="Settings for share-of-voice campaigns"
    )

    # Creative Requirements
    supported_creative_specs: list[CreativeSpecification] = Field(
        default_factory=lambda: [
            CreativeSpecification(resolution="1920x1080", aspect_ratio="16:9", orientation="landscape"),
            CreativeSpecification(resolution="1080x1920", aspect_ratio="9:16", orientation="portrait"),
        ],
        description="Supported creative specifications",
    )

    default_spot_duration_seconds: int = Field(15, description="Default creative duration in seconds", ge=5, le=120)

    require_proof_of_play: bool = Field(True, description="Require proof-of-play verification for billing")

    # Inventory Management
    auto_sync_screens: bool = Field(True, description="Automatically sync available screens from Broadsign")

    sync_interval_hours: int = Field(24, description="How often to refresh screen availability data", ge=1, le=168)

    cache_venue_data: bool = Field(True, description="Cache venue metadata for faster campaign creation")

    # Targeting Preferences
    enable_dayparting: bool = Field(
        False, description="Allow time-of-day targeting (premium feature in some Broadsign accounts)"
    )

    enable_weather_targeting: bool = Field(
        False, description="Enable weather-based targeting (if available in Broadsign account)"
    )

    # Reporting & Attribution
    use_traffic_estimation: bool = Field(True, description="Use foot traffic estimation for impression calculations")

    attribution_model: Literal["audience_based", "loop_based", "time_based"] = Field(
        "audience_based",
        description="How to calculate impressions from screen plays. "
        "audience_based=multiply by venue traffic, loop_based=count plays, time_based=calculate from duration",
    )

    proof_of_play_webhook_url: str | None = Field(
        None, description="Webhook URL for real-time proof-of-play notifications"
    )

    # Advanced Settings
    allow_screen_overbook: bool = Field(
        False, description="Allow overbooking of screen inventory (risk of non-delivery)"
    )

    priority_level: int = Field(5, description="Campaign priority (1=highest, 10=lowest)", ge=1, le=10)

    require_manual_approval: bool = Field(False, description="Require human approval before booking campaigns")

    # Notes and metadata
    internal_notes: str = Field("", description="Internal notes about this product configuration")

    @field_validator("default_buying_mode")
    def validate_buying_mode(cls, v):
        valid_modes = {"frequency", "share_of_voice", "impressions"}
        if v not in valid_modes:
            raise ValueError(f"Invalid buying mode. Must be one of: {valid_modes}")
        return v

    @field_validator("attribution_model")
    def validate_attribution_model(cls, v):
        valid_models = {"audience_based", "loop_based", "time_based"}
        if v not in valid_models:
            raise ValueError(f"Invalid attribution model. Must be one of: {valid_models}")
        return v

    @field_validator("max_screens_per_campaign")
    def validate_screen_limits(cls, v, info):
        min_screens = info.data.get("min_screens_per_campaign", 1)
        if v < min_screens:
            raise ValueError(f"max_screens_per_campaign must be >= min_screens_per_campaign ({min_screens})")
        return v


# Example configuration for a transit DOOH product
EXAMPLE_TRANSIT_CONFIG = {
    "campaign_name_template": "{promoted_offering} - Transit Campaign",
    "default_buying_mode": "frequency",
    "frequency_settings": {"plays_per_hour": 6, "min_spot_length_seconds": 15, "max_spot_length_seconds": 30},
    "preferred_venue_categories": [7, 8],  # Transit venues
    "min_screens_per_campaign": 20,
    "supported_creative_specs": [
        {"resolution": "1920x1080", "aspect_ratio": "16:9", "orientation": "landscape"},
    ],
    "default_spot_duration_seconds": 15,
    "use_traffic_estimation": True,
    "attribution_model": "audience_based",
    "require_proof_of_play": True,
}

# Example configuration for a retail DOOH product
EXAMPLE_RETAIL_CONFIG = {
    "campaign_name_template": "{promoted_offering} - Retail Network",
    "default_buying_mode": "share_of_voice",
    "share_of_voice_settings": {"min_sov_percentage": 15.0, "max_sov_percentage": 50.0},
    "preferred_venue_categories": [11, 12],  # Shopping malls, retail
    "min_screens_per_campaign": 50,
    "max_screens_per_campaign": 500,
    "supported_creative_specs": [
        {"resolution": "1920x1080", "aspect_ratio": "16:9", "orientation": "landscape"},
        {"resolution": "1080x1920", "aspect_ratio": "9:16", "orientation": "portrait"},
    ],
    "default_spot_duration_seconds": 30,
    "enable_dayparting": True,
    "attribution_model": "loop_based",
}
