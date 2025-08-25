#!/usr/bin/env python3
"""
Standard A2A client query script using python-a2a library.
This script demonstrates how to use the standard library with authentication.

Usage:
    python scripts/a2a_query.py <token> <message>

Example:
    python scripts/a2a_query.py test_token_1 "What products do you have?"
"""

import os
import sys

# Add parent directory to path so we can import from src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_a2a import A2AClient, create_text_message, pretty_print_message


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/a2a_query.py <token> <message>")
        print("Example: python scripts/a2a_query.py test_token_1 'What products do you have?'")
        sys.exit(1)

    token = sys.argv[1]
    message_text = " ".join(sys.argv[2:])

    # Build endpoint URL with token as query parameter
    # The A2AClient will append /tasks/send to this base URL
    base_url = f"http://localhost:8091?token={token}"

    # Create standard A2AClient from python-a2a library
    client = A2AClient(base_url)

    # Create message using library utilities
    message = create_text_message(message_text)

    print(f"Sending to AdCP Sales Agent: {message_text}")
    print("-" * 50)

    try:
        # Send message using standard library method
        response = client.send_message(message)

        # Pretty print using library utilities
        pretty_print_message(response)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
