"""Runtime configuration, read from environment variables (and an optional .env file).

Secrets (DB password, Twilio token) never live in source code; see .env.example.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: Path) -> Path:
    value = _env(name)
    path = Path(value).expanduser() if value else default
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class TwilioSettings:
    account_sid: str | None = None
    auth_token: str | None = None
    from_number: str | None = None
    messaging_service_sid: str | None = None

    @property
    def configured(self) -> bool:
        has_sender = bool(self.from_number or self.messaging_service_sid)
        return bool(self.account_sid and self.auth_token and has_sender)


@dataclass(frozen=True)
class Fast2SmsSettings:
    """Fast2SMS (India): a free-quota alternative to Twilio for trying SMS
    without a paid account. Sign up at fast2sms.com for an API key — the
    'q' (Quick SMS) route needs no DLT template approval and gives a small
    free daily quota, enough to demo or test this project end to end."""

    api_key: str | None = None
    route: str = "q"

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class Settings:
    model_path: Path = PROJECT_ROOT / "models" / "classifier.pt"
    device: str = "auto"
    tta: bool = True
    # P(grade >= Moderate) above which a patient is flagged for referral. Lowering it
    # trades specificity for sensitivity (fewer missed referable cases).
    referral_threshold: float = 0.5
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'drscreen.db'}"
    image_store: Path = PROJECT_ROOT / "data" / "images"
    report_dir: Path = PROJECT_ROOT / "data" / "reports"
    sms_enabled: bool = True
    default_country_code: str = "+91"
    clinic_name: str = "DR Screening Centre"
    twilio: TwilioSettings = field(default_factory=TwilioSettings)
    fast2sms: Fast2SmsSettings = field(default_factory=Fast2SmsSettings)

    @classmethod
    def from_env(cls, env_file: str | os.PathLike | None = None) -> Settings:
        try:
            from dotenv import load_dotenv
        except ImportError:  # pragma: no cover - python-dotenv is a core dependency
            pass
        else:
            load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)

        defaults = cls()
        threshold = float(_env("DRS_REFERRAL_THRESHOLD", str(defaults.referral_threshold)))
        if not 0.0 < threshold < 1.0:
            raise ValueError("DRS_REFERRAL_THRESHOLD must be between 0 and 1")

        return cls(
            model_path=_env_path("DRS_MODEL_PATH", defaults.model_path),
            device=_env("DRS_DEVICE", defaults.device),
            tta=_env_bool("DRS_TTA", defaults.tta),
            referral_threshold=threshold,
            database_url=_env("DRS_DATABASE_URL", defaults.database_url),
            image_store=_env_path("DRS_IMAGE_STORE", defaults.image_store),
            report_dir=_env_path("DRS_REPORT_DIR", defaults.report_dir),
            sms_enabled=_env_bool("DRS_SMS_ENABLED", defaults.sms_enabled),
            default_country_code=_env("DRS_DEFAULT_COUNTRY_CODE", defaults.default_country_code),
            clinic_name=_env("DRS_CLINIC_NAME", defaults.clinic_name),
            twilio=TwilioSettings(
                account_sid=_env("TWILIO_ACCOUNT_SID"),
                auth_token=_env("TWILIO_AUTH_TOKEN"),
                from_number=_env("TWILIO_FROM_NUMBER"),
                messaging_service_sid=_env("TWILIO_MESSAGING_SERVICE_SID"),
            ),
            fast2sms=Fast2SmsSettings(
                api_key=_env("FAST2SMS_API_KEY"),
                route=_env("FAST2SMS_ROUTE", defaults.fast2sms.route),
            ),
        )


def update_env(pairs: dict[str, str], env_file: str | os.PathLike | None = None) -> Path:
    """Persist settings changes made in the GUI's Settings screen to ``.env``,
    so they survive a restart instead of only affecting the running process."""
    from dotenv import set_key

    path = Path(env_file or PROJECT_ROOT / ".env")
    path.touch(exist_ok=True)
    for key, value in pairs.items():
        set_key(str(path), key, value, quote_mode="never")
    return path
