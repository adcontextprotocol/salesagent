"""Configuration loader with environment variable support."""

import os
import json
from typing import Dict, Any

def load_config() -> Dict[str, Any]:
    """
    Load configuration from config.json with environment variable overrides.
    
    Environment variables:
    - GEMINI_API_KEY: Overrides gemini_api_key
    - AD_SERVER_ADAPTER: Overrides ad_server.adapter (gam, triton_digital, kevel, mock)
    - AD_SERVER_BASE_URL: Overrides ad_server.base_url
    - AD_SERVER_AUTH_TOKEN: Overrides ad_server.auth_token (for Triton)
    - GAM_SERVICE_ACCOUNT_JSON: Google Ad Manager service account credentials (JSON string)
    - GAM_NETWORK_CODE: Google Ad Manager network code
    - CREATIVE_ENGINE_ADAPTER: Overrides creative_engine.adapter
    - CREATIVE_ENGINE_HUMAN_REVIEW: Overrides creative_engine.human_review_required
    """
    # Load base config
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        # If no config.json, start with sample
        try:
            with open('config.json.sample', 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            # Start with empty config if no sample exists
            config = {
                'ad_server': {},
                'creative_engine': {}
            }
    
    # Override with environment variables
    if gemini_key := os.environ.get('GEMINI_API_KEY'):
        config['gemini_api_key'] = gemini_key
    
    # Ad server overrides
    if 'ad_server' not in config:
        config['ad_server'] = {}
    
    if ad_server_adapter := os.environ.get('AD_SERVER_ADAPTER'):
        config['ad_server']['adapter'] = ad_server_adapter
    
    if ad_server_url := os.environ.get('AD_SERVER_BASE_URL'):
        config['ad_server']['base_url'] = ad_server_url
    
    if ad_server_token := os.environ.get('AD_SERVER_AUTH_TOKEN'):
        config['ad_server']['auth_token'] = ad_server_token
    
    # GAM-specific configuration
    if gam_service_account := os.environ.get('GAM_SERVICE_ACCOUNT_JSON'):
        if 'gam' not in config:
            config['gam'] = {}
        # Parse JSON and save to a temp file or keep in memory
        config['gam']['service_account_json'] = gam_service_account
    
    if gam_network_code := os.environ.get('GAM_NETWORK_CODE'):
        if 'gam' not in config:
            config['gam'] = {}
        config['gam']['network_code'] = gam_network_code
    
    # Creative engine overrides
    if 'creative_engine' not in config:
        config['creative_engine'] = {}
    
    if creative_adapter := os.environ.get('CREATIVE_ENGINE_ADAPTER'):
        config['creative_engine']['adapter'] = creative_adapter
    
    if human_review := os.environ.get('CREATIVE_ENGINE_HUMAN_REVIEW'):
        config['creative_engine']['human_review_required'] = human_review.lower() == 'true'
    
    return config

def get_secret(key: str, default: str = None) -> str:
    """Get a secret from environment or config."""
    return os.environ.get(key, default)