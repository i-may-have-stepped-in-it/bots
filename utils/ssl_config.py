"""
SSL/TLS configuration manager for local vs remote services.
Automatically disables SSL verification for local/private networks.
"""

import logging
import os
import ssl
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSLConfigManager:
    """
    Manages SSL verification based on endpoint type.

    Local/private network services (LocalAI, SD) don't use SSL.
    Public cloud services (OpenAI) require SSL verification.
    """

    # Local hostnames that never need SSL
    LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}

    # Private IP ranges (RFC 1918)
    PRIVATE_PREFIXES = (
        '192.168.', '10.', '172.16.', '172.17.', '172.18.',
        '172.19.', '172.20.', '172.21.', '172.22.', '172.23.',
        '172.24.', '172.25.', '172.26.', '172.27.', '172.28.',
        '172.29.', '172.30.', '172.31.'
    )

    # Common Tailscale/Tailnet domains
    TAILSCALE_DOMAINS = ('.tailscale.net', '.ts.net', '.tail')

    @classmethod
    def should_verify_ssl(cls, url: str) -> bool:
        """
        Determine if SSL verification should be enabled for URL.

        Args:
            url: The endpoint URL

        Returns:
            True if SSL should be verified, False otherwise
        """
        if not url:
            return False

        # Check for override environment variable
        override = os.getenv('VERIFY_SSL', '').lower()
        if override == 'always':
            logger.debug("SSL verification forced ON by VERIFY_SSL=always")
            return True
        if override == 'never':
            logger.debug("SSL verification forced OFF by VERIFY_SSL=never")
            return False

        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        scheme = parsed.scheme or 'http'

        # HTTP connections don't use SSL
        if scheme == 'http':
            logger.debug(f"SSL disabled for HTTP endpoint: {url}")
            return False

        # HTTPS connections - check if private
        if cls._is_private_host(hostname):
            logger.debug(f"SSL disabled for private HTTPS endpoint: {url}")
            return False

        # Public HTTPS - verify SSL
        logger.debug(f"SSL enabled for public HTTPS endpoint: {url}")
        return True

    @classmethod
    def _is_private_host(cls, hostname: str) -> bool:
        """Check if hostname is a local/private address."""
        if not hostname:
            return True

        hostname_lower = hostname.lower()

        # Check local hosts
        if hostname_lower in cls.LOCAL_HOSTS:
            return True

        # Check private IP prefixes
        if hostname_lower.startswith(cls.PRIVATE_PREFIXES):
            return True

        # Check Tailscale domains
        if any(domain in hostname_lower for domain in cls.TAILSCALE_DOMAINS):
            return True

        return False

    @classmethod
    def get_ssl_context(cls, url: str) -> ssl.SSLContext | bool:
        """
        Get appropriate SSL context for URL.

        Args:
            url: The endpoint URL

        Returns:
            SSLContext for verification, or False to disable verification
        """
        if cls.should_verify_ssl(url):
            return ssl.create_default_context()
        return False

    @classmethod
    def get_aiohttp_ssl_param(cls, url: str):
        """
        Get the ssl parameter for aiohttp requests.

        Usage:
            ssl_param = SSLConfigManager.get_aiohttp_ssl_param("https://api.example.com")
            async with session.get(url, ssl=ssl_param) as resp:
                ...
        """
        return cls.get_ssl_context(url)


# Convenience function for quick access
def get_ssl_for_url(url: str):
    """Get SSL context/parameter for a URL."""
    return SSLConfigManager.get_aiohttp_ssl_param(url)
