"""SMS delivery of screening reports.

Two real providers are supported, plus a dry-run fallback:

- **Twilio** — the industry-standard choice; free trial credit, no payment
  method required, but SMS can only go to phone numbers you've verified in
  the Twilio console until you add a paid plan.
- **Fast2SMS** (India) — cheaper and needs no DLT template approval on its
  "Quick SMS" route, but it is *not* free: their API refuses every request,
  even the first, until the account has a minimum ₹100 wallet top-up (their
  own error: "You need to complete one transaction of 100 INR or more
  before using API route."). Budget for that top-up before relying on it.
  See ``Fast2SmsSettings``.

``build_sender()`` picks Twilio if configured, else Fast2SMS, else falls back
to printing the message (dry-run) — the app always works, it just doesn't
send real texts until one provider is configured.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from drscreen.config import Fast2SmsSettings, Settings, TwilioSettings

if TYPE_CHECKING:  # keep this module importable without torch
    from drscreen.inference import Prediction

log = logging.getLogger(__name__)

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


@dataclass(frozen=True)
class SmsResult:
    status: str  # "sent" | "dry_run" | "failed"
    sid: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"sent", "dry_run"}


class SmsSender(Protocol):
    def send(self, to: str, body: str) -> SmsResult: ...


def normalize_phone(raw: str, default_country_code: str = "+91") -> str:
    """Normalise user input to E.164. Bare 10-digit numbers get the default code.

    >>> normalize_phone("098765 43210")
    '+919876543210'
    """
    digits = re.sub(r"[\s\-().]", "", raw or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        digits = digits.lstrip("0")
        digits = default_country_code + digits
    if not _E164.match(digits):
        raise ValueError(f"Invalid phone number: {raw!r}")
    return digits


def compose_report(patient_name: str, prediction: Prediction, clinic_name: str) -> str:
    """Plain GSM-7 text (no emoji) so the message fits in as few segments as possible."""
    first_name = patient_name.split()[0] if patient_name.strip() else "Patient"
    lines = [
        f"{clinic_name}: Eye screening report",
        f"Dear {first_name}, result: {prediction.grade.label} "
        f"(Grade {int(prediction.grade)}/4, {prediction.confidence:.0%} confidence).",
        prediction.grade.advice,
    ]
    if prediction.referable and not prediction.grade.is_referable:
        lines.append("As a precaution, please consult an ophthalmologist.")
    lines.append("AI-assisted screening, not a diagnosis.")
    return "\n".join(lines)


class ConsoleSender:
    """Logs the message instead of sending it (used when Twilio isn't configured)."""

    def send(self, to: str, body: str) -> SmsResult:
        log.info("[dry-run SMS to %s]\n%s", _mask(to), body)
        return SmsResult("dry_run")


class TwilioSender:
    def __init__(self, settings: TwilioSettings):
        if not settings.configured:
            raise ValueError("Twilio credentials are incomplete")
        from twilio.rest import Client  # optional dependency: pip install drscreen[sms]

        self._client = Client(settings.account_sid, settings.auth_token)
        self._settings = settings

    def send(self, to: str, body: str) -> SmsResult:
        from twilio.base.exceptions import TwilioException

        sender = ({"messaging_service_sid": self._settings.messaging_service_sid}
                  if self._settings.messaging_service_sid
                  else {"from_": self._settings.from_number})
        try:
            message = self._client.messages.create(to=to, body=body, **sender)
        except TwilioException as exc:
            log.warning("Twilio send to %s failed: %s", _mask(to), exc)
            return SmsResult("failed", error=str(exc))
        log.info("SMS queued to %s (sid=%s)", _mask(to), message.sid)
        return SmsResult("sent", sid=message.sid)


class Fast2SmsSender:
    """A low-cost SMS provider (India) — see the module docstring for the
    ₹100 minimum-balance requirement their API enforces.

    Uses only the stdlib (``urllib``), so it needs no extra dependency.
    ``opener`` is injectable for testing without a real network call.
    """

    API_URL = "https://www.fast2sms.com/dev/bulkV2"

    def __init__(self, settings: Fast2SmsSettings,
                opener: Callable[[urllib.request.Request], object] | None = None):
        if not settings.configured:
            raise ValueError("Fast2SMS API key is not configured")
        self._settings = settings
        self._opener = opener or (lambda req: urllib.request.urlopen(req, timeout=15))

    def send(self, to: str, body: str) -> SmsResult:
        # Fast2SMS takes bare 10-digit Indian mobile numbers, not E.164.
        digits = re.sub(r"\D", "", to)[-10:]
        payload = urllib.parse.urlencode({
            "route": self._settings.route,
            "message": body,
            "language": "english",
            "flash": "0",
            "numbers": digits,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.API_URL, data=payload, method="POST",
            headers={"authorization": self._settings.api_key,
                    "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self._opener(request) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # An HTTPError IS the response (a 4xx/5xx status) — Fast2SMS puts
            # its actual reason in the body even on failure, e.g. "You need
            # to complete one transaction of 100 INR or more before using
            # API route." Reading only str(exc) throws that away and leaves
            # just "HTTP Error 400: Bad Request", which explains nothing.
            error = _extract_error(exc)
            log.warning("Fast2SMS send to %s failed: %s", _mask(to), error)
            return SmsResult("failed", error=error)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            log.warning("Fast2SMS send to %s failed: %s", _mask(to), exc)
            return SmsResult("failed", error=str(exc))

        if data.get("return") is True:
            sid = str(data["request_id"]) if data.get("request_id") else None
            log.info("Fast2SMS queued to %s (request_id=%s)", _mask(to), sid)
            return SmsResult("sent", sid=sid)
        error = str(data.get("message") or data)
        log.warning("Fast2SMS send to %s failed: %s", _mask(to), error)
        return SmsResult("failed", error=error)


def build_sender(settings: Settings) -> SmsSender:
    """Pick the best available provider: Twilio, then Fast2SMS, then dry-run."""
    if not settings.sms_enabled:
        return ConsoleSender()
    if settings.twilio.configured:
        try:
            return TwilioSender(settings.twilio)
        except ImportError:
            log.warning("twilio package not installed; trying the next SMS provider")
    if settings.fast2sms.configured:
        return Fast2SmsSender(settings.fast2sms)
    return ConsoleSender()


def _mask(phone: str) -> str:
    return phone[:3] + "*" * max(len(phone) - 7, 0) + phone[-4:]


def _extract_error(exc: urllib.error.HTTPError) -> str:
    """Pull the provider's actual reason out of an HTTP error response body,
    falling back gracefully if the body isn't readable JSON."""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return str(exc)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip() or str(exc)
    return str(parsed.get("message") or parsed)
