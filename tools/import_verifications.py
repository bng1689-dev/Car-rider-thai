#!/usr/bin/env python3
"""นำผลตรวจที่บันทึกในเว็บแอปเข้า data/eligibility.jsonl

    python tools/import_verifications.py webapp-verifications-2026-09-23.json
    python tools/import_verifications.py <ไฟล์> --dry-run     แสดงผลอย่างเดียว ไม่เขียน

รับได้ทั้งไฟล์ .json (อาร์เรย์ที่แอปส่งออก) และ .jsonl (หนึ่งบรรทัดต่อหนึ่งแถว)

กติกา
  • ผลตรวจหนึ่งแถว = คำตอบล่าสุดของช่องนั้น (รถ × หมวด) — จึงแทนที่ข้อกล่าวอ้าง
    เดิมทุกแถวของช่องเดียวกัน ของเดิมยังอยู่ใน git history
  • ทุกแถวต้องผ่านกติกาเดียวกับ `evbuild validate` เช่น basis=official_list
    ต้องมี source_url และ checked_at
  • ทั้งหมดหรือไม่มีเลย: ถ้าผลรวมหลังนำเข้ามีข้อผิดพลาดแม้แต่จุดเดียว
    จะไม่เขียนไฟล์ใด ๆ และบอกจุดที่ผิด
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evbuild.loader import (  # noqa: E402
    ELIGIBILITY_PATH, load_reference, load_vehicles, read_jsonl, write_jsonl,
)
from evbuild.model import Claim  # noqa: E402
from evbuild.resolve import resolve_all  # noqa: E402
from evbuild.validate import validate_logic, validate_structure  # noqa: E402

CLAIM_FIELDS = ("vehicle_id", "category_id", "eligibility", "basis", "confidence",
                "tier", "source_url", "checked_at", "checked_by", "note")


class ImportError_(Exception):
    """ไฟล์นำเข้าอ่านไม่ได้ หรือผลรวมหลังนำเข้าไม่ผ่านการตรวจ"""


def read_import(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            rows = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ImportError_(f"{path.name}: JSON ผิดรูปแบบ — {exc}") from exc
    else:
        rows = [rec for _lineno, rec in read_jsonl(path)]
    if not all(isinstance(r, dict) for r in rows):
        raise ImportError_(f"{path.name}: ทุกแถวต้องเป็น object")
    return rows


def normalize(row: dict) -> dict:
    """เก็บเฉพาะฟิลด์ของข้อกล่าวอ้าง ตัดฟิลด์ว่างที่ไม่บังคับออก"""
    clean = {k: row[k] for k in CLAIM_FIELDS if k in row and row[k] is not None}
    clean.setdefault("note", "")
    clean.setdefault("source_url", "")
    if not clean.get("tier"):
        clean.pop("tier", None)
    return clean


def to_claim(rec: dict) -> Claim:
    return Claim(
        vehicle_id=rec.get("vehicle_id", ""), category_id=rec.get("category_id", ""),
        eligibility=rec.get("eligibility", ""), basis=rec.get("basis", ""),
        confidence=rec.get("confidence", "medium"), tier=rec.get("tier"),
        source_url=rec.get("source_url", ""), checked_at=rec.get("checked_at", ""),
        checked_by=rec.get("checked_by", ""), note=rec.get("note", ""),
    )


def merge(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], list[tuple]]:
    """แทนที่ทุกแถวของช่องเดียวกัน ณ ตำแหน่งของแถวแรกที่ถูกแทน — diff ใน git อ่านง่าย

    คืน (แถวทั้งหมดหลังรวม, รายการเปลี่ยนแปลง [(ชนิด, แถวเดิมหรือ None, แถวใหม่)])
    """
    latest: dict[tuple[str, str], dict] = {}
    for row in incoming:                      # ไฟล์เดียวมีช่องซ้ำ → แถวหลังชนะ
        latest[(row["vehicle_id"], row["category_id"])] = row

    merged: list[dict] = []
    placed: set[tuple[str, str]] = set()
    changes: list[tuple] = []
    for row in existing:
        key = (row.get("vehicle_id"), row.get("category_id"))
        if key not in latest:
            merged.append(row)
            continue
        if key not in placed:
            merged.append(latest[key])
            placed.add(key)
        changes.append(("replaced", row, latest[key]))

    for key, row in latest.items():
        if key not in placed:
            merged.append(row)
            changes.append(("added", None, row))
    return merged, changes


def run(import_path: Path, dry_run: bool, eligibility_path: Path = ELIGIBILITY_PATH) -> int:
    reference = load_reference()
    vehicles = load_vehicles()
    existing = [rec for _lineno, rec in read_jsonl(eligibility_path)]

    incoming = [normalize(r) for r in read_import(import_path)]
    if not incoming:
        print(f"{import_path.name}: ไม่มีผลตรวจให้นำเข้า")
        return 0

    merged, changes = merge(existing, incoming)

    # ตรวจทั้งชุดหลังรวม ไม่ใช่เฉพาะแถวที่นำเข้า — แถวใหม่อาจทำให้ตรรกะข้ามชั้นขัดกัน
    claims = [to_claim(r) for r in merged]
    validator = validate_structure(reference, vehicles, claims)
    if validator.ok():
        resolved = resolve_all(reference, vehicles, claims)
        validate_logic(reference, vehicles, resolved, validator)

    kinds = Counter(kind for kind, _old, _new in changes)
    print(f"นำเข้าจาก {import_path.name}: {len(incoming)} แถว")
    print(f"  เพิ่มใหม่ {kinds['added']} · แทนที่แถวเดิม {kinds['replaced']}")
    for kind, old, new in changes:
        label = f"{new['vehicle_id']} × {new['category_id']}"
        if kind == "added":
            print(f"  + {label}: {new['eligibility']} ({new['basis']})")
        else:
            print(f"  ~ {label}: {old.get('eligibility')} ({old.get('basis')}) "
                  f"→ {new['eligibility']} ({new['basis']})")

    if validator.errors:
        print(f"\nไม่เขียนไฟล์ — ผลรวมหลังนำเข้ามีข้อผิดพลาด {len(validator.errors)} จุด:",
              file=sys.stderr)
        for issue in validator.errors:
            print(f"  {issue}", file=sys.stderr)
        return 1

    if dry_run:
        print("\n--dry-run: ผ่านการตรวจ แต่ไม่เขียนไฟล์")
        return 0

    write_jsonl(eligibility_path, merged)
    try:
        shown = eligibility_path.resolve().relative_to(ROOT)
    except ValueError:
        shown = eligibility_path          # อยู่นอกโปรเจก — แสดง path เต็ม
    print(f"\nเขียนแล้ว → {shown}")
    print("ขั้นต่อไป: python -m evbuild build")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="ไฟล์ผลตรวจที่ส่งออกจากเว็บแอป")
    parser.add_argument("--dry-run", action="store_true", help="ตรวจอย่างเดียว ไม่เขียนไฟล์")
    args = parser.parse_args(argv)
    if not args.file.exists():
        print(f"ไม่พบไฟล์: {args.file}", file=sys.stderr)
        return 2
    try:
        return run(args.file, args.dry_run)
    except ImportError_ as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
