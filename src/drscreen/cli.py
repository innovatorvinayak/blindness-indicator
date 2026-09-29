"""Command-line interface: ``drscreen <command>`` (or ``python -m drscreen``)."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from pathlib import Path

from drscreen import __version__
from drscreen.config import PROJECT_ROOT, Settings

log = logging.getLogger("drscreen")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    settings = Settings.from_env()
    try:
        return args.handler(args, settings) or 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # surface a clean message; --verbose shows the traceback
        if args.verbose:
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drscreen", description=__doc__)
    parser.add_argument("--version", action="version", version=f"drscreen {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("web", help="serve the JSON API behind the Next.js UI")
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to accept connections "
                   "from other machines (e.g. behind a reverse proxy)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev only)")
    p.set_defaults(handler=cmd_web)

    p = sub.add_parser("predict", help="grade one or more images / folders")
    p.add_argument("images", nargs="+", type=Path)
    p.add_argument("--model", type=Path, help="checkpoint path (default: DRS_MODEL_PATH)")
    p.add_argument("--json", action="store_true", help="emit JSON lines")
    p.add_argument("--no-tta", action="store_true", help="disable flip test-time augmentation")
    p.set_defaults(handler=cmd_predict)

    p = sub.add_parser("train", help="fine-tune the classifier on APTOS 2019")
    p.add_argument("--csv", type=Path, required=True, help="train.csv with id_code,diagnosis")
    p.add_argument("--images", type=Path, required=True, help="directory of training images")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT / "models" / "classifier_v2.pt")
    p.add_argument("--arch", default="resnet152")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--image-size", type=int, default=224)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--init-from", type=Path, help="continue from an existing checkpoint")
    p.add_argument("--limit", type=int, help="train on a random subset (debugging)")
    p.set_defaults(handler=cmd_train)

    p = sub.add_parser("evaluate", help="score a checkpoint on a labelled set")
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--images", type=Path, required=True)
    p.add_argument("--model", type=Path)
    p.add_argument("--sweep", action="store_true",
                   help="report referral sensitivity/specificity across thresholds")
    p.add_argument("--output", type=Path, help="write the full report as JSON")
    p.set_defaults(handler=cmd_evaluate)

    p = sub.add_parser("init-db", help="create database tables")
    p.set_defaults(handler=cmd_init_db)

    p = sub.add_parser("add-user", help="create an operator account")
    p.add_argument("username")
    p.set_defaults(handler=cmd_add_user)

    p = sub.add_parser("history", help="show recent screenings")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.set_defaults(handler=cmd_history)

    p = sub.add_parser("sms-test", help="send a test SMS to verify Twilio setup")
    p.add_argument("phone")
    p.set_defaults(handler=cmd_sms_test)

    p = sub.add_parser("report", help="generate the full detailed report for a screening")
    p.add_argument("screening_id", type=int)
    p.add_argument("--open", action="store_true", help="open the report in the default browser")
    p.set_defaults(handler=cmd_report)

    p = sub.add_parser("batch-screen", help="screen a whole eye-camp folder in one pass")
    p.add_argument("--csv", type=Path, required=True,
                   help="columns: image,full_name,phone,age,sex (age/sex optional)")
    p.add_argument("--images", type=Path, required=True, help="directory holding the images")
    p.add_argument("--send-sms", action="store_true", help="text each patient their result")
    p.add_argument("--username", help="operator username to attribute these screenings to")
    p.set_defaults(handler=cmd_batch_screen)

    p = sub.add_parser("export-csv", help="export screening history as CSV")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("-n", "--limit", type=int, default=2000)
    p.set_defaults(handler=cmd_export_csv)

    p = sub.add_parser("convert-weights", help="convert a legacy classifier.pt to safe format")
    p.add_argument("src", type=Path)
    p.add_argument("dst", type=Path)
    p.add_argument("--trust", action="store_true",
                   help="confirm SRC is from a trusted source (it is unpickled)")
    p.set_defaults(handler=cmd_convert)

    p = sub.add_parser("doctor", help="check model, database and SMS configuration")
    p.set_defaults(handler=cmd_doctor)
    return parser


def cmd_web(args, settings: Settings) -> int:
    from drscreen.web.app import run

    run(settings, host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_predict(args, settings: Settings) -> int:
    from drscreen.inference import Predictor
    from drscreen.preprocessing import iter_image_files

    files = iter_image_files(args.images)
    if not files:
        raise FileNotFoundError("No images found.")
    predictor = Predictor.from_checkpoint(
        args.model or settings.model_path, settings.device,
        tta=settings.tta and not args.no_tta, referral_threshold=settings.referral_threshold)

    for pred in predictor.predict_batch(files):
        if args.json:
            print(json.dumps(pred.to_dict()))
            continue
        flag = "REFER" if pred.referable else "     "
        print(f"{Path(pred.source).name:<28} {flag}  grade {int(pred.grade)}  "
              f"{pred.grade.label:<24} {pred.confidence:6.1%}")
        for warning in pred.warnings:
            print(f"{'':<28} ! {warning}")
    return 0


def cmd_train(args, settings: Settings) -> int:
    from drscreen.training import TrainConfig, train

    cfg = TrainConfig(
        csv=args.csv, image_dir=args.images, output=args.output, arch=args.arch,
        image_size=args.image_size, epochs=args.epochs, batch_size=args.batch_size,
        lr=args.lr, workers=args.workers, seed=args.seed, device=settings.device,
        init_from=args.init_from, limit=args.limit,
    )
    summary = train(cfg)
    print(f"best validation QWK: {summary['best_val_qwk']:.4f} -> {cfg.output}")
    return 0


def cmd_evaluate(args, settings: Settings) -> int:
    from drscreen.data import read_labels
    from drscreen.inference import Predictor
    from drscreen.metrics import classification_report, referral_metrics

    samples = read_labels(args.csv, args.images)
    predictor = Predictor.from_checkpoint(args.model or settings.model_path, settings.device,
                                          tta=settings.tta,
                                          referral_threshold=settings.referral_threshold)
    preds = predictor.predict_batch([s.path for s in samples], batch_size=16)
    y_true = [s.grade for s in samples]
    y_pred = [int(p.grade) for p in preds]
    p_ref = [p.referral_probability for p in preds]
    report = classification_report(y_true, y_pred, p_ref, settings.referral_threshold)

    print(f"n={report['n']}  accuracy={report['accuracy']:.4f}  "
          f"QWK={report['quadratic_weighted_kappa']:.4f}")
    for label, m in report["per_class"].items():
        print(f"  {label:<26} precision={m['precision']:.3f} recall={m['recall']:.3f} "
              f"n={m['support']}")
    print("confusion matrix (rows=truth, cols=predicted):")
    for row in report["confusion_matrix"]:
        print("  " + " ".join(f"{v:5d}" for v in row))
    ref = report["referral"]
    print(f"referable DR @ {ref['threshold']:.2f}: sensitivity={ref['sensitivity']:.3f} "
          f"specificity={ref['specificity']:.3f} false_negatives={ref['false_negatives']}")

    if args.sweep:
        print("threshold  sensitivity  specificity  FN")
        report["sweep"] = []
        for t in [x / 20 for x in range(1, 20)]:
            m = referral_metrics(y_true, p_ref, t)
            report["sweep"].append(m.__dict__)
            print(f"  {t:5.2f}     {m.sensitivity:8.3f}     {m.specificity:8.3f}  "
                  f"{m.false_negatives:4d}")
    if args.output:
        args.output.write_text(json.dumps(report, indent=2))
    return 0


def cmd_init_db(args, settings: Settings) -> int:
    from drscreen.storage import Database

    Database(settings.database_url).create_schema()
    print(f"schema ready at {_redact(settings.database_url)}")
    return 0


def cmd_add_user(args, settings: Settings) -> int:
    from drscreen.storage import Database

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        raise ValueError("Passwords do not match.")
    db = Database(settings.database_url)
    db.create_schema()
    op = db.create_operator(args.username, password)
    print(f"created operator {op.username!r} (id={op.id})")
    return 0


def cmd_history(args, settings: Settings) -> int:
    from drscreen.grading import Grade
    from drscreen.storage import Database

    db = Database(settings.database_url)
    db.create_schema()
    for r in db.recent_screenings(args.limit):
        print(f"#{r.id:<5} {r.created_at:%Y-%m-%d %H:%M}  {r.patient_name:<24} "
              f"{Grade(r.grade).label:<24} {r.confidence:6.1%}  "
              f"{'REFER' if r.referable else '':<5} sms={r.sms_status or '-'}")
    return 0


def cmd_report(args, settings: Settings) -> int:
    import webbrowser

    from drscreen.reporting import ReportContext, save_report
    from drscreen.storage import Database

    # Reports are built straight from stored data, not through ScreeningService,
    # so generating one never needs the (large, slow-to-load) model weights.
    db = Database(settings.database_url)
    detail = db.get_screening_detail(args.screening_id)
    if detail is None:
        raise KeyError(f"No screening with id {args.screening_id}")
    ctx = ReportContext(clinic_name=settings.clinic_name,
                        referral_threshold=settings.referral_threshold)
    path = save_report(detail, ctx, settings.report_dir)
    print(f"report saved to {path}")
    if args.open:
        webbrowser.open(path.as_uri())
    return 0


def cmd_batch_screen(args, settings: Settings) -> int:
    """Screen a whole folder in one pass — the eye-camp workflow: one CSV
    mapping image filenames to patients, one command, every result recorded
    (and optionally texted) without touching the GUI per patient."""
    import csv as csv_module

    from drscreen.service import ScreeningService
    from drscreen.storage import PatientInfo

    with open(args.csv, newline="") as fh:
        reader = csv_module.DictReader(fh)
        required = {"image", "full_name"}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError(f"{args.csv} must have at least columns: {sorted(required)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{args.csv} has no data rows")

    service = ScreeningService.from_settings(settings)
    operator = None
    if args.username:
        from sqlalchemy import select

        from drscreen.storage import Operator, OperatorInfo

        with service.db.session() as s:
            row = s.scalar(select(Operator).where(Operator.username == args.username))
        if row is None:
            raise ValueError(f"No operator named {args.username!r}. Create one with add-user.")
        operator = OperatorInfo(row.id, row.username)

    ok = failed = 0
    for i, row in enumerate(rows, start=1):
        image_path = args.images / row["image"]
        if not image_path.is_file():
            print(f"[{i}/{len(rows)}] SKIP  {row['image']}: file not found")
            failed += 1
            continue
        try:
            patient = PatientInfo(
                full_name=row["full_name"],
                phone=service.normalize_phone(row.get("phone") or None),
                age=int(row["age"]) if row.get("age", "").strip() else None,
                sex=(row.get("sex") or "").strip().upper() or None,
            )
            outcome = service.screen(image_path, patient, operator, send_sms=args.send_sms)
        except Exception as exc:  # one bad row must not abort the whole camp
            print(f"[{i}/{len(rows)}] FAIL  {row['image']}: {exc}")
            failed += 1
            continue
        p = outcome.prediction
        flag = "REFER" if p.referable else "     "
        print(f"[{i}/{len(rows)}] {flag} #{outcome.screening_id:<5} {row['full_name']:<24} "
             f"{p.grade.label:<24} {p.confidence:5.1%}")
        ok += 1

    print(f"\n{ok} screened, {failed} failed, out of {len(rows)} rows.")
    return 0 if failed == 0 else 1


def cmd_export_csv(args, settings: Settings) -> int:
    from drscreen.storage import Database

    db = Database(settings.database_url)
    args.output.write_text(db.export_csv(args.limit), encoding="utf-8")
    print(f"exported to {args.output}")
    return 0


def cmd_sms_test(args, settings: Settings) -> int:
    from drscreen.notify import build_sender, normalize_phone

    sender = build_sender(settings)
    to = normalize_phone(args.phone, settings.default_country_code)
    result = sender.send(to, f"{settings.clinic_name}: test message from drscreen.")
    print(f"status={result.status} sid={result.sid or '-'}"
          + (f" error={result.error}" if result.error else ""))
    return 0 if result.ok else 1


def cmd_convert(args, settings: Settings) -> int:
    from drscreen.model import convert_legacy_checkpoint

    if not args.trust:
        raise ValueError("Converting unpickles the source file. Re-run with --trust only if "
                         "it came from a source you trust.")
    meta = convert_legacy_checkpoint(args.src, args.dst)
    print(f"wrote {args.dst} (arch={meta.arch}, channel_order={meta.channel_order}, "
          f"version={meta.version})")
    return 0


def cmd_doctor(args, settings: Settings) -> int:
    from drscreen.model import CheckpointError, load_checkpoint, resolve_device
    from drscreen.storage import Database

    ok = True

    def report(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"[{'ok' if passed else 'FAIL':>4}] {name:<10} {detail}")

    report("device", True, str(resolve_device(settings.device)))
    try:
        _, meta = load_checkpoint(settings.model_path)
        report("model", True, f"{settings.model_path.name} ({meta.arch}, {meta.version}, "
                              f"{meta.channel_order})")
    except CheckpointError as exc:
        report("model", False, str(exc).splitlines()[0])
    try:
        db = Database(settings.database_url)
        db.create_schema()
        report("database", True, _redact(settings.database_url))
    except Exception as exc:
        report("database", False, f"{_redact(settings.database_url)}: {exc}")
    report("sms", True, "Twilio configured" if settings.twilio.configured and
           settings.sms_enabled else "dry-run (Twilio not configured or disabled)")
    from drscreen import chat

    reachable = chat.is_reachable(settings.ollama)
    chat_detail = (f"reachable at {settings.ollama.host} ({settings.ollama.model})"
                   if reachable else "not reachable (optional; disables the chat assistant)")
    print(f"[{'ok' if reachable else 'warn':>4}] {'chat':<10} {chat_detail}")
    return 0 if ok else 1


def _redact(url: str) -> str:
    from sqlalchemy.engine import make_url

    return make_url(url).render_as_string(hide_password=True)
