"""Vision-model support via Ollama: confirm an upload really is a fundus
photograph, and describe what is visible in it for the report.

Two things this is emphatically *not*:

* **It does not grade.** The ResNet-152 classifier decides severity. A
  general-purpose vision model is not a validated DR grader, and anything it
  says about severity is ignored — its output is descriptive only, and the
  report labels it as such.
* **It is not required.** Ollama is optional, the model may not be pulled,
  and vision models are slow. Every entry point here degrades to ``None``
  rather than raising, and callers carry on without it.

It earns its place on the *gate*: colour statistics alone cannot separate a
washed-out fundus photograph from a warm-lit close-up of skin (see
:mod:`drscreen.retina`). Something that understands image content can.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from drscreen.config import OllamaSettings

log = logging.getLogger(__name__)

# Vision models are heavyweight; give them longer than the text assistant.
_TIMEOUT = 120

_CONFIRM_PROMPT = """You are shown one image. Answer ONLY with strict JSON, no prose:

{"is_retina": true|false, "confidence": 0.0-1.0, "what_it_is": "<short description>"}

"is_retina" must be true only if this is a retinal fundus photograph — the
inside back surface of an eye, as captured by a fundus camera or
ophthalmoscope. It typically shows a round orange/red field with branching
blood vessels and a bright optic disc.

Photographs of a face, an eye from the outside, skin, scenery, documents,
screenshots or anything else must be false."""

_DESCRIBE_PROMPT = """You are shown a retinal fundus photograph. Describe ONLY what
is directly visible, as a trained grader would when writing observations.

Answer with strict JSON, no prose:

{
  "optic_disc": "<appearance and clarity, or 'not clearly visible'>",
  "vessels": "<calibre, tortuosity, any visible abnormality>",
  "macula": "<appearance, or 'not clearly visible'>",
  "lesions": ["<visible lesion types: haemorrhages, hard exudates,
               cotton wool spots, microaneurysms, neovascularisation>"],
  "image_quality": "<focus, illumination, field coverage>"
}

Report only what you can actually see. Use "not clearly visible" rather than
guessing. Do NOT state a diabetic retinopathy grade or severity — that is
decided by a separate validated classifier, not by you."""


@dataclass(frozen=True)
class FundusConfirmation:
    is_retina: bool
    confidence: float
    what_it_is: str


@dataclass(frozen=True)
class VisionFindings:
    optic_disc: str
    vessels: str
    macula: str
    lesions: tuple[str, ...]
    image_quality: str
    model: str

    def to_dict(self) -> dict:
        return {
            "optic_disc": self.optic_disc,
            "vessels": self.vessels,
            "macula": self.macula,
            "lesions": list(self.lesions),
            "image_quality": self.image_quality,
            "model": self.model,
            "disclaimer": "Descriptive observations from a vision model. "
                          "Not a diagnosis and not used to decide the grade.",
        }


def confirm_fundus(image_bytes: bytes, settings: OllamaSettings) -> FundusConfirmation | None:
    """Ask the vision model whether this image is a fundus photograph.

    Returns ``None`` when vision is unavailable, so the caller falls back to
    the heuristic verdict alone.
    """
    data = _generate(_CONFIRM_PROMPT, image_bytes, settings)
    if data is None:
        return None
    try:
        return FundusConfirmation(
            is_retina=bool(data["is_retina"]),
            confidence=float(data.get("confidence", 0.0)),
            what_it_is=str(data.get("what_it_is", "")).strip(),
        )
    except (KeyError, TypeError, ValueError):
        log.warning("vision model returned an unusable confirmation payload: %r", data)
        return None


def describe_findings(image_bytes: bytes, settings: OllamaSettings) -> VisionFindings | None:
    """Descriptive observations for the detailed report. Never a grade."""
    data = _generate(_DESCRIBE_PROMPT, image_bytes, settings)
    if data is None:
        return None
    lesions = data.get("lesions") or []
    if isinstance(lesions, str):
        lesions = [lesions]
    return VisionFindings(
        optic_disc=str(data.get("optic_disc", "not reported")),
        vessels=str(data.get("vessels", "not reported")),
        macula=str(data.get("macula", "not reported")),
        lesions=tuple(str(x) for x in lesions),
        image_quality=str(data.get("image_quality", "not reported")),
        model=settings.vision_model,
    )


def is_available(settings: OllamaSettings, timeout: float = 2.0) -> bool:
    """True when Ollama is reachable *and* the configured vision model is pulled."""
    if not settings.enabled or not settings.vision_model:
        return False
    try:
        with urllib.request.urlopen(
            f"{settings.host.rstrip('/')}/api/tags", timeout=timeout
        ) as response:
            tags = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return False
    names = {m.get("name", "") for m in tags.get("models", [])}
    # Ollama reports "llava:7b"; accept a bare "llava" in config too.
    return any(n == settings.vision_model or n.split(":")[0] == settings.vision_model
               for n in names)


def _generate(prompt: str, image_bytes: bytes, settings: OllamaSettings) -> dict | None:
    if not settings.enabled or not settings.vision_model:
        return None

    payload = json.dumps({
        "model": settings.vision_model,
        "prompt": prompt,
        "images": [base64.b64encode(image_bytes).decode("ascii")],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{settings.host.rstrip('/')}/api/generate", data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        log.info("vision model unavailable (%s); continuing without it", exc)
        return None
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("vision request failed: %s", exc)
        return None

    try:
        # `format: json` makes the model emit JSON as its response text.
        return json.loads(body["response"])
    except (KeyError, json.JSONDecodeError):
        log.warning("vision model did not return JSON: %r", str(body)[:200])
        return None
