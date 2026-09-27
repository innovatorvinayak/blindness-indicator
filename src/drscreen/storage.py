"""Persistence for operators, patients and screening results.

Backed by SQLAlchemy so the same code runs on MySQL (production, via HeidiSQL or any
client) and SQLite (zero-setup local use and tests). Every public method runs in its
own short transaction; together with InnoDB row-level locking and the UNIQUE
constraints below this makes concurrent use from several workstations safe, which
the legacy "read all rows then INSERT" code was not.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from drscreen.grading import Grade
from drscreen.security import hash_password, verify_password

if TYPE_CHECKING:  # keep this module importable without torch
    from drscreen.inference import Prediction


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Operator(Base):
    __tablename__ = "operators"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("full_name", "phone", name="uq_patient_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    age: Mapped[int | None] = mapped_column(SmallInteger)
    sex: Mapped[str | None] = mapped_column(String(1))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Screening(Base):
    __tablename__ = "screenings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id"))
    image_path: Mapped[str] = mapped_column(String(512))
    image_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    grade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    referral_probability: Mapped[float] = mapped_column(Float, nullable=False)
    referable: Mapped[bool] = mapped_column(nullable=False)
    probabilities: Mapped[list] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64))
    sms_status: Mapped[str | None] = mapped_column(String(16))
    sms_sid: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class DuplicateUsernameError(ValueError):
    pass


@dataclass(frozen=True)
class OperatorInfo:
    id: int
    username: str


@dataclass(frozen=True)
class PatientInfo:
    full_name: str
    phone: str | None = None
    age: int | None = None
    sex: str | None = None

    def __post_init__(self):
        if not self.full_name.strip():
            raise ValueError("Patient name is required.")
        if self.age is not None and not 0 < self.age < 130:
            raise ValueError("Age must be between 1 and 129.")
        if self.sex is not None and self.sex not in {"M", "F", "O"}:
            raise ValueError("Sex must be M, F or O.")


@dataclass(frozen=True)
class ScreeningRow:
    id: int
    created_at: datetime
    patient_name: str
    phone: str | None
    grade: int
    confidence: float
    referable: bool
    sms_status: str | None


@dataclass(frozen=True)
class ScreeningDetail:
    """Everything a full clinical report needs, in one place. Rebuildable for
    any past screening from the database alone (the image is content-addressed
    and archived by :class:`~drscreen.service.ScreeningService`), so a report
    can be regenerated long after the original upload file is gone."""

    id: int
    created_at: datetime
    patient_name: str
    phone: str | None
    age: int | None
    sex: str | None
    operator_username: str | None
    image_path: str
    image_sha256: str | None
    grade: int
    confidence: float
    referral_probability: float
    referable: bool
    probabilities: list[float]
    model_version: str
    sms_status: str | None
    sms_sid: str | None


class Database:
    def __init__(self, url: str, *, echo: bool = False):
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(url, echo=echo, pool_pre_ping=True, future=True)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._sessions.begin() as session:
            yield session

    # -- operators -----------------------------------------------------------------
    def create_operator(self, username: str, password: str) -> OperatorInfo:
        username = username.strip()
        if not username:
            raise ValueError("Username is required.")
        operator = Operator(username=username, password_hash=hash_password(password))
        try:
            with self.session() as s:
                s.add(operator)
                s.flush()
        except IntegrityError as exc:  # UNIQUE(username) closes the check-then-insert race
            raise DuplicateUsernameError(f"Username {username!r} is already registered.") from exc
        return OperatorInfo(operator.id, operator.username)

    def authenticate(self, username: str, password: str) -> OperatorInfo | None:
        with self.session() as s:
            op = s.scalar(select(Operator).where(Operator.username == username.strip()))
        if op is None:
            # Burn comparable time so response latency doesn't reveal valid usernames.
            verify_password(password, _DUMMY_HASH)
            return None
        return OperatorInfo(op.id, op.username) if verify_password(password, op.password_hash) \
            else None

    # -- screenings ----------------------------------------------------------------
    def record_screening(self, patient: PatientInfo, prediction: Prediction, image_path: str,
                         operator_id: int | None = None) -> int:
        with self.session() as s:
            patient_id = self._get_or_create_patient(s, patient)
            row = Screening(
                patient_id=patient_id,
                operator_id=operator_id,
                image_path=image_path,
                image_sha256=prediction.image_sha256,
                grade=int(prediction.grade),
                confidence=prediction.confidence,
                referral_probability=prediction.referral_probability,
                referable=prediction.referable,
                probabilities=list(prediction.probabilities),
                model_version=prediction.model_version,
            )
            s.add(row)
            s.flush()
            return row.id

    def update_sms_status(self, screening_id: int, status: str, sid: str | None) -> None:
        with self.session() as s:
            row = s.get(Screening, screening_id, with_for_update=True)
            if row is None:
                raise KeyError(screening_id)
            row.sms_status, row.sms_sid = status, sid

    def recent_screenings(self, limit: int = 50) -> list[ScreeningRow]:
        query = (
            select(Screening, Patient)
            .join(Patient, Patient.id == Screening.patient_id)
            .order_by(Screening.created_at.desc(), Screening.id.desc())
            .limit(limit)
        )
        with self.session() as s:
            return [
                ScreeningRow(sc.id, sc.created_at, p.full_name, p.phone, sc.grade,
                             sc.confidence, sc.referable, sc.sms_status)
                for sc, p in s.execute(query)
            ]

    def get_screening_detail(self, screening_id: int) -> ScreeningDetail | None:
        query = (
            select(Screening, Patient, Operator)
            .join(Patient, Patient.id == Screening.patient_id)
            .outerjoin(Operator, Operator.id == Screening.operator_id)
            .where(Screening.id == screening_id)
        )
        with self.session() as s:
            row = s.execute(query).first()
        if row is None:
            return None
        sc, p, op = row
        return ScreeningDetail(
            id=sc.id, created_at=sc.created_at, patient_name=p.full_name, phone=p.phone,
            age=p.age, sex=p.sex, operator_username=op.username if op else None,
            image_path=sc.image_path, image_sha256=sc.image_sha256, grade=sc.grade,
            confidence=sc.confidence, referral_probability=sc.referral_probability,
            referable=sc.referable, probabilities=list(sc.probabilities),
            model_version=sc.model_version, sms_status=sc.sms_status, sms_sid=sc.sms_sid,
        )

    def patient_history(self, patient_name: str, phone: str | None,
                        exclude_id: int | None = None, limit: int = 10) -> list[ScreeningRow]:
        """Prior screenings for the same patient identity (name + phone), most
        recent first — used to show progression over time in a report."""
        name = " ".join(patient_name.split())
        query = (
            select(Screening, Patient)
            .join(Patient, Patient.id == Screening.patient_id)
            .where(Patient.full_name == name, Patient.phone == phone)
            .order_by(Screening.created_at.desc(), Screening.id.desc())
            .limit(limit)
        )
        with self.session() as s:
            rows = [
                ScreeningRow(sc.id, sc.created_at, p.full_name, p.phone, sc.grade,
                             sc.confidence, sc.referable, sc.sms_status)
                for sc, p in s.execute(query)
            ]
        return [r for r in rows if r.id != exclude_id]

    def export_json(self, limit: int = 1000) -> str:
        rows = self.recent_screenings(limit)
        return json.dumps([r.__dict__ for r in rows], default=str, indent=2)

    def export_csv(self, limit: int = 1000) -> str:
        rows = self.recent_screenings(limit)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "date", "patient_name", "phone", "grade", "grade_label",
                        "confidence", "referable", "sms_status"])
        for r in rows:
            writer.writerow([r.id, r.created_at.isoformat(), r.patient_name, r.phone or "",
                            r.grade, Grade(r.grade).label, f"{r.confidence:.4f}",
                            "yes" if r.referable else "no", r.sms_status or ""])
        return buf.getvalue()

    @staticmethod
    def _get_or_create_patient(s: Session, info: PatientInfo) -> int:
        name = " ".join(info.full_name.split())
        query = select(Patient).where(Patient.full_name == name, Patient.phone == info.phone)
        patient = s.scalar(query.with_for_update())
        if patient is None:
            patient = Patient(full_name=name, phone=info.phone, age=info.age, sex=info.sex)
            s.add(patient)
            s.flush()
        else:
            patient.age = info.age or patient.age
            patient.sex = info.sex or patient.sex
        return patient.id


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")
