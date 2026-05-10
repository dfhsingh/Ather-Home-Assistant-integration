"""Helper functions for Ather Electric integration."""

from __future__ import annotations


def safe_bool(value) -> bool:
    """Safely convert to bool."""
    if value in [1, "1", True, "True", "true", "On", "on"]:
        return True
    return False


def is_binary_value(value) -> bool:
    """Check if a value is effectively binary (0/1/True/False)."""
    if isinstance(value, bool):
        return True
    if str(value).lower() in ["true", "false", "on", "off"]:
        return True
    if str(value) in ["0", "1"]:
        return True
    return False
