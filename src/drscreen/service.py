"""The screening workflow: predict -> archive image -> store result -> notify patient.

Both the GUI and the CLI go through this one class, so the business rules live in a
single, testable place.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from drscreen.config import Settings
from drscreen.inference import Prediction, Predictor
from drscreen.notify import SmsResult, SmsSender, build_sender, compose_report, normalize_phone
from drscreen.reporting import ReportContext, save_report
from drscreen.storage import Database, OperatorInfo, PatientInfo

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScreeningOutcome:
    screening_id: int
    prediction: Prediction
    sms: SmsResult | None


class ScreeningService:
    def __init__(self, predictor: Predictor, db: Database, sms: SmsSender, settings: Settings):
        self.predictor = predictor
        self.db = db
        self.sms = sms
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings) -> ScreeningService:
        predictor = Predictor.from_checkpoint(
            settings.model_path, settings.device, tta=settings.tta,
            referral_threshold=settings.referral_threshold,
        )
        db = Database(settings.database_url)
        db.create_schema()
        return cls(predictor, db, build_sender(settings), settings)

    def normalize_phone(self, raw: str | None) -> str | None:
        return normalize_phone(raw, self.settings.default_country_code) if raw else None

    def screen(self, image_path: str | Path, patient: PatientInfo,
               operator: OperatorInfo | None = None, *, send_sms: bool = False
               ) -> ScreeningOutcome:
        image_path = Path(image_path)
        # Validate inputs before spending compute on inference.
        if send_sms and not patient.phone:
            raise ValueError("A phone number is required to send an SMS report.")

        prediction = self.predictor.predict(image_path)
        archived = self._archive(image_path, prediction.image_sha256)
        screening_id = self.db.record_screening(
            patient, prediction, str(archived), operator.id if operator else None)
        log.info("screening #%d: %s (p=%.2f)", screening_id, prediction.grade,
                 prediction.confidence)

        sms_result = self.notify(screening_id, patient, prediction) if send_sms else None
        return ScreeningOutcome(screening_id, prediction, sms_result)

    def notify(self, screening_id: int, patient: PatientInfo, prediction: Prediction
               ) -> SmsResult:
        body = compose_report(patient.full_name, prediction, self.settings.clinic_name)
        result = self.sms.send(patient.phone, body)
        self.db.update_sms_status(screening_id, result.status, result.sid)
        return result

    def build_report(self, screening_id: int) -> Path:
        """Regenerate the full HTML report for any past screening from the
        database alone — works even if the original upload file is gone,
        since the fundus image is archived in content-addressed storage."""
        detail = self.db.get_screening_detail(screening_id)
        if detail is None:
            raise KeyError(f"No screening with id {screening_id}")
        ctx = ReportContext(clinic_name=self.settings.clinic_name,
                            referral_threshold=self.settings.referral_threshold)
        return save_report(detail, ctx, self.settings.report_dir)

    def _archive(self, image_path: Path, sha256: str | None) -> Path:
        """Copy the upload into content-addressed storage so records never dangle."""
        if sha256 is None:
            return image_path
        store = self.settings.image_store
        store.mkdir(parents=True, exist_ok=True)
        target = store / f"{sha256}{image_path.suffix.lower()}"
        if not target.exists():
            shutil.copy2(image_path, target)
        return target
