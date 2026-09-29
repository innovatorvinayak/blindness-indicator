"""JSON API consumed by the Next.js frontend.

The UI is a separate Next.js app (``frontend/``) which proxies ``/api/*``
here, so the session cookie stays same-origin and no CORS handling or token
juggling is needed. Everything the UI can do goes through these endpoints;
they are thin wrappers over ScreeningService/Database, which hold the actual
business rules.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from drscreen import chat, vision
from drscreen import stats as stats_module
from drscreen.config import Settings, update_env
from drscreen.grading import Grade
from drscreen.preprocessing import assess_quality, load_image
from drscreen.retina import check_fundus
from drscreen.security import MIN_PASSWORD_LENGTH
from drscreen.storage import DuplicateUsernameError, OperatorInfo, PatientInfo
from drscreen.web.auth import COOKIE_NAME, MAX_AGE_SECONDS, current_operator, encode_session

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _require(request: Request) -> OperatorInfo:
    operator = current_operator(request)
    if operator is None:
        raise HTTPException(401, "Not signed in.")
    return operator


def _grade_payload(grade_value: int) -> dict:
    grade = Grade(grade_value)
    return {"grade": int(grade), "label": grade.label, "advice": grade.advice,
            "referable_grade": grade.is_referable}


# -- session ------------------------------------------------------------------
class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(request: Request, body: LoginBody) -> JSONResponse:
    operator = request.app.state.db.authenticate(body.username, body.password)
    if operator is None:
        raise HTTPException(401, "Incorrect username or password.")
    token = encode_session(request.app.state.serializer, operator)
    response = JSONResponse({"id": operator.id, "username": operator.username})
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
                        max_age=MAX_AGE_SECONDS, path="/")
    return response


class SignupBody(BaseModel):
    username: str
    password: str
    code: str = ""


@router.post("/signup")
def signup(request: Request, body: SignupBody) -> JSONResponse:
    """Create an operator account and sign them straight in.

    Gated by settings because an operator can read every patient record:
    signup can be turned off entirely, or put behind a shared code.
    """
    settings: Settings = request.app.state.settings
    if not settings.allow_signup:
        raise HTTPException(
            403, "Self sign-up is disabled. Ask an administrator to create your account.")
    if settings.signup_code and body.code.strip() != settings.signup_code:
        raise HTTPException(403, "That sign-up code isn't right.")

    username = body.username.strip()
    if len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters.")
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    try:
        operator = request.app.state.db.create_operator(username, body.password)
    except DuplicateUsernameError:
        raise HTTPException(409, f"The username {username!r} is already taken.") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    token = encode_session(request.app.state.serializer, operator)
    response = JSONResponse({"id": operator.id, "username": operator.username})
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
                        max_age=MAX_AGE_SECONDS, path="/")
    return response


@router.post("/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/me")
def me(request: Request) -> dict:
    operator = _require(request)
    return {"id": operator.id, "username": operator.username}


@router.get("/status")
def status(request: Request) -> dict:
    """Everything the shell needs to render: who's signed in, whether the
    model actually loaded, and whether the chat assistant is reachable."""
    settings: Settings = request.app.state.settings
    operator = current_operator(request)
    return {
        "operator": {"id": operator.id, "username": operator.username} if operator else None,
        "clinic_name": settings.clinic_name,
        "model_ready": request.app.state.service is not None,
        "model_error": request.app.state.model_error,
        "model_path": str(settings.model_path),
        "chat_available": chat.is_reachable(settings.ollama),
        "referral_threshold": settings.referral_threshold,
        "signup_enabled": settings.allow_signup,
        "signup_requires_code": bool(settings.signup_code),
    }


# -- screening ----------------------------------------------------------------
@router.post("/quality-check")
async def quality_check(request: Request, image: UploadFile) -> dict:
    _require(request)
    data = await image.read()
    try:
        img = load_image(data)
    except Exception as exc:
        raise HTTPException(400, f"Couldn't read that image: {exc}") from None
    report = assess_quality(img)
    fundus = check_fundus(img)
    return {
        "width": report.width,
        "height": report.height,
        "warnings": list(report.warnings),
        "fundus": fundus.to_dict(),
    }


@router.post("/screen")
async def screen(
    request: Request,
    image: UploadFile,
    full_name: str = Form(...),
    phone: str = Form(""),
    age: str = Form(""),
    sex: str = Form(""),
    send_sms: bool = Form(False),
) -> dict:
    operator = _require(request)
    service = request.app.state.service
    if service is None:
        raise HTTPException(503, request.app.state.model_error or "Model not loaded.")

    suffix = Path(image.filename or "upload.jpg").suffix or ".jpg"
    data = await image.read()

    # Refuse to grade anything that isn't a retina. The model would return a
    # confident-looking severity for a photo of a car park, and an operator
    # has no way to tell that result apart from a real one.
    try:
        fundus = check_fundus(load_image(data))
    except Exception as exc:
        raise HTTPException(400, f"Couldn't read that image: {exc}") from None
    if not fundus.is_fundus:
        request.app.state.rejected_uploads += 1
        raise HTTPException(
            status_code=422,
            detail={
                "error": "not_a_fundus_image",
                "message": "This does not look like a retinal fundus photograph, "
                           "so it was not graded.",
                "reasons": list(fundus.reasons),
                "check": fundus.to_dict(),
            },
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        patient = PatientInfo(
            full_name=full_name,
            phone=service.normalize_phone(phone) if phone.strip() else None,
            age=int(age) if age.strip() else None,
            sex=(sex or "").strip().upper() or None,
        )
    except ValueError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from None

    try:
        outcome = service.screen(tmp_path, patient, operator, send_sms=send_sms)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    finally:
        tmp_path.unlink(missing_ok=True)

    prediction = outcome.prediction
    return {
        "screening_id": outcome.screening_id,
        "grade": int(prediction.grade),
        "label": prediction.grade.label,
        "advice": prediction.grade.advice,
        "confidence": prediction.confidence,
        "probabilities": list(prediction.probabilities),
        "referral_probability": prediction.referral_probability,
        "referable": prediction.referable,
        "warnings": list(prediction.warnings),
        "model_version": prediction.model_version,
        "sms_status": outcome.sms.status if outcome.sms else None,
    }


# -- history / reports ---------------------------------------------------------
@router.get("/screenings")
def screenings(request: Request, q: str = "", referrals_only: bool = False,
               limit: int = 500) -> list[dict]:
    _require(request)
    rows = request.app.state.db.recent_screenings(limit)
    needle = q.strip().lower()
    if needle:
        rows = [r for r in rows
                if needle in r.patient_name.lower() or needle in (r.phone or "").lower()]
    if referrals_only:
        rows = [r for r in rows if r.referable]
    return [{
        "id": r.id,
        "created_at": r.created_at.isoformat(),
        "patient_name": r.patient_name,
        "phone": r.phone,
        "confidence": r.confidence,
        "referable": r.referable,
        "sms_status": r.sms_status,
        **_grade_payload(r.grade),
    } for r in rows]


@router.get("/stats")
def dashboard_stats(request: Request) -> dict:
    """Everything the dashboard widgets need, in one round trip."""
    _require(request)
    settings: Settings = request.app.state.settings
    payload = stats_module.build(request.app.state.db).to_dict()

    predictor = getattr(request.app.state.service, "predictor", None)
    payload["model"] = {
        "ready": request.app.state.service is not None,
        "error": request.app.state.model_error,
        "version": predictor.metadata.version if predictor else None,
        "architecture": predictor.metadata.arch if predictor else None,
        "device": str(predictor.device) if predictor else None,
        "tta": settings.tta,
        "channel_order": predictor.metadata.channel_order if predictor else None,
    }
    payload["config"] = {
        "clinic_name": settings.clinic_name,
        "referral_threshold": settings.referral_threshold,
        "sms_enabled": settings.sms_enabled,
        "sms_provider": _sms_provider(settings),
    }
    payload["assistant"] = {
        "chat_available": chat.is_reachable(settings.ollama),
        "chat_model": settings.ollama.model,
        "vision_available": vision.is_available(settings.ollama),
        "vision_model": settings.ollama.vision_model,
    }
    payload["rejected_uploads"] = request.app.state.rejected_uploads
    return payload


def _sms_provider(settings: Settings) -> str:
    if not settings.sms_enabled:
        return "disabled"
    if settings.twilio.configured:
        return "twilio"
    if settings.fast2sms.configured:
        return "fast2sms"
    return "dry-run"


@router.get("/screenings/export.csv")
def export_csv(request: Request) -> PlainTextResponse:
    _require(request)
    return PlainTextResponse(
        request.app.state.db.export_csv(2000), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=drscreen_history.csv"},
    )


@router.get("/screenings/{screening_id}")
def screening_detail(request: Request, screening_id: int) -> dict:
    _require(request)
    db = request.app.state.db
    detail = db.get_screening_detail(screening_id)
    if detail is None:
        raise HTTPException(404, "No such screening.")
    history = db.patient_history(detail.patient_name, detail.phone, exclude_id=screening_id)
    return {
        "id": detail.id,
        "created_at": detail.created_at.isoformat(),
        "patient_name": detail.patient_name,
        "phone": detail.phone,
        "age": detail.age,
        "sex": detail.sex,
        "operator_username": detail.operator_username,
        "image_sha256": detail.image_sha256,
        "confidence": detail.confidence,
        "referral_probability": detail.referral_probability,
        "referable": detail.referable,
        "probabilities": list(detail.probabilities),
        "model_version": detail.model_version,
        "sms_status": detail.sms_status,
        **_grade_payload(detail.grade),
        "history": [{
            "id": h.id,
            "created_at": h.created_at.isoformat(),
            "confidence": h.confidence,
            "referable": h.referable,
            **_grade_payload(h.grade),
        } for h in history],
    }


@router.get("/screenings/{screening_id}/image")
def screening_image(request: Request, screening_id: int) -> FileResponse:
    _require(request)
    detail = request.app.state.db.get_screening_detail(screening_id)
    if detail is None or not Path(detail.image_path).is_file():
        raise HTTPException(404, "Image not available.")
    return FileResponse(detail.image_path)


@router.get("/screenings/{screening_id}/report.html")
def screening_report(request: Request, screening_id: int) -> FileResponse:
    _require(request)
    service = request.app.state.service
    if service is None:
        raise HTTPException(503, "Model not loaded; cannot build a report right now.")
    try:
        path = service.build_report(screening_id)
    except KeyError:
        raise HTTPException(404, "No such screening.") from None
    return FileResponse(path, media_type="text/html",
                        filename=f"drscreen_report_{screening_id:06d}.html")


# -- settings -------------------------------------------------------------------
class SettingsBody(BaseModel):
    clinic_name: str
    default_country_code: str
    referral_threshold: float
    sms_enabled: bool
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    fast2sms_api_key: str = ""
    ollama_host: str
    ollama_model: str
    ollama_enabled: bool


@router.get("/settings")
def get_settings(request: Request) -> dict:
    _require(request)
    s: Settings = request.app.state.settings
    return {
        "clinic_name": s.clinic_name,
        "default_country_code": s.default_country_code,
        "referral_threshold": s.referral_threshold,
        "sms_enabled": s.sms_enabled,
        "twilio_account_sid": s.twilio.account_sid or "",
        "twilio_auth_token": s.twilio.auth_token or "",
        "twilio_from_number": s.twilio.from_number or "",
        "fast2sms_api_key": s.fast2sms.api_key or "",
        "ollama_host": s.ollama.host,
        "ollama_model": s.ollama.model,
        "ollama_enabled": s.ollama.enabled,
    }


@router.post("/settings")
def save_settings(request: Request, body: SettingsBody) -> dict:
    _require(request)
    if not 0.0 < body.referral_threshold < 1.0:
        raise HTTPException(400, "Referral threshold must be between 0 and 1.")
    update_env({
        "DRS_CLINIC_NAME": body.clinic_name,
        "DRS_DEFAULT_COUNTRY_CODE": body.default_country_code,
        "DRS_REFERRAL_THRESHOLD": str(body.referral_threshold),
        "DRS_SMS_ENABLED": "true" if body.sms_enabled else "false",
        "TWILIO_ACCOUNT_SID": body.twilio_account_sid,
        "TWILIO_AUTH_TOKEN": body.twilio_auth_token,
        "TWILIO_FROM_NUMBER": body.twilio_from_number,
        "FAST2SMS_API_KEY": body.fast2sms_api_key,
        "OLLAMA_HOST": body.ollama_host,
        "OLLAMA_MODEL": body.ollama_model,
        "OLLAMA_ENABLED": "true" if body.ollama_enabled else "false",
    })
    new_settings = Settings.from_env()
    request.app.state.settings = new_settings
    if request.app.state.service is not None:
        from drscreen.notify import build_sender

        request.app.state.service.sms = build_sender(new_settings)
        request.app.state.service.settings = new_settings
    return {"ok": True}


# -- chat --------------------------------------------------------------------------
class ChatTurn(BaseModel):
    role: str
    content: str


class ChatBody(BaseModel):
    question: str
    history: list[ChatTurn] = []


@router.post("/chat/{screening_id}")
def ask_chat(request: Request, screening_id: int, body: ChatBody) -> dict:
    _require(request)
    detail = request.app.state.db.get_screening_detail(screening_id)
    if detail is None:
        raise HTTPException(404, "No such screening.")
    context = chat.ScreeningContext(grade=detail.grade, confidence=detail.confidence,
                                    referable=detail.referable)
    try:
        answer = chat.ask(body.question, context, request.app.state.settings.ollama,
                          [turn.model_dump() for turn in body.history])
    except chat.ChatUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    return {"answer": answer}


@router.get("/health")
def health(response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
