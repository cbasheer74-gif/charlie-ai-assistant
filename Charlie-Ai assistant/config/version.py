"""
config/version.py — Canonical version and release metadata for CHARLIE.

Single source of truth for application versioning, build stamping, and release channels.
"""

APP_NAME = "CHARLIE"
APP_VERSION = "1.2.4"
BUILD_NUMBER = 109
PROTOCOL_VERSION = "1.0.0"
MIN_OS_VERSION = "10.0"
DEFAULT_RELEASE_CHANNEL = "STABLE"

# Release channels
CHANNEL_STABLE = "STABLE"
CHANNEL_BETA = "BETA"
CHANNEL_INTERNAL = "INTERNAL"
VALID_CHANNELS = (CHANNEL_STABLE, CHANNEL_BETA, CHANNEL_INTERNAL)
