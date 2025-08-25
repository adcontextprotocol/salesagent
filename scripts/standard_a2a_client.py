#!/usr/bin/env python3
"""
Demonstration of using the STANDARD python-a2a library with authentication.
No custom code - just standard library usage with environment variables.

Usage:
    export A2A_AUTH_TOKEN=test_token_1
    python scripts/standard_a2a_client.py "What products do you have?"
"""

import os
import sys

# This is the STANDARD python-a2a library - no modifications
from python_a2a import A2AClient, create_text_message, pretty_print_message


def main():
    # Check for auth token in environment
    if not os.environ.get("A2A_AUTH_TOKEN"):
        print("Error: A2A_AUTH_TOKEN environment variable not set")
        print("Usage:")
        print("  export A2A_AUTH_TOKEN=test_token_1")
        print("  python scripts/standard_a2a_client.py 'Your message'")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python scripts/standard_a2a_client.py 'Your message'")
        sys.exit(1)

    message_text = " ".join(sys.argv[1:])

    # Standard A2AClient from python-a2a library - NO MODIFICATIONS
    client = A2AClient("http://localhost:8091")

    # Create message using standard library utilities
    message = create_text_message(message_text)

    print(f"Query: {message_text}")
    print("-" * 50)

    try:
        # Send message using standard library method
        response = client.send_message(message)

        # Pretty print using standard library utilities
        pretty_print_message(response)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
