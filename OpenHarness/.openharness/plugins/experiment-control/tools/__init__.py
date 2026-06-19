"""Experiment control tools — shared HTTP client and configuration."""
import os
import aiohttp

BASE_URL = os.environ.get("JF_CONTROL_API_URL", "http://localhost:8000")

_session: aiohttp.ClientSession | None = None


def get_session() -> aiohttp.ClientSession:
    """Return or create a shared aiohttp session."""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def close_session():
    """Close the shared session (call on plugin teardown)."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None
