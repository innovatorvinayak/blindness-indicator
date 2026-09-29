"""A scoped chat assistant, backed by a local Ollama model, that explains one
screening result in plain language.

Deliberately narrow: the system prompt fixes the model, patient-safe context,
and grade/advice from the actual prediction, and instructs it to answer only
questions about *this* result — not open-ended medical advice, and never to
contradict or soften the referral recommendation the classifier already gave.
This is an explanation aid, not a second opinion.

Ollama is a separate local process (``ollama serve``, or the ``ollama``
container in docker-compose.yml) — this module is a thin HTTP client over its
REST API, so the assistant degrades gracefully (a clear error message, not a
crash) when Ollama isn't running or the model hasn't been pulled yet.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from drscreen.config import OllamaSettings
from drscreen.grading import Grade

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a patient-facing assistant embedded in a diabetic \
retinopathy (DR) screening tool called drscreen. You are shown the AI \
screening result for ONE patient below. Your only job is to explain that \
result in short, plain, reassuring language for a non-medical reader.

Rules you must always follow:
- Only discuss the screening result given below. If asked about anything \
else (other conditions, medications, dosages, unrelated symptoms), say you \
can only discuss this screening result and suggest they ask their doctor.
- Never contradict, soften, or second-guess the referral recommendation \
below. If it says refer to an ophthalmologist, your answer must not talk \
the patient out of that.
- Make clear this is an AI screening aid, not a diagnosis, whenever it's \
relevant.
- Keep answers to 3-4 short sentences unless the patient explicitly asks \
for more detail.
- Never invent details about the image or patient that aren't given below.

Screening result:
- Grade: {grade} ({label})
- Confidence: {confidence:.0%}
- Referral recommendation: {referral_line}
- Advice: {advice}
"""


@dataclass(frozen=True)
class ScreeningContext:
    grade: int
    confidence: float
    referable: bool

    @property
    def prompt_block(self) -> str:
        grade = Grade(self.grade)
        referral_line = (
            "Refer to an ophthalmologist" if self.referable
            else "No referral needed at this time"
        )
        return _SYSTEM_PROMPT.format(
            grade=int(grade), label=grade.label, confidence=self.confidence,
            referral_line=referral_line, advice=grade.advice,
        )


class ChatUnavailable(RuntimeError):
    """Raised when Ollama can't be reached or the model isn't available."""


def ask(question: str, context: ScreeningContext, settings: OllamaSettings,
        history: list[dict[str, str]] | None = None) -> str:
    """Ask the assistant one question about a specific screening result.

    ``history`` is prior turns as ``[{"role": "user"/"assistant", "content": ...}]``,
    so a conversation can carry follow-up questions.
    """
    if not settings.enabled:
        raise ChatUnavailable("The chat assistant is disabled (OLLAMA_ENABLED=false).")

    messages = [{"role": "system", "content": context.prompt_block}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})

    payload = json.dumps({
        "model": settings.model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3},
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{settings.host.rstrip('/')}/api/chat", data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        log.warning("Ollama request failed: %s", exc)
        raise ChatUnavailable(
            f"Can't reach the chat assistant at {settings.host}. "
            "Is Ollama running (`ollama serve`) and has the model been pulled "
            f"(`ollama pull {settings.model}`)?"
        ) from exc
    except (json.JSONDecodeError, KeyError) as exc:
        log.warning("Unexpected Ollama response: %s", exc)
        raise ChatUnavailable("The chat assistant returned an unexpected response.") from exc

    try:
        return data["message"]["content"].strip()
    except (KeyError, TypeError) as exc:
        raise ChatUnavailable("The chat assistant returned an empty response.") from exc


def is_reachable(settings: OllamaSettings, timeout: float = 2.0) -> bool:
    """Cheap health check used by the web UI to hide/show the chat widget
    and by ``drscreen doctor``."""
    if not settings.enabled:
        return False
    try:
        with urllib.request.urlopen(f"{settings.host.rstrip('/')}/api/tags", timeout=timeout):
            return True
    except urllib.error.URLError:
        return False
