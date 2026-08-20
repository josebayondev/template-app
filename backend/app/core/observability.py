import logging
import re
from typing import Any, cast

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.types import Event, Hint

from app.core.config import Settings

logger = logging.getLogger(__name__)

REDACTED = "[redacted]"

# Keys whose value is dropped whatever it looks like. Matched as a substring, so
# "user_email" and "customer_phone" are covered. Bare "tel" is deliberately absent:
# it would also redact "hotel", which in plenty of domains is real data.
SENSITIVE_KEY_PATTERN = re.compile(
    r"e?mail|phone|telefono|teléfono|m[oó]vil"
    r"|password|passwd|contrase[nñ]a|secret|token|authorization|api[_-]?key"
    r"|cookie|session|dsn|iban|card_number|credit_card|\bdni\b|\bnif\b|\bnie\b",
    re.IGNORECASE,
)

# Free text is the other half of the problem: an address interpolated into a log
# message ("could not notify ana@example.com") never passes through a key we
# could recognise, so the values themselves have to be swept too.
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Spanish numbers: nine digits starting 6-9, optional +34, optional separators.
# The \b anchors stop it matching inside a longer run of digits, so timestamps,
# ids and byte counts survive. Deliberately narrow — a loose pattern would redact
# half of every traceback and make the events useless.
PHONE_PATTERN = re.compile(r"\b(?:\+34[ .-]?)?[6-9]\d{2}[ .-]?\d{3}[ .-]?\d{3}\b")

# Events are nested but not infinitely: this only guards against a pathological
# or cyclic structure turning one report into a hang.
MAX_SCRUB_DEPTH = 12


def _scrub_value(value: Any, depth: int = 0) -> Any:
    """Walk an event recursively, redacting by key name and by value shape."""
    if depth > MAX_SCRUB_DEPTH:
        return REDACTED
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if isinstance(key, str) and SENSITIVE_KEY_PATTERN.search(key)
                else _scrub_value(item, depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(item, depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item, depth + 1) for item in value)
    if isinstance(value, str):
        return PHONE_PATTERN.sub(REDACTED, EMAIL_PATTERN.sub(REDACTED, value))
    return value


def scrub_event(event: Event, hint: Hint) -> Event | None:
    """Strip personal data from an event just before it leaves the process.

    send_default_pii=False already keeps Sentry from attaching request bodies,
    headers, cookies and client IPs. What it cannot cover is the data we put in
    ourselves: log messages, exception strings, and the local variables Sentry
    captures from every stack frame. That is where a customer's email or phone
    realistically leaks, so this sweeps the whole event.
    """
    return cast("Event", _scrub_value(event))


def configure_sentry(settings: Settings) -> None:
    """Initialise Sentry when a DSN is configured, otherwise do nothing.

    Leaving SENTRY_DSN unset is the normal case locally and in CI, so this is a
    no-op there instead of shipping events from a developer machine.
    """
    if not settings.sentry_dsn:
        logger.info("Sentry disabled: SENTRY_DSN is not set")
        return

    try:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            # Assume the repo is public and the app handles personal data: never
            # attach request bodies, headers, cookies or client IPs to an event.
            send_default_pii=False,
            # send_default_pii only stops Sentry from collecting PII itself. It
            # does nothing about PII we hand it in a log line or a local variable.
            before_send=scrub_event,
            integrations=[
                # Breadcrumbs from INFO up, and one Sentry event per logging.error()
                # call. These are the SDK defaults, spelled out so a future change to
                # them cannot silently stop reporting errors.
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
        )
    except Exception:
        # A malformed DSN raises BadDsn, and this runs at import time in main.py,
        # so an unguarded failure kills the container. Losing telemetry is bad;
        # refusing to serve requests because telemetry is misconfigured is worse.
        logger.exception("Sentry init failed, continuing without it")
        return

    logger.info("Sentry enabled for environment %s", settings.environment)
