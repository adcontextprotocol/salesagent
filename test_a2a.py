# \!/usr/bin/env python3
"""Demo: Using standard python-a2a library with our server."""

from python_a2a.client import A2AClient

# Create client using python-a2a library
client = A2AClient(endpoint_url="http://localhost:8091")

print("Testing python-a2a client...")
response = client.send_task("What advertising products are available?")
print(f"Task ID: {response.get('id')}")
print(f"Status: {response.get('status', {}).get('state')}")
print("\nSuccess\\! The standard python-a2a library works with our server.")
