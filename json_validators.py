"""
JSON field validators for database models.

This module provides Pydantic models and SQLAlchemy validators
to ensure JSON fields contain valid, properly structured data.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import validates
import json


# Pydantic models for JSON field validation

class CommentModel(BaseModel):
    """Model for a single comment in workflow_steps.comments."""
    user: str = Field(..., min_length=1, description="User who made the comment")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    text: str = Field(..., min_length=1, description="Comment text")
    
    @field_validator('user', 'text')
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class PlatformMappingModel(BaseModel):
    """Model for principal.platform_mappings."""
    google_ad_manager: Optional[Dict[str, Any]] = None
    kevel: Optional[Dict[str, Any]] = None
    mock: Optional[Dict[str, Any]] = None
    
    @model_validator(mode='after')
    def at_least_one_platform(self):
        if not any([self.google_ad_manager, self.kevel, self.mock]):
            raise ValueError("At least one platform mapping is required")
        return self


class CreativeFormatModel(BaseModel):
    """Model for product.formats array items."""
    format_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    type: str = Field(..., pattern="^(display|video|audio|native)$")
    description: str = Field(..., min_length=1)
    width: Optional[int] = Field(None, gt=0)
    height: Optional[int] = Field(None, gt=0)
    duration: Optional[int] = Field(None, gt=0)
    assets: List[Dict[str, Any]] = Field(default_factory=list)
    delivery_options: Dict[str, Any] = Field(default_factory=dict)


class TargetingTemplateModel(BaseModel):
    """Model for product.targeting_template."""
    geo_targets: Optional[List[str]] = None
    device_targets: Optional[List[str]] = None
    audience_segments: Optional[List[str]] = None
    content_categories: Optional[List[str]] = None
    custom_parameters: Optional[Dict[str, Any]] = None


class PolicySettingsModel(BaseModel):
    """Model for tenant.policy_settings."""
    enabled: bool = Field(default=False)
    require_approval: bool = Field(default=False)
    max_daily_budget: Optional[float] = Field(None, gt=0)
    blocked_categories: List[str] = Field(default_factory=list)
    allowed_advertisers: List[str] = Field(default_factory=list)
    custom_rules: Dict[str, Any] = Field(default_factory=dict)


class DeliveryDataModel(BaseModel):
    """Model for gam_line_items.delivery_data."""
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    ctr: float = Field(default=0.0, ge=0.0, le=100.0)
    spend: float = Field(default=0.0, ge=0.0)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# SQLAlchemy validator mixins

class JSONValidatorMixin:
    """Mixin to add JSON validation to SQLAlchemy models."""
    
    @validates('authorized_emails', 'authorized_domains', 'auto_approve_formats')
    def validate_json_array_fields(self, key, value):
        """Validate that these fields are JSON arrays."""
        return ensure_json_array(value, default=[])
    
    @validates('comments')
    def validate_comments(self, key, value):
        """Validate comments field is a list of proper comment objects."""
        if value is None:
            return []
        
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"{key} must be valid JSON")
        
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list")
        
        validated_comments = []
        for comment in value:
            if isinstance(comment, dict):
                # Validate and normalize using Pydantic
                validated = CommentModel(**comment)
                validated_comments.append(validated.model_dump(mode='json'))
            else:
                raise ValueError(f"Each comment must be a dictionary")
        
        return validated_comments
    
    @validates('platform_mappings')
    def validate_platform_mappings(self, key, value):
        """Validate platform_mappings contains at least one platform."""
        if value is None:
            raise ValueError(f"{key} cannot be None")
        
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"{key} must be valid JSON")
        
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be a dictionary")
        
        # Validate using Pydantic
        validated = PlatformMappingModel(**value)
        return validated.model_dump(mode='json', exclude_none=True)
    
    @validates('formats')
    def validate_formats(self, key, value):
        """Validate formats field is a list of proper format objects."""
        if value is None:
            return []
        
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"{key} must be valid JSON")
        
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list")
        
        validated_formats = []
        for fmt in value:
            if isinstance(fmt, dict):
                # Validate and normalize using Pydantic
                validated = CreativeFormatModel(**fmt)
                validated_formats.append(validated.model_dump(mode='json'))
            else:
                raise ValueError(f"Each format must be a dictionary")
        
        return validated_formats
    
    @validates('targeting_template')
    def validate_targeting_template(self, key, value):
        """Validate targeting_template field structure."""
        if value is None:
            return {}
        
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"{key} must be valid JSON")
        
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be a dictionary")
        
        # Validate using Pydantic
        validated = TargetingTemplateModel(**value)
        return validated.model_dump(mode='json', exclude_none=True)
    
    @validates('policy_settings')
    def validate_policy_settings(self, key, value):
        """Validate policy_settings field structure."""
        if value is None:
            return {}
        
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"{key} must be valid JSON")
        
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be a dictionary")
        
        # Validate using Pydantic
        validated = PolicySettingsModel(**value)
        return validated.model_dump(mode='json')
    
    @validates('delivery_data')
    def validate_delivery_data(self, key, value):
        """Validate delivery_data field structure."""
        if value is None:
            return None
        
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"{key} must be valid JSON")
        
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be a dictionary")
        
        # Validate using Pydantic
        validated = DeliveryDataModel(**value)
        return validated.model_dump(mode='json')


# Utility functions for JSON handling

def ensure_json_array(value: Union[str, list, None], default: list = None) -> list:
    """
    Ensure a value is a JSON array (list).
    
    Args:
        value: The value to check/convert
        default: Default value if input is None
    
    Returns:
        A list
    """
    if value is None:
        return default or []
    
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON string")
    
    if not isinstance(value, list):
        raise ValueError("Value must be a list")
    
    return value


def ensure_json_object(value: Union[str, dict, None], default: dict = None) -> dict:
    """
    Ensure a value is a JSON object (dict).
    
    Args:
        value: The value to check/convert
        default: Default value if input is None
    
    Returns:
        A dictionary
    """
    if value is None:
        return default or {}
    
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON string")
    
    if not isinstance(value, dict):
        raise ValueError("Value must be a dictionary")
    
    return value


def validate_json_schema(value: Any, schema: type[BaseModel]) -> dict:
    """
    Validate a value against a Pydantic schema.
    
    Args:
        value: The value to validate
        schema: The Pydantic model class to validate against
    
    Returns:
        The validated and normalized dictionary
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON string")
    
    validated = schema(**value)
    return validated.model_dump(mode='json')