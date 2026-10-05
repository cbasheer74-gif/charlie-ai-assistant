"""
licensing_server/env_validator.py — Production environment configuration validator.

Fails fast on boot if critical security or configuration parameters are missing or insecure,
preventing silent failures or vulnerability exposure in production.
"""

from __future__ import annotations

import logging
import sys
from typing import List, Tuple

from licensing_server.config import config

logger = logging.getLogger("licensing_server.config")

INSECURE_DEFAULT_SECRETS = {
    "charlie_jwt_dev_secret_change_in_production",
    "secret",
    "changeme",
    "password",
    "123456",
}


def validate_environment() -> Tuple[bool, List[str], List[str]]:
    """
    Validate environment variables on startup.
    Returns: (is_valid, errors, warnings)
    """
    errors: List[str] = []
    warnings: List[str] = []

    is_prod = config.ENVIRONMENT == "production"

    # 1. JWT Secret Validation
    if not config.JWT_SECRET:
        errors.append("CHARLIE_JWT_SECRET is empty.")
    elif config.JWT_SECRET in INSECURE_DEFAULT_SECRETS:
        if is_prod:
            errors.append("CHARLIE_JWT_SECRET is set to an insecure default value in production.")
        else:
            warnings.append("CHARLIE_JWT_SECRET is using a development default secret.")
    elif len(config.JWT_SECRET) < 32:
        if is_prod:
            errors.append(f"CHARLIE_JWT_SECRET is too short ({len(config.JWT_SECRET)} chars, min 32 required for HS256).")
        else:
            warnings.append(f"CHARLIE_JWT_SECRET is short ({len(config.JWT_SECRET)} chars, 32+ recommended).")

    # 2. Admin API Key Validation
    if is_prod and not config.ADMIN_API_KEY:
        errors.append("CHARLIE_ADMIN_KEY must be set in production mode.")

    # 3. Database URL
    if not config.DATABASE_URL:
        errors.append("CHARLIE_DB_URL is not configured.")

    # 4. Payment Gateway Configuration
    if is_prod:
        if not config.RAZORPAY_KEY_ID or not config.RAZORPAY_KEY_SECRET:
            warnings.append("RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET missing in production; payments will be disabled.")
        if not config.RAZORPAY_WEBHOOK_SECRET:
            warnings.append("RAZORPAY_WEBHOOK_SECRET missing; incoming webhooks will be rejected.")

    # 5. SMTP Configuration
    if not config.SMTP_HOST:
        warnings.append("SMTP_HOST not configured; transactional emails (verification, reset) will be simulated or skipped.")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def enforce_environment_or_halt() -> None:
    """Run validation. Log warnings; raise RuntimeError on fatal errors in production."""
    is_valid, errors, warnings = validate_environment()

    for w in warnings:
        logger.warning(f"[CONFIG WARNING] {w}")

    if not is_valid:
        for err in errors:
            logger.error(f"[CONFIG FATAL] {err}")
        if config.ENVIRONMENT == "production":
            raise RuntimeError(
                f"Startup halted due to {len(errors)} critical configuration errors in production:\n"
                + "\n".join(f" - {e}" for e in errors)
            )
        else:
            logger.warning(
                f"Application started with {len(errors)} non-fatal configuration issues in development mode."
            )
