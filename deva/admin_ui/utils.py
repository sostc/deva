"""Admin UI utilities."""

import hashlib

def stable_widget_id(key, prefix="id"):
    """Generate a stable widget ID based on a key."""
    digest = hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"
