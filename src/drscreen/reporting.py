"""Full detailed screening reports: patient, image, grade, probability
breakdown, referral recommendation, and model provenance in one document.

Reports are self-contained HTML (the fundus image is embedded as a base64
data URI), so a single file can be emailed, archived, or printed to PDF from
any browser without shipping the original image alongside it — useful since
this is meant to leave the clinic and reach a referral ophthalmologist.
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from pathlib import Path

from drscreen.grading import Grade
from drscreen.gui.branding import render_logo_png_bytes
from drscreen.storage import ScreeningDetail

# Deliberately not importing drscreen.gui.theme: the GUI's tkinter colour
# system doesn't apply to HTML/CSS, but the two brand colours are the same
# source of truth, restated here for the web-safe half of the design system.
EMERALD = "#064E3B"
CREAM = "#F8E7C9"

_GRADE_COLORS = ("#1e7e46", "#6b8e23", "#c9971f", "#c96a1f", "#b23a3a")

_MIME_BY_SUFFIX = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff",
}


@dataclass(frozen=True)
class ReportContext:
    """Non-database context a report needs that isn't stored per-screening."""

    clinic_name: str
    referral_threshold: float
    report_id: str | None = None  # defaults to f"DRS-{screening.id:06d}"


def build_report_html(screening: ScreeningDetail, ctx: ReportContext) -> str:
    """Render a complete, self-contained HTML report for one screening."""
    grade = Grade(screening.grade)
    report_id = ctx.report_id or f"DRS-{screening.id:06d}"
    image_data_uri = _embed_image(screening.image_path)
    rows = "\n".join(_probability_row(Grade(g), p, g == grade)
                     for g, p in enumerate(screening.probabilities))
    referral_html = _referral_block(screening, ctx.referral_threshold)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Screening report {html.escape(report_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <header>
    <div class="brand">
      <img class="mark" src="{_logo_data_uri()}" alt="" aria-hidden="true">
      <div>
        <div class="clinic">{html.escape(ctx.clinic_name)}</div>
        <div class="subtitle">Diabetic Retinopathy Screening Report</div>
      </div>
    </div>
    <div class="report-meta">
      <div><span>Report ID</span>{html.escape(report_id)}</div>
      <div><span>Date</span>{screening.created_at:%d %b %Y, %H:%M}</div>
      <div><span>Operator</span>{html.escape(screening.operator_username or "—")}</div>
    </div>
  </header>

  <section class="grid">
    <div class="card">
      <h2>Patient</h2>
      <dl>
        <dt>Name</dt><dd>{html.escape(screening.patient_name)}</dd>
        <dt>Mobile</dt><dd>{html.escape(screening.phone or "—")}</dd>
        <dt>Age</dt><dd>{screening.age if screening.age is not None else "—"}</dd>
        <dt>Sex</dt><dd>{html.escape(_sex_label(screening.sex))}</dd>
      </dl>
    </div>
    <div class="card image-card">
      <h2>Fundus image</h2>
      {f'<img src="{image_data_uri}" alt="Fundus photograph">' if image_data_uri
        else '<div class="no-image">Image not available</div>'}
      <div class="hash">SHA-256 {html.escape(screening.image_sha256 or "—")}</div>
    </div>
  </section>

  <section class="card assessment">
    <h2>AI assessment</h2>
    <div class="grade-banner" style="--grade-color:{_GRADE_COLORS[grade]}">
      <div class="grade-num">{int(grade)}</div>
      <div>
        <div class="grade-label">{html.escape(grade.label)}</div>
        <div class="grade-sub">Confidence {screening.confidence:.1%}
          &nbsp;·&nbsp; P(referable) {screening.referral_probability:.1%}</div>
      </div>
    </div>
    {referral_html}
    <p class="advice">{html.escape(grade.advice)}</p>

    <table class="probabilities">
      <thead><tr><th>Grade</th><th>Meaning</th><th>Probability</th><th></th></tr></thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </section>

  <section class="card technical">
    <h2>Technical details</h2>
    <dl class="two-col">
      <dt>Model architecture</dt><dd>ResNet-152 (PyTorch)</dd>
      <dt>Model version</dt><dd>{html.escape(screening.model_version)}</dd>
      <dt>Referral threshold</dt><dd>P(grade ≥ Moderate) ≥ {ctx.referral_threshold:.0%}</dd>
      <dt>SMS status</dt><dd>{html.escape(screening.sms_status or "not sent")}</dd>
    </dl>
  </section>

  <footer>
    <p><strong>This is an AI-assisted screening aid, not a medical diagnosis.</strong>
    The prediction above should be confirmed by a qualified ophthalmologist before
    any clinical decision is made. Screening report generated automatically by
    drscreen — see docs/MODEL_CARD.md in the project for validated performance
    and known limitations.</p>
  </footer>
</div>
</body>
</html>
"""


def save_report(screening: ScreeningDetail, ctx: ReportContext, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"screening_{screening.id:06d}.html"
    path.write_text(build_report_html(screening, ctx), encoding="utf-8")
    return path


def _probability_row(grade: Grade, probability: float, is_predicted: bool) -> str:
    pct = max(0.0, min(1.0, probability)) * 100
    css_class = "predicted" if is_predicted else ""
    return f"""<tr class="{css_class}">
      <td>{int(grade)}</td>
      <td>{html.escape(grade.label)}</td>
      <td class="pct">{probability:.1%}</td>
      <td class="bar-cell"><div class="bar-track">
        <div class="bar-fill" style="width:{pct:.1f}%; background:{_GRADE_COLORS[grade]}"></div>
      </div></td>
    </tr>"""


def _referral_block(screening: ScreeningDetail, threshold: float) -> str:
    if screening.referable:
        return (f'<div class="referral refer">⬤ REFER TO OPHTHALMOLOGIST'
               f'<span>P(referable) {screening.referral_probability:.1%} ≥ '
               f'threshold {threshold:.0%}</span></div>')
    return (f'<div class="referral clear">✓ No referral required'
           f'<span>P(referable) {screening.referral_probability:.1%} &lt; '
           f'threshold {threshold:.0%}</span></div>')


def _sex_label(code: str | None) -> str:
    return {"M": "Male", "F": "Female", "O": "Other"}.get(code or "", "—")


def _logo_data_uri() -> str:
    data = base64.b64encode(render_logo_png_bytes(96)).decode("ascii")
    return f"data:image/png;base64,{data}"


def _embed_image(path: str) -> str | None:
    file = Path(path)
    if not file.is_file():
        return None
    mime = _MIME_BY_SUFFIX.get(file.suffix.lower(), "application/octet-stream")
    data = base64.b64encode(file.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


_CSS = f"""
:root {{
  --emerald: {EMERALD};
  --cream: {CREAM};
  --ink: #16261f;
  --muted: #5c6b62;
  --border: #d9cfa8;
  --surface: #fffdf6;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: #ece3cf;
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  color: var(--ink);
}}
.page {{ max-width: 880px; margin: 24px auto; background: var(--surface);
  border-radius: 14px; overflow: hidden; box-shadow: 0 12px 40px rgba(6,78,59,0.18); }}
header {{ background: var(--emerald); color: var(--cream); padding: 28px 32px;
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; }}
.brand {{ display: flex; align-items: center; gap: 14px; }}
.mark {{ width: 44px; height: 44px; border-radius: 12px; flex: none;
  box-shadow: 0 2px 8px rgba(0,0,0,0.25); }}
.clinic {{ font-size: 19px; font-weight: 700; }}
.subtitle {{ font-size: 12.5px; opacity: .85; margin-top: 2px; }}
.report-meta {{ text-align: right; font-size: 12.5px; line-height: 1.6; }}
.report-meta span {{ display: block; opacity: .7; font-size: 10.5px;
  text-transform: uppercase; letter-spacing: .06em; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 24px 32px 0; }}
@media (max-width: 640px) {{ .grid {{ grid-template-columns: 1fr; }} }}
.card {{ background: #fbf6e8; border: 1px solid var(--border); border-radius: 12px;
  padding: 18px 20px; }}
.card h2 {{ margin: 0 0 12px; font-size: 13px; text-transform: uppercase;
  letter-spacing: .06em; color: var(--emerald); }}
dl {{ margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; }}
dl.two-col {{ grid-template-columns: 1fr 1fr; }}
dt {{ color: var(--muted); font-size: 12.5px; }}
dd {{ margin: 0; font-size: 14px; font-weight: 600; }}
.image-card img {{ width: 100%; border-radius: 10px; display: block;
  border: 1px solid var(--border); }}
.no-image {{ padding: 40px; text-align: center; color: var(--muted); }}
.hash {{ margin-top: 8px; font-size: 10.5px; color: var(--muted); word-break: break-all; }}
.assessment {{ margin: 20px 32px 0; }}
.grade-banner {{ display: flex; align-items: center; gap: 16px; padding: 14px 16px;
  border-radius: 10px; background: color-mix(in srgb, var(--grade-color) 14%, white); }}
.grade-num {{ width: 44px; height: 44px; border-radius: 50%; background: var(--grade-color);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 700; flex: none; }}
.grade-label {{ font-size: 20px; font-weight: 700; color: var(--grade-color); }}
.grade-sub {{ font-size: 12.5px; color: var(--muted); margin-top: 2px; }}
.referral {{ margin-top: 14px; padding: 10px 14px; border-radius: 8px;
  font-weight: 700; font-size: 13.5px; display: flex; justify-content: space-between;
  align-items: center; flex-wrap: wrap; gap: 6px; }}
.referral span {{ font-weight: 500; font-size: 11.5px; opacity: .8; }}
.referral.refer {{ background: #fbe2df; color: #9c2b2b; }}
.referral.clear {{ background: #e3f3e6; color: #1e6b34; }}
.advice {{ margin: 14px 0 6px; font-size: 14px; }}
table.probabilities {{ width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 13px; }}
table.probabilities th {{ text-align: left; font-size: 11px; text-transform: uppercase;
  letter-spacing: .05em; color: var(--muted); padding: 6px 8px;
  border-bottom: 1px solid var(--border); }}
table.probabilities td {{ padding: 7px 8px; border-bottom: 1px solid #eee2c4; }}
tr.predicted td {{ font-weight: 700; }}
.pct {{ width: 60px; }}
.bar-cell {{ width: 40%; }}
.bar-track {{ background: #eee2c4; border-radius: 6px; height: 8px; overflow: hidden; }}
.bar-fill {{ height: 100%; border-radius: 6px; }}
.technical {{ margin: 20px 32px 0; }}
footer {{ margin: 24px 32px 32px; padding-top: 16px; border-top: 1px solid var(--border);
  font-size: 11.5px; color: var(--muted); line-height: 1.5; }}
@media print {{ body {{ background: #fff; }} .page {{ box-shadow: none; margin: 0; }} }}
"""
