"""Signed-cookie session auth, reusing the existing Operator/scrypt login.

No server-side session store: the cookie itself is a signed, timestamped
token (via itsdangerous) holding the operator's id and username. Signing
(not encryption) is enough here because the payload isn't secret, only
tamper-proof — the actual authentication already happened against the
password hash when the cookie was issued.
"""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.requests import Request

from drscreen.storage import OperatorInfo

COOKIE_NAME = "drs_session"
MAX_AGE_SECONDS = 60 * 60 * 12  # 12 hours; re-login after that


def make_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt="drscreen-session")


def encode_session(serializer: URLSafeTimedSerializer, operator: OperatorInfo) -> str:
    return serializer.dumps({"id": operator.id, "username": operator.username})


def decode_session(serializer: URLSafeTimedSerializer, token: str) -> OperatorInfo | None:
    try:
        data = serializer.loads(token, max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return OperatorInfo(id=data["id"], username=data["username"])


def current_operator(request: Request) -> OperatorInfo | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return decode_session(request.app.state.serializer, token)
