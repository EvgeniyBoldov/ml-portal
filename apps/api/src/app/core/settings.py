# PATCHED: additive defaults for previously-missing settings used across routers/clients.
# Place this content at the END of your existing settings.py (or merge manually if your file differs).
try:
    from pydantic import BaseModel  # noqa: F401
except Exception:
    pass

# ---- BEGIN PATCH: additive settings ----
# These are *only* set if they weren't already defined earlier in the Settings class.
# If you have them already, keep your originals and remove duplicates below.
def _patch_settings_defaults(Settings):
    # Helper to add an attribute only if it's missing
    def _ensure(name, value):
        if not hasattr(Settings, name):
            setattr(Settings, name, value)
    # Commonly used in codebase but sometimes missing
    _ensure("CHAT_RATE_LIMIT_RPS", 3)
    _ensure("CHAT_SSE_HEARTBEAT_SECONDS", 15)
    _ensure("ALLOWED_FILE_TYPES", ["text/plain", "application/pdf", "image/png", "image/jpeg", "application/json"])
    _ensure("S3_BUCKET_ANALYSIS", "analysis")
    # Keep a sane default; callers should prefer ACCESS_TTL_SECONDS if present
    _ensure("JWT_TTL_DEFAULT", 3600)

try:
    # Import the existing Settings symbol from current module namespace
    Settings  # type: ignore[name-defined]
except NameError:
    # If your file calls it something else (e.g., AppSettings), you can rename here or import above.
    pass
else:
    _patch_settings_defaults(Settings)
# ---- END PATCH ----
