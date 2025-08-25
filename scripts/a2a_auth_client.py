#!/usr/bin/env python3
"""
Authenticated A2A client for sending messages to the AdCP A2A server.

This script wraps the python-a2a client to add authentication support
since the standard a2a CLI doesn't support custom headers.

Usage:
    python scripts/a2a_auth_client.py <endpoint> <message> --token <auth_token>

Example:
    python scripts/a2a_auth_client.py http://localhost:8091/a2a "list products" --token demo_token_123
    python scripts/a2a_auth_client.py https://adcp-sales-agent.fly.dev/a2a "get pricing" --token prod_token_456
"""

import argparse
import json
import sys

import requests


def send_authenticated_message(endpoint: str, message: str, token: str) -> dict:
    """
    Send an authenticated message to an A2A server.

    Args:
        endpoint: The A2A server endpoint URL
        message: The message text to send
        token: The authentication token

    Returns:
        The server's response as a dictionary
    """
    # Create a simple A2A message structure
    message_data = {"content": {"text": message}, "role": "user"}

    # Set up headers with authentication
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Auth-Token": token,  # Also send in custom header for compatibility
    }

    # Send the request
    # Note: The A2A server uses /tasks/send relative to its base URL
    # So if endpoint is http://localhost:8091/a2a, we use http://localhost:8091/a2a/tasks/send
    # But if endpoint is http://localhost:8091, we use http://localhost:8091/tasks/send
    endpoint_url = f"{endpoint.rstrip('/')}/tasks/send"

    try:
        response = requests.post(endpoint_url, json=message_data, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("Authentication failed. Please check your token.", file=sys.stderr)
            print(f"Response: {e.response.text}", file=sys.stderr)
        elif e.response.status_code == 404:
            print(f"Endpoint not found: {endpoint_url}", file=sys.stderr)
            print("Make sure the A2A server is running and the URL is correct.", file=sys.stderr)
        else:
            print(f"HTTP Error {e.response.status_code}: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"Failed to connect to {endpoint}", file=sys.stderr)
        print("Make sure the A2A server is running and accessible.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {str(e)}", file=sys.stderr)
        sys.exit(1)


def pretty_print_response(response: dict):
    """
    Pretty print an A2A response.

    Args:
        response: The response dictionary from the server
    """
    # Extract the content from the response
    if isinstance(response, dict):
        if "content" in response:
            content = response["content"]
            if isinstance(content, dict) and "text" in content:
                print(f"\n🤖 Agent Response:\n{content['text']}")
            else:
                print(f"\n🤖 Agent Response:\n{json.dumps(content, indent=2)}")
        else:
            print(f"\n🤖 Agent Response:\n{json.dumps(response, indent=2)}")
    else:
        print(f"\n🤖 Agent Response:\n{response}")


def main():
    parser = argparse.ArgumentParser(description="Send authenticated messages to an A2A server")
    parser.add_argument("endpoint", help="A2A server endpoint URL (e.g., http://localhost:8091/a2a)")
    parser.add_argument("message", help="Message text to send")
    parser.add_argument("--token", required=True, help="Authentication token")
    parser.add_argument("--json", action="store_true", help="Output raw JSON response")

    args = parser.parse_args()

    # Send the authenticated message
    print(f"📤 Sending message to {args.endpoint} with authentication...")
    response = send_authenticated_message(args.endpoint, args.message, args.token)

    # Print the response
    if args.json:
        print(json.dumps(response, indent=2))
    else:
        pretty_print_response(response)


if __name__ == "__main__":
    main()
