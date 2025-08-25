#!/usr/bin/env python3
"""Test script to see what python-a2a expects from the server."""

import json

import httpx

# Test the REST endpoint directly
url = "http://localhost:8091/tasks/send"
payload = {"text": "What advertising products are available?", "context": {}}

print(f"Testing REST endpoint: {url}")
print(f"Payload: {json.dumps(payload, indent=2)}")

response = httpx.post(url, json=payload)
print(f"\nStatus: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

# Also test with the format the a2a CLI might be using
if response.status_code != 200:
    print("\n\nTrying alternative format...")
    alt_payload = {"message": "What advertising products are available?"}
    response = httpx.post(url, json=alt_payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
