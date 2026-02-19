"""Superagente86 package."""

# Apply httplib2 patch for macOS compatibility
try:
    from . import httplib2_patch  # noqa: F401
except ImportError:
    pass  # Patch not needed if httplib2 not installed
