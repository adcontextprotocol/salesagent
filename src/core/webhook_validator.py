"""Webhook URL validation to prevent SSRF attacks.

This module provides security validation for webhook URLs to prevent
Server-Side Request Forgery (SSRF) attacks where malicious users could
trick the server into making requests to internal services.
"""

import ipaddress
import socket
from urllib.parse import urlparse


class WebhookURLValidator:
    """Validates webhook URLs to prevent SSRF attacks."""

    # Blocked IP ranges (RFC 1918 private networks, loopback, link-local)
    BLOCKED_NETWORKS = [
        ipaddress.ip_network("10.0.0.0/8"),  # Private network
        ipaddress.ip_network("172.16.0.0/12"),  # Private network
        ipaddress.ip_network("192.168.0.0/16"),  # Private network
        ipaddress.ip_network("127.0.0.0/8"),  # Loopback
        ipaddress.ip_network("169.254.0.0/16"),  # Link-local (AWS metadata service)
        ipaddress.ip_network("::1/128"),  # IPv6 loopback
        ipaddress.ip_network("fc00::/7"),  # IPv6 private
        ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ]

    # Blocked hostnames (cloud metadata services, localhost aliases)
    BLOCKED_HOSTNAMES = {
        "localhost",
        "metadata.google.internal",  # GCP metadata
        "169.254.169.254",  # AWS metadata IP
        "metadata",
        "instance-data",
    }

    @classmethod
    def validate_webhook_url(cls, url: str) -> tuple[bool, str]:
        """
        Validate webhook URL for SSRF protection.

        Args:
            url: The webhook URL to validate

        Returns:
            (is_valid, error_message) - is_valid is True if safe, error_message explains failures
        """
        try:
            parsed = urlparse(url)

            # Must be HTTP or HTTPS
            if parsed.scheme not in ("http", "https"):
                return False, "Webhook URL must use http or https protocol"

            # Must have a hostname
            if not parsed.hostname:
                return False, "Webhook URL must have a valid hostname"

            # Check against blocked hostnames
            if parsed.hostname.lower() in cls.BLOCKED_HOSTNAMES:
                return False, f"Webhook URL hostname '{parsed.hostname}' is blocked for security reasons"

            # Resolve hostname to IP address
            try:
                ip_str = socket.gethostbyname(parsed.hostname)
                ip = ipaddress.ip_address(ip_str)
            except socket.gaierror:
                return False, f"Cannot resolve hostname: {parsed.hostname}"
            except ValueError as e:
                return False, f"Invalid IP address from hostname resolution: {e}"

            # Check against blocked IP ranges
            for network in cls.BLOCKED_NETWORKS:
                if ip in network:
                    return (
                        False,
                        f"Webhook URL resolves to blocked IP range {network} (private/internal network)",
                    )

            # Prevent localhost even if resolved to public IP somehow
            if ip.is_loopback or ip.is_link_local or ip.is_private:
                return False, f"Webhook URL resolves to private/internal IP address: {ip}"

            return True, ""

        except Exception as e:
            return False, f"Invalid webhook URL: {e}"

    @classmethod
    def validate_for_testing(cls, url: str, allow_localhost: bool = False) -> tuple[bool, str]:
        """
        Validate webhook URL with optional localhost allowance for testing.

        This is useful for development/testing scenarios where webhooks need to
        point to localhost services. Production should use validate_webhook_url().

        Args:
            url: The webhook URL to validate
            allow_localhost: If True, allows localhost and 127.0.0.1

        Returns:
            (is_valid, error_message)
        """
        is_valid, error = cls.validate_webhook_url(url)

        # If validation failed but it's a localhost error and we allow it
        if not is_valid and allow_localhost:
            if "localhost" in error.lower() or "127.0.0" in error or "loopback" in error.lower():
                return True, ""

        return is_valid, error
