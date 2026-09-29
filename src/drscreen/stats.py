"""Aggregations for the dashboard.

All derived from the screenings table in one read, rather than a query per
widget — the dashboard asks for everything at once and a screening camp's
table is small enough that a single pass is cheaper than twenty round trips.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from drscreen.grading import NUM_GRADES, Grade
from drscreen.storage import Database, ScreeningRow

TREND_DAYS = 14


@dataclass(frozen=True)
class DashboardStats:
    total: int
    referable: int
    referral_rate: float
    unique_patients: int
    screened_today: int
    screened_week: int
    grade_counts: list[int]
    grade_percentages: list[float]
    mean_confidence: float
    low_confidence_count: int
    sms_sent: int
    sms_failed: int
    sms_not_sent: int
    daily: list[dict]
    last_screening_at: str | None
    busiest_day: str | None
    severe_queue: list[dict]
    recent: list[dict]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "referable": self.referable,
            "referral_rate": round(self.referral_rate, 4),
            "unique_patients": self.unique_patients,
            "screened_today": self.screened_today,
            "screened_week": self.screened_week,
            "grade_counts": self.grade_counts,
            "grade_percentages": [round(p, 4) for p in self.grade_percentages],
            "mean_confidence": round(self.mean_confidence, 4),
            "low_confidence_count": self.low_confidence_count,
            "sms_sent": self.sms_sent,
            "sms_failed": self.sms_failed,
            "sms_not_sent": self.sms_not_sent,
            "daily": self.daily,
            "last_screening_at": self.last_screening_at,
            "busiest_day": self.busiest_day,
            "severe_queue": self.severe_queue,
            "recent": self.recent,
        }


def build(db: Database, limit: int = 2000) -> DashboardStats:
    rows = db.recent_screenings(limit)
    total = len(rows)

    if total == 0:
        empty_daily = _daily_series([], TREND_DAYS)
        return DashboardStats(
            total=0, referable=0, referral_rate=0.0, unique_patients=0,
            screened_today=0, screened_week=0,
            grade_counts=[0] * NUM_GRADES, grade_percentages=[0.0] * NUM_GRADES,
            mean_confidence=0.0, low_confidence_count=0,
            sms_sent=0, sms_failed=0, sms_not_sent=0,
            daily=empty_daily, last_screening_at=None, busiest_day=None,
            severe_queue=[], recent=[],
        )

    today = datetime.now().date()
    week_ago = today - timedelta(days=6)

    grade_counts = [0] * NUM_GRADES
    for row in rows:
        grade_counts[row.grade] += 1

    referable = sum(1 for r in rows if r.referable)
    confidences = [r.confidence for r in rows]

    sms = Counter(r.sms_status or "not_sent" for r in rows)

    # Worst first, then oldest first — the ones waiting longest at the top
    # severity band are the ones most at risk of being missed.
    severe = sorted(
        (r for r in rows if r.grade >= Grade.SEVERE),
        key=lambda r: (-r.grade, r.created_at),
    )[:8]

    day_counts = Counter(r.created_at.date() for r in rows)
    busiest = max(day_counts.items(), key=lambda kv: kv[1])[0] if day_counts else None

    return DashboardStats(
        total=total,
        referable=referable,
        referral_rate=referable / total,
        unique_patients=len({(r.patient_name.lower(), r.phone) for r in rows}),
        screened_today=sum(1 for r in rows if r.created_at.date() == today),
        screened_week=sum(1 for r in rows if r.created_at.date() >= week_ago),
        grade_counts=grade_counts,
        grade_percentages=[c / total for c in grade_counts],
        mean_confidence=sum(confidences) / total,
        low_confidence_count=sum(1 for c in confidences if c < 0.60),
        sms_sent=sms.get("sent", 0),
        sms_failed=sms.get("failed", 0),
        sms_not_sent=sms.get("not_sent", 0) + sms.get("dry_run", 0),
        daily=_daily_series(rows, TREND_DAYS),
        last_screening_at=rows[0].created_at.isoformat(),
        busiest_day=busiest.isoformat() if busiest else None,
        severe_queue=[_row_summary(r) for r in severe],
        recent=[_row_summary(r) for r in rows[:8]],
    )


def _daily_series(rows: list[ScreeningRow], days: int) -> list[dict]:
    """Screenings and referrals per day, zero-filled so the chart has no gaps."""
    today = date.today()
    window = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    by_day: dict[date, list[ScreeningRow]] = {day: [] for day in window}
    for row in rows:
        day = row.created_at.date()
        if day in by_day:
            by_day[day].append(row)
    return [
        {
            "date": day.isoformat(),
            "label": day.strftime("%d %b"),
            "total": len(items),
            "referable": sum(1 for r in items if r.referable),
        }
        for day, items in by_day.items()
    ]


def _row_summary(row: ScreeningRow) -> dict:
    grade = Grade(row.grade)
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "patient_name": row.patient_name,
        "phone": row.phone,
        "grade": int(grade),
        "label": grade.label,
        "confidence": round(row.confidence, 4),
        "referable": row.referable,
        "sms_status": row.sms_status,
    }
