"""จุดเข้าใช้งานทั้งหมด

    python -m evbuild validate                ตรวจอย่างเดียว (ใช้ใน CI)
    python -m evbuild build                   ตรวจ + สร้าง output ทุกชนิด
    python -m evbuild build xlsx html         เลือกเฉพาะบางชนิด
    python -m evbuild report coverage         หมวด/รุ่นไหนยังไม่ได้ตรวจ
    python -m evbuild report stale --days 90  ข้อมูลเก่าเกินกำหนด
    python -m evbuild report qa               จุดที่ต้องให้คนตัดสิน

ลำดับงานคงที่เสมอ: load → validate → derive+resolve → render
ข้อมูลผิด = ล้มที่ขั้น validate ก่อนสร้างไฟล์แม้แต่ไฟล์เดียว
ระบบเดิมล้มกลางทางหลังเขียนไฟล์แรกไปแล้ว ทำให้ output ไม่ตรงกัน
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from . import reports
from .loader import DataError, load_all
from .render import OUTPUTS
from .resolve import DEFAULT_STALE_DAYS, resolve_all
from .validate import validate_logic, validate_structure

RENDERERS = ("xlsx", "html", "pdf", "csv")


def _parse_as_of(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(f"--as-of ต้องเป็น YYYY-MM-DD (พบ {value!r})")


def _print_issues(validator, strict: bool) -> None:
    for issue in validator.errors:
        print(f"  {issue}", file=sys.stderr)
    shown = validator.warnings if strict else validator.warnings[:12]
    for issue in shown:
        print(f"  {issue}", file=sys.stderr)
    hidden = len(validator.warnings) - len(shown)
    if hidden > 0:
        print(f"  … และคำเตือนอีก {hidden} รายการ (ดูทั้งหมดด้วย --strict)",
              file=sys.stderr)


def _fail(validator, args, stage: str):
    print(f"ตรวจ  ผิดพลาด {len(validator.errors)} · คำเตือน {len(validator.warnings)}")
    _print_issues(validator, args.strict)
    print(f"\nหยุดที่ขั้น{stage} — แก้ข้อมูลให้ถูกต้องก่อน", file=sys.stderr)
    raise SystemExit(1)


def _pipeline(args):
    """load → ตรวจโครงสร้าง → resolve → ตรวจตรรกะ

    ลำดับนี้สำคัญ: rules engine สมมติว่าชนิดข้อมูลถูกต้องแล้ว การ resolve
    ก่อนตรวจจะทำให้ข้อมูลผิดชนิด (เช่น seats เป็นสตริง) พังด้วย traceback
    แทนที่จะได้ข้อความบอกจุดที่ผิด

    คืน (reference, vehicles, claims, resolved, as_of)
    """
    reference, vehicles, claims = load_all()
    as_of = _parse_as_of(args.as_of)

    print(f"โหลด  รถ {len(vehicles)} รุ่น · ข้อกล่าวอ้าง {len(claims)} แถว · "
          f"หมวด {len(reference.categories)} หมวด")

    # ขั้นที่ 1 — โครงสร้าง · ต้องผ่านก่อนถึงจะแตะ rules engine ได้
    validator = validate_structure(reference, vehicles, claims)
    if not validator.ok(strict=args.strict):
        _fail(validator, args, "ตรวจโครงสร้าง")

    resolved = resolve_all(reference, vehicles, claims,
                           as_of=as_of, stale_days=args.days)

    # ขั้นที่ 2 — ตรรกะข้ามชั้น · ต้องใช้ผลลัพธ์ที่ resolve แล้ว
    validate_logic(reference, vehicles, resolved, validator)
    print(f"ตรวจ  ผิดพลาด {len(validator.errors)} · "
          f"คำเตือน {len(validator.warnings)}")
    if validator.issues:
        _print_issues(validator, args.strict)
    if not validator.ok(strict=args.strict):
        print("\nหยุดก่อนสร้าง output — แก้ข้อมูลให้ถูกต้องก่อน", file=sys.stderr)
        raise SystemExit(1)

    return reference, vehicles, claims, resolved, as_of


def cmd_validate(args) -> int:
    _pipeline(args)
    print("\nข้อมูลผ่านการตรวจทั้งหมด")
    return 0


def cmd_build(args) -> int:
    reference, vehicles, claims, resolved, as_of = _pipeline(args)
    targets = args.targets or list(RENDERERS)

    for line in reports.summary(reference, vehicles, resolved):
        print(line)
    print()

    out_dir = Path(args.out) if args.out else OUTPUTS
    failures = 0

    for target in targets:
        if target not in RENDERERS:
            print(f"[{target}] ไม่รู้จัก — เลือกได้: {', '.join(RENDERERS)}",
                  file=sys.stderr)
            failures += 1
            continue
        module = __import__(f"evbuild.render.{'csvx' if target == 'csv' else target}",
                            fromlist=["build"])
        try:
            result = module.build(reference, vehicles, resolved,
                                  as_of=as_of, stale_days=args.days, out_dir=out_dir)
        except ImportError as exc:
            # ขาด dependency เสริม (weasyprint) — ไม่ควรล้มทั้งบิลด์
            print(f"[{target}] ข้าม: {exc}")
            continue
        for path in (result if isinstance(result, list) else [result]):
            print(f"[{target}] {path}")

    print(f"\nเสร็จ → {out_dir}")
    return 1 if failures else 0


def cmd_report(args) -> int:
    reference, vehicles, claims, resolved, as_of = _pipeline(args)
    print()
    if args.kind == "coverage":
        lines = reports.coverage(reference, vehicles, resolved)
    elif args.kind == "stale":
        lines = reports.stale(resolved, args.days, as_of)
    elif args.kind == "qa":
        lines = reports.qa(reference, vehicles, resolved)
    else:
        lines = reports.summary(reference, vehicles, resolved)
    print("\n".join(lines))
    return 0


# ตัวเลือกร่วม — ใส่ได้ทั้งก่อนและหลังคำสั่งย่อย
#
# argparse รับตัวเลือกของ parser หลักเฉพาะ "ก่อน" คำสั่งย่อยเท่านั้น
# วิธีแก้คือใส่ตัวเลือกชุดเดียวกันทั้งสองระดับผ่าน parents=[...]
# และตั้ง default=SUPPRESS เพื่อไม่ให้ระดับล่างเขียนทับค่าที่ระดับบนตั้งไว้
# (ถ้าใช้ค่า default ปกติ `--days 30 report stale` จะถูกรีเซ็ตกลับเป็น 90)
SHARED_DEFAULTS = {"as_of": None, "days": DEFAULT_STALE_DAYS, "strict": False, "out": None}


def _shared_options() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--as-of", default=argparse.SUPPRESS,
                        help="ประเมินความสดของข้อมูล ณ วันนี้ (YYYY-MM-DD)")
    shared.add_argument("--days", type=int, default=argparse.SUPPRESS,
                        help=f"เพดานอายุข้อมูล (ค่าเริ่มต้น {DEFAULT_STALE_DAYS} วัน)")
    shared.add_argument("--strict", action="store_true", default=argparse.SUPPRESS,
                        help="ถือว่าคำเตือนเป็นข้อผิดพลาดด้วย")
    return shared


def main(argv: list[str] | None = None) -> int:
    shared = _shared_options()
    parser = argparse.ArgumentParser(prog="evbuild", description=__doc__,
                                     parents=[shared],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate", help="ตรวจข้อมูลอย่างเดียว",
                                     parents=[shared])
    validate_parser.set_defaults(func=cmd_validate)

    build_parser = sub.add_parser("build", help="ตรวจแล้วสร้าง output", parents=[shared])
    build_parser.add_argument("targets", nargs="*",
                              help=f"เลือกชนิด: {', '.join(RENDERERS)} (ว่าง = ทั้งหมด)")
    build_parser.add_argument("--out", default=argparse.SUPPRESS,
                              help="โฟลเดอร์ปลายทาง")
    build_parser.set_defaults(func=cmd_build)

    report_parser = sub.add_parser("report", help="รายงานความครบถ้วน/ความสด/QA",
                                   parents=[shared])
    report_parser.add_argument("kind", choices=("coverage", "stale", "qa", "summary"))
    report_parser.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    for name, default in SHARED_DEFAULTS.items():
        if not hasattr(args, name):
            setattr(args, name, default)

    try:
        return args.func(args)
    except DataError as exc:
        print(f"อ่านข้อมูลไม่ได้: {exc}", file=sys.stderr)
        return 2
