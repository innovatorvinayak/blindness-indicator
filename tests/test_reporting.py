from __future__ import annotations

from datetime import datetime

import pytest

from drscreen.reporting import ReportContext, build_report_html, save_report
from drscreen.storage import Database, PatientInfo, ScreeningDetail
from tests.test_storage_notify_service import _prediction


def _detail(**overrides) -> ScreeningDetail:
    base = dict(
        id=42, created_at=datetime(2026, 1, 15, 9, 30), patient_name="Asha Patil",
        phone="+919876543210", age=54, sex="F", operator_username="nurse1",
        image_path="/does/not/exist.png", image_sha256="ab" * 32, grade=3,
        confidence=0.87, referral_probability=0.94, referable=True,
        probabilities=[0.01, 0.02, 0.10, 0.87, 0.00], model_version="test-v1",
        sms_status="sent", sms_sid="SM123",
    )
    base.update(overrides)
    return ScreeningDetail(**base)


def _ctx(**overrides) -> ReportContext:
    base = dict(clinic_name="City Eye Camp", referral_threshold=0.5)
    base.update(overrides)
    return ReportContext(**base)


def test_report_contains_patient_and_assessment_details():
    html = build_report_html(_detail(), _ctx())
    assert "Asha Patil" in html
    assert "+919876543210" in html
    assert "Severe DR" in html
    assert "87.0%" in html  # confidence
    assert "REFER TO OPHTHALMOLOGIST" in html
    assert "City Eye Camp" in html
    assert "DRS-000042" in html
    assert "not a medical diagnosis" in html


def test_report_shows_clear_banner_when_not_referable():
    html = build_report_html(_detail(grade=0, referable=False, referral_probability=0.02,
                                     probabilities=[0.97, 0.01, 0.01, 0.005, 0.005]), _ctx())
    assert "No referral required" in html
    assert "REFER TO OPHTHALMOLOGIST" not in html


def test_report_embeds_real_image_as_data_uri(fundus_image):
    html = build_report_html(_detail(image_path=str(fundus_image)), _ctx())
    assert 'alt="Fundus photograph"' in html
    assert "Image not available" not in html


def test_report_handles_missing_image_gracefully():
    # The header logo is always a data URI; only the fundus photo itself
    # should be affected by a missing source image.
    html = build_report_html(_detail(image_path="/nope/gone.png"), _ctx())
    assert "Image not available" in html
    assert 'alt="Fundus photograph"' not in html
    assert 'class="mark"' in html  # the logo itself still renders


def test_report_escapes_untrusted_patient_name():
    html = build_report_html(_detail(patient_name='<script>alert(1)</script>'), _ctx())
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_all_five_probability_rows_present_and_predicted_row_marked():
    html = build_report_html(_detail(probabilities=[0.1, 0.1, 0.1, 0.6, 0.1], grade=3), _ctx())
    for label in ("No Diabetic Retinopathy", "Mild DR", "Moderate DR", "Severe DR",
                  "Proliferative DR"):
        assert label in html
    assert 'class="predicted"' in html


def test_save_report_writes_file_named_by_id(tmp_path):
    path = save_report(_detail(id=7), _ctx(), tmp_path)
    assert path == tmp_path / "screening_000007.html"
    assert path.is_file()
    assert "Asha Patil" in path.read_text()


def test_report_id_defaults_but_can_be_overridden():
    html = build_report_html(_detail(id=5), _ctx(report_id="CUSTOM-ID"))
    assert "CUSTOM-ID" in html
    assert "DRS-000005" not in html


# -- storage: fetching the full detail record ------------------------------------------
@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'db.sqlite'}")
    database.create_schema()
    return database


def test_get_screening_detail_joins_patient_and_operator(db):
    operator = db.create_operator("nurse1", "s3cure-pass")
    patient = PatientInfo("Asha Patil", "+919876543210", 54, "F")
    screening_id = db.record_screening(patient, _prediction(), "/img/a.png", operator.id)

    detail = db.get_screening_detail(screening_id)

    assert detail is not None
    assert detail.patient_name == "Asha Patil"
    assert detail.operator_username == "nurse1"
    assert detail.phone == "+919876543210" and detail.age == 54 and detail.sex == "F"
    assert detail.grade == int(_prediction().grade)


def test_get_screening_detail_without_operator_is_none_not_error(db):
    patient = PatientInfo("Walk-in Patient")
    screening_id = db.record_screening(patient, _prediction(), "/img/b.png", operator_id=None)

    detail = db.get_screening_detail(screening_id)

    assert detail is not None
    assert detail.operator_username is None


def test_get_screening_detail_missing_id_returns_none(db):
    assert db.get_screening_detail(999) is None


def test_patient_history_orders_by_recency_and_excludes_current(db):
    patient = PatientInfo("Asha Patil", "+919876543210")
    first = db.record_screening(patient, _prediction(), "/img/a.png")
    second = db.record_screening(patient, _prediction(), "/img/b.png")
    third = db.record_screening(patient, _prediction(), "/img/c.png")

    history = db.patient_history("Asha Patil", "+919876543210", exclude_id=third)

    assert [r.id for r in history] == [second, first]


def test_patient_history_does_not_leak_other_patients(db):
    a = PatientInfo("Asha Patil", "+919876543210")
    b = PatientInfo("Ravi Kumar", "+919123456780")
    db.record_screening(a, _prediction(), "/img/a.png")
    db.record_screening(b, _prediction(), "/img/b.png")

    assert len(db.patient_history("Asha Patil", "+919876543210")) == 1


# -- service: end-to-end report generation from a real screening ------------------------
def test_service_builds_report_for_a_real_screening(settings, fundus_image):
    from drscreen.service import ScreeningService

    service = ScreeningService.from_settings(settings)
    patient = PatientInfo("Ravi Kumar", service.normalize_phone("9123456780"), 61, "M")
    outcome = service.screen(fundus_image, patient)

    report_path = service.build_report(outcome.screening_id)

    assert report_path.is_file()
    text = report_path.read_text()
    assert "Ravi Kumar" in text
    assert "data:image/png;base64," in text  # the archived image was embedded


def test_service_build_report_raises_for_unknown_id(settings):
    from drscreen.service import ScreeningService

    service = ScreeningService.from_settings(settings)
    with pytest.raises(KeyError):
        service.build_report(999999)
