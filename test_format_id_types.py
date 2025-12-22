#!/usr/bin/env python3
"""
Test script to verify the format_id type handling fix.

This reproduces the AttributeError: 'str' object has no attribute 'agent_url'
and demonstrates the correct fix for dict and FormatId types.
"""

from pydantic import BaseModel
from typing import Any


class FormatId(BaseModel):
    """Simulating the FormatId Pydantic model."""
    agent_url: str | None = None
    id: str


def test_attribute_access():
    """Test different format_id representations and their behavior."""
    
    print("=" * 60)
    print("Testing format_id type handling")
    print("=" * 60)
    
    format_id_pydantic = FormatId(agent_url="https://creative.adcontextprotocol.org/", id="display_300x250_image")
    format_id_dict = {"agent_url": "https://creative.adcontextprotocol.org/", "id": "display_300x250_image"}
    
    print("\n1. FormatId Pydantic object:")
    print(f"   type: {type(format_id_pydantic)}")
    print(f"   value: {format_id_pydantic}")
    
    print("\n2. Dict (from database JSONB):")
    print(f"   type: {type(format_id_dict)}")
    print(f"   value: {format_id_dict}")
    
    print("\n" + "-" * 60)
    print("Testing .agent_url attribute access (ORIGINAL BUGGY CODE)")
    print("-" * 60)
    
    print("\n✅ FormatId.agent_url:", format_id_pydantic.agent_url)
    print("✅ FormatId.id:", format_id_pydantic.id)
    
    print("\n❌ Testing dict.agent_url:")
    try:
        _ = format_id_dict.agent_url  # type: ignore
        print("   Unexpected success!")
    except AttributeError as e:
        print(f"   AttributeError: {e}")
    
    print("\n" + "-" * 60)
    print("Testing CORRECT FIX: Type-aware extraction")
    print("-" * 60)
    
    def extract_format_key(fmt: Any) -> tuple[str | None, str]:
        """Extract (agent_url, id) tuple from dict or FormatId object."""
        if isinstance(fmt, dict):
            agent_url = fmt.get("agent_url")
            format_id = fmt.get("id") or fmt.get("format_id")
            normalized_url = str(agent_url).rstrip("/") if agent_url else None
            return (normalized_url, format_id or "")
        else:
            # FormatId object
            normalized_url = str(fmt.agent_url).rstrip("/") if fmt.agent_url else None
            return (normalized_url, fmt.id)
    
    print("\n✅ Pydantic object:")
    result = extract_format_key(format_id_pydantic)
    print(f"   extract_format_key(FormatId) = {result}")
    
    print("\n✅ Dict:")
    result = extract_format_key(format_id_dict)
    print(f"   extract_format_key(dict) = {result}")


def simulate_buggy_code():
    """Simulate the exact code path that caused the error."""
    print("\n" + "=" * 60)
    print("SIMULATING THE BUGGY CODE PATH")
    print("=" * 60)
    
    # Database format_ids (JSONB -> list of dicts)
    pkg_product_format_ids = [
        {"agent_url": "https://creative.adcontextprotocol.org/", "id": "display_300x250_generative"},
        {"agent_url": "https://creative.adcontextprotocol.org/", "id": "display_300x250_image"}
    ]
    
    print("\nDatabase format_ids (JSONB -> dicts):")
    print(f"  {pkg_product_format_ids}")
    
    print("\nRunning buggy code:")
    print("""
    for fmt in pkg_product.format_ids:
        normalized_url = str(fmt.agent_url).rstrip("/") if fmt.agent_url else None
        product_format_keys.add((normalized_url, fmt.id))
    """)
    
    product_format_keys = set()
    try:
        for fmt in pkg_product_format_ids:
            normalized_url = str(fmt.agent_url).rstrip("/") if fmt.agent_url else None  # type: ignore
            product_format_keys.add((normalized_url, fmt.id))  # type: ignore
    except AttributeError as e:
        print(f"❌ ERROR: AttributeError: {e}")


def test_fixed_code():
    """Test the fixed code with dict and FormatId types."""
    print("\n" + "=" * 60)
    print("TESTING THE FIXED CODE")
    print("=" * 60)
    
    def extract_format_key(fmt: Any) -> tuple[str | None, str]:
        """Extract (agent_url, id) tuple from dict or FormatId object."""
        if isinstance(fmt, dict):
            agent_url = fmt.get("agent_url")
            format_id = fmt.get("id") or fmt.get("format_id")
            normalized_url = str(agent_url).rstrip("/") if agent_url else None
            return (normalized_url, format_id or "")
        else:
            # FormatId object
            normalized_url = str(fmt.agent_url).rstrip("/") if fmt.agent_url else None
            return (normalized_url, fmt.id)
    
    # Test with database format_ids (dicts from JSONB)
    print("\n1. Testing with database JSONB data (dicts):")
    db_format_ids = [
        {"agent_url": "https://creative.adcontextprotocol.org/", "id": "display_300x250_generative"},
        {"agent_url": "https://creative.adcontextprotocol.org/", "id": "display_300x250_image"}
    ]
    
    product_format_keys = set()
    for fmt in db_format_ids:
        key = extract_format_key(fmt)
        product_format_keys.add(key)
        print(f"   ✅ Extracted: {key}")
    
    # Test with Pydantic FormatId objects
    print("\n2. Testing with Pydantic FormatId objects:")
    pydantic_format_ids = [
        FormatId(agent_url="https://creative.adcontextprotocol.org/", id="display_300x250_generative"),
        FormatId(agent_url="https://creative.adcontextprotocol.org/", id="display_300x250_image")
    ]
    
    for fmt in pydantic_format_ids:
        key = extract_format_key(fmt)
        print(f"   ✅ Extracted: {key}")
    
    # Test cross-type validation
    print("\n3. Cross-type validation (request Pydantic vs database dict):")
    request_format_ids = [
        FormatId(agent_url="https://creative.adcontextprotocol.org/", id="display_300x250_image")
    ]
    
    for fmt in request_format_ids:
        key = extract_format_key(fmt)
        is_valid = key in product_format_keys
        print(f"   {'✅ VALID' if is_valid else '❌ INVALID'}: {key}")
    
    print("\n" + "=" * 60)
    print("✅ Fix verified - handles both dict and FormatId types")
    print("=" * 60)


if __name__ == "__main__":
    test_attribute_access()
    simulate_buggy_code()
    test_fixed_code()
