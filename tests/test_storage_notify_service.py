from __future__ import annotations

import json
import urllib.error

import pytest

from drscreen.config import Fast2SmsSettings, Settings, TwilioSettings
from drscreen.grading import Grade
from drscreen.inference import Prediction
from drscreen.notify import (
    ConsoleSender,
    Fast2SmsSender,
    SmsResult,
    build_sender,
    compose_report,
    normalize_phone,
)
from drscreen.security import hash_password, verify_password
from drscreen.service import ScreeningService
from drscreen.storage import Database, DuplicateUsernameError, PatientInfo


def _prediction(grade: Grade = Grade.MODERATE, referable: bool = True) -> Prediction:
    probs = [0.05] * 5
    probs[grade] = 0.8
    return Prediction(grade=grade, probabilities=tuple(probs),
                      referral_probability=sum(probs[2:]), referable=referable,
                      model_version="test", image_sha256="ab" * 32)


# -- security -------------------------------------------------------------------------
def test_password_hash_roundtrip_and_salting():
    h1, h2 = hash_password("correct horse"), hash_password("correct horse")
    assert h1 != h2 and "correct horse" not in h1
    assert verify_password("correct horse", h1)
    assert not verify_password("wrong horse", h1)
    assert not verify_password("anything", "garbage")


def test_short_passwords_rejected():
    with pytest.raises(ValueError):
        hash_password("short")


# -- storage --------------------------------------------------------------------------
@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'db.sqlite'}")
    database.create_schema()
    return database


def test_operator_signup_and_login(db):
    op = db.create_operator("nurse1", "s3cure-pass")
    assert db.authenticate("nurse1", "s3cure-pass") == op
    assert db.authenticate("nurse1", "wrong-pass!") is None
    assert db.authenticate("ghost", "s3cure-pass") is None


def test_login_does_not_mix_users_credentials(db):
    """Legacy bug: any username + any *other* user's password logged you in."""
    db.create_operator("alice", "alice-password")
    db.create_operator("bob", "bob-password")
    assert db.authenticate("alice", "bob-password") is None


def test_duplicate_username_rejected(db):
    db.create_operator("nurse1", "s3cure-pass")
    with pytest.raises(DuplicateUsernameError):
        db.create_operator("nurse1", "another-pass")


def test_sql_injection_payload_is_inert(db):
    db.create_operator("admin", "s3cure-pass")
    assert db.authenticate("admin' OR '1'='1", "x' OR '1'='1") is None


def test_screening_record_and_history(db):
    patient = PatientInfo("Asha  Patil", "+919876543210", 54, "F")
    first = db.record_screening(patient, _prediction(), "/img/a.png")
    second = db.record_screening(patient, _prediction(Grade.NO_DR, False), "/img/b.png")
    db.update_sms_status(first, "sent", "SM123")

    rows = db.recent_screenings()
    assert [r.id for r in rows] == [second, first]
    assert rows[1].sms_status == "sent" and rows[1].referable
    assert rows[0].patient_name == "Asha Patil"  # whitespace normalised, patient reused


def test_export_csv_contains_header_and_rows(db):
    patient = PatientInfo("Asha Patil", "+919876543210", 54, "F")
    db.record_screening(patient, _prediction(), "/img/a.png")

    csv_text = db.export_csv()

    lines = csv_text.strip().splitlines()
    assert lines[0] == "id,date,patient_name,phone,grade,grade_label,confidence," \
                       "referable,sms_status"
    assert "Asha Patil" in lines[1] and "+919876543210" in lines[1]
    assert "Moderate DR" in lines[1]  # grade 2 label from _prediction()'s default


def test_patient_validation():
    with pytest.raises(ValueError):
        PatientInfo("  ")
    with pytest.raises(ValueError):
        PatientInfo("X", age=200)


# -- notifications --------------------------------------------------------------------
@pytest.mark.parametrize(("raw", "expected"), [
    ("9876543210", "+919876543210"),
    ("098765 43210", "+919876543210"),
    ("+1 (415) 555-0100", "+14155550100"),
    ("0044 20 7946 0958", "+442079460958"),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12", "+0123456789"])
def test_normalize_phone_rejects_garbage(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_report_text_is_short_plain_and_includes_disclaimer():
    body = compose_report("Asha Patil", _prediction(), "City Eye Camp")
    assert body.startswith("City Eye Camp")
    assert "Dear Asha" in body and "Moderate DR" in body and "not a diagnosis" in body
    assert body.isascii() and len(body) <= 320  # at most two GSM-7 segments


def test_precautionary_referral_line_when_threshold_flags_mild_case():
    body = compose_report("Ravi", _prediction(Grade.MILD, referable=True), "Clinic")
    assert "As a precaution" in body


# -- end-to-end service ---------------------------------------------------------------
class RecordingSender:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, to, body):
        self.sent.append((to, body))
        return SmsResult("sent", sid="SM-test")


def test_service_screens_stores_archives_and_notifies(settings, fundus_image):
    service = ScreeningService.from_settings(settings)
    sender = RecordingSender()
    service.sms = sender
    patient = PatientInfo("Asha Patil", service.normalize_phone("9876543210"), 54, "F")

    outcome = service.screen(fundus_image, patient, send_sms=True)

    assert outcome.sms.status == "sent"
    assert sender.sent[0][0] == "+919876543210"
    archived = settings.image_store / f"{outcome.prediction.image_sha256}.png"
    assert archived.read_bytes() == fundus_image.read_bytes()
    row = service.db.recent_screenings(1)[0]
    assert row.id == outcome.screening_id and row.sms_status == "sent"


def test_service_requires_phone_for_sms_before_running_model(settings, fundus_image):
    service = ScreeningService.from_settings(settings)
    service.predictor = None  # would crash if inference were attempted
    with pytest.raises(ValueError, match="phone"):
        service.screen(fundus_image, PatientInfo("No Phone"), send_sms=True)


def test_dry_run_sender_never_raises():
    assert ConsoleSender().send("+919876543210", "hello").status == "dry_run"


# -- Fast2SMS (free-quota alternative to Twilio) ---------------------------------------
class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fast2sms_sends_and_parses_success_response():
    captured = {}

    def fake_opener(request):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode()
        captured["auth"] = request.get_header("Authorization")
        return _FakeHttpResponse({"return": True, "request_id": "abc123"})

    sender = Fast2SmsSender(Fast2SmsSettings(api_key="test-key"), opener=fake_opener)
    result = sender.send("+919876543210", "hello from the clinic")

    assert result.status == "sent" and result.sid == "abc123"
    assert captured["auth"] == "test-key"
    assert "numbers=9876543210" in captured["body"]  # bare 10-digit, not E.164
    assert "route=q" in captured["body"]


def test_fast2sms_reports_provider_level_failure():
    def fake_opener(_request):
        return _FakeHttpResponse({"return": False, "message": "Invalid Authentication"})

    sender = Fast2SmsSender(Fast2SmsSettings(api_key="bad-key"), opener=fake_opener)
    result = sender.send("+919876543210", "hi")

    assert result.status == "failed" and "Invalid Authentication" in result.error


def test_fast2sms_surfaces_the_real_reason_from_an_http_error_body():
    # Reproduces a real failure: Fast2SMS returns HTTP 400 (not a 200 with
    # return:false) when the wallet has never been topped up, with the
    # actual explanation in the body. Losing that body left users with just
    # "HTTP Error 400: Bad Request" and no way to know what to fix.
    import io

    body = b'{"status_code":999,"message":"You need to complete one transaction of ' \
          b'100 INR or more before using API route."}'

    def fake_opener(request):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", None,
                                     io.BytesIO(body))

    sender = Fast2SmsSender(Fast2SmsSettings(api_key="test-key"), opener=fake_opener)
    result = sender.send("+919876543210", "hi")

    assert result.status == "failed"
    assert "100 INR" in result.error


def test_fast2sms_http_error_falls_back_gracefully_on_non_json_body():
    import io

    def fake_opener(request):
        raise urllib.error.HTTPError(request.full_url, 500, "Server Error", None,
                                     io.BytesIO(b"<html>not json</html>"))

    sender = Fast2SmsSender(Fast2SmsSettings(api_key="test-key"), opener=fake_opener)
    result = sender.send("+919876543210", "hi")

    assert result.status == "failed" and result.error


def test_fast2sms_reports_network_failure_without_raising():
    def fake_opener(_request):
        raise urllib.error.URLError("no route to host")

    sender = Fast2SmsSender(Fast2SmsSettings(api_key="test-key"), opener=fake_opener)
    result = sender.send("+919876543210", "hi")

    assert result.status == "failed" and result.error


def test_fast2sms_rejects_unconfigured_settings():
    with pytest.raises(ValueError):
        Fast2SmsSender(Fast2SmsSettings(api_key=None))


# -- provider selection: Twilio > Fast2SMS > dry-run -------------------------------------
def test_build_sender_falls_back_to_console_when_nothing_configured(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path/'x.db'}")
    assert isinstance(build_sender(settings), ConsoleSender)


def test_build_sender_prefers_fast2sms_when_twilio_not_configured(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path/'x.db'}",
                        fast2sms=Fast2SmsSettings(api_key="test-key"))
    assert isinstance(build_sender(settings), Fast2SmsSender)


def test_build_sender_respects_sms_enabled_false(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path/'x.db'}", sms_enabled=False,
                        fast2sms=Fast2SmsSettings(api_key="test-key"),
                        twilio=TwilioSettings(account_sid="AC", auth_token="tok",
                                             from_number="+15550100"))
    assert isinstance(build_sender(settings), ConsoleSender)
