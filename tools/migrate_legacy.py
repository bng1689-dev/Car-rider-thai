#!/usr/bin/env python3
"""แปลงข้อมูลเดิม ev-project/ev_data.json → โครงสร้างใหม่ L1 + L2

รันครั้งเดียวตอนย้ายระบบ · รันซ้ำได้ (idempotent) · ไม่แก้ไฟล์ต้นทาง

    python tools/migrate_legacy.py [--dry-run]

สิ่งที่สคริปต์นี้ทำ
  1. ตั้ง vehicle_id (slug) ให้ทุกคัน — แก้ปัญหาชื่อรุ่นซ้ำ (ES, X)
  2. แปลง body 18 ค่า → body_type enum + size_class ผ่านตารางคำพ้องใน L0
  3. แยกข้อมูลที่มีโครงสร้างออกจากฟิลด์ note (Exec tier / เวลา / สเปก)
  4. ทิ้งคอลัมน์ที่พิสูจน์แล้วว่าคำนวณได้ 100% (gcar / bbasic / bgreen)
     — 351 ช่องที่เคยกรอกมือ ย้ายไปเป็นกฎใน categories.yaml
  5. แปลงธงที่เหลือเป็นข้อกล่าวอ้างรูปแบบยาว พร้อม basis / confidence /
     source_url / checked_at ครบทุกแถว
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evbuild.loader import (  # noqa: E402
    ELIGIBILITY_PATH, VEHICLES_PATH, load_reference, write_jsonl,
)

LEGACY_PATH = ROOT / "ev-project" / "ev_data.json"

# วันที่ที่ข้อมูลเดิมระบุไว้ใน README ("ข้อมูล ณ กันยายน 2568")
# ทุกข้อกล่าวอ้างที่ย้ายมาได้วันที่นี้เป็นจุดตั้งต้น แล้วค่อยอัปเดตเมื่อตรวจจริง
LEGACY_CHECKED_AT = "2025-09-15"
LEGACY_CHECKED_BY = "legacy_import"

# คอลัมน์ที่ไม่ต้องย้าย เพราะกฎใน categories.yaml คำนวณได้ครบ
# (ตรวจแล้วทั้ง 117 แถว: gcar=='y' ⟺ ไม่ใช่กระบะ · bbasic==bgreen==gcar เสมอ)
DERIVABLE_KEYS = {"gcar", "bbasic", "bgreen"}

# ขนาดรถ — เดิมถูกยัดรวมในฟิลด์เดียวกับประเภทตัวถัง
SIZE_BY_LEGACY_BODY = {
    "SUV เล็ก": "compact", "Hatchback เล็ก": "compact", "City car": "compact",
    "SUV ใหญ่": "large",
}

THAI_MONTHS = {
    "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
    "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12,
}

LAUNCH_STATUS_BY_LEGACY = {"sale": "on_sale", "2026": "announced", "2027": "expected"}

# ข้อความใน note ที่ซ้ำกับฟิลด์อื่นอยู่แล้ว → ทิ้งได้โดยไม่เสียข้อมูล
REDUNDANT_NOTE_PATTERNS = (
    re.compile(r"^\s*\d+\s*ที่นั่ง\s*$"),
    re.compile(r"^\s*SUV\s*\d+\s*ที่นั่ง\s*$"),
    re.compile(r"กระบะ"),
)


def slugify(brand: str, model: str) -> str:
    """byd + 'Dolphin Mini / Atto 1' → 'byd-dolphin-mini-atto-1'"""
    raw = f"{brand} {model}"
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-zA-Z0-9฀-๿]+", "-", raw).strip("-").lower()
    return re.sub(r"-{2,}", "-", slug)


def parse_exec_tier(note: str) -> str | None:
    """'Grab Exec Lite' → 'lite' · 'Grab Exec M' → 'm' · 'Grab Exec' → None

    ข้อมูลระดับชั้นที่เดิมอยู่ในข้อความอิสระ จึงกรองและจัดกลุ่มไม่ได้เลย
    """
    if re.search(r"Exec\s+Lite", note, re.I):
        return "lite"
    if re.search(r"Exec\s+M\b", note):
        return "m"
    return None


def parse_launch(legacy_status: str, note: str) -> tuple[dict, str]:
    """คืน (launch, conflict) — conflict ว่างถ้า note กับ status ไม่ขัดกัน"""
    launch: dict = {"status": LAUNCH_STATUS_BY_LEGACY[legacy_status]}

    if legacy_status in ("2026", "2027"):
        launch["year"] = int(legacy_status)

    quarter = re.search(r"\bQ([1-4])\b", note)
    if quarter:
        launch["quarter"] = int(quarter.group(1))

    for thai_month, number in THAI_MONTHS.items():
        if thai_month in note:
            launch["month"] = number
            break

    # ตรวจความขัดแย้งระหว่าง status กับปีที่เอ่ยใน note
    conflict = ""
    years_in_note = {int(y) for y in re.findall(r"\b(20\d{2})\b", note)}
    if legacy_status == "sale" and years_in_note and min(years_in_note) > 2025:
        conflict = (f"status='sale' (ขายแล้ว) แต่ note ระบุปี "
                    f"{sorted(years_in_note)} — ต้องให้คนตัดสิน")
    elif legacy_status in ("2026", "2027") and years_in_note \
            and int(legacy_status) not in years_in_note:
        conflict = (f"status={legacy_status} แต่ note ระบุปี {sorted(years_in_note)}")

    return launch, conflict


def parse_specs(note: str) -> dict:
    specs: dict = {}
    range_km = re.search(r"(\d{3,4})\s*กม\./ชาร์จ", note)
    if range_km:
        specs["range_km"] = int(range_km.group(1))
    architecture = re.search(r"\b(\d{3,4})V\b", note)
    if architecture:
        specs["architecture_v"] = int(architecture.group(1))
    if "ประตูสไลด์" in note:
        specs["features"] = ["sliding_door"]
    return specs


def residual_note(note: str, extracted_launch: bool, specs: dict, tier_found: bool) -> str:
    """เหลือเฉพาะข้อความที่ยังไม่มีที่อยู่เป็นฟิลด์จริง"""
    if not note:
        return ""
    for pattern in REDUNDANT_NOTE_PATTERNS:
        if pattern.search(note):
            return ""
    if tier_found or re.match(r"^\s*Grab (Exec|Premium)", note, re.I):
        return ""
    if specs:
        return ""
    if extracted_launch and re.search(r"\b20\d{2}\b", note):
        return ""
    return note.strip()


def migrate(legacy: list[dict], reference) -> tuple[list[dict], list[dict], list[str]]:
    vehicles: list[dict] = []
    claims: list[dict] = []
    notices: list[str] = []
    seen_ids: dict[str, str] = {}

    for entry in legacy:
        brand, model, note = entry["brand"], entry["model"], entry.get("note", "")
        vehicle_id = slugify(brand, model)
        if vehicle_id in seen_ids:
            raise SystemExit(
                f"slug ชนกัน: {vehicle_id!r} ใช้โดยทั้ง {seen_ids[vehicle_id]} "
                f"และ {brand} {model} — ต้องตั้งชื่อให้ต่างกันก่อน"
            )
        seen_ids[vehicle_id] = f"{brand} {model}"

        legacy_body = entry["body"]
        body_type = reference.body_type_by_alias.get(legacy_body)
        if body_type is None:
            raise SystemExit(
                f"ไม่รู้จักตัวถัง {legacy_body!r} ({brand} {model}) — "
                f"เพิ่มเป็น alias ใน data/reference/body_types.yaml ก่อน"
            )

        launch, conflict = parse_launch(entry["status"], note)
        specs = parse_specs(note)
        tier = parse_exec_tier(note)
        if conflict:
            notices.append(f"{brand} {model}: {conflict}")

        vehicle = {
            "vehicle_id": vehicle_id,
            "brand": brand,
            "model": model,
            "body_type": body_type,
            "size_class": SIZE_BY_LEGACY_BODY.get(legacy_body, "standard"),
            "seats": entry["seats"],
            # จำนวนประตูไม่มีในข้อมูลเดิม — บันทึกว่า "ไม่ทราบ" ตรง ๆ
            # ห้ามเดาเป็น 4 เพราะจะกลายเป็นข้อมูลที่เราแต่งขึ้นเอง
            "doors": None,
            "powertrain": "bev",
            "launch": launch,
            "specs": specs,
            "note": residual_note(note, bool(launch.get("year")), specs, tier is not None),
            "sources": [
                {"url": "", "checked_at": LEGACY_CHECKED_AT, "field": "*",
                 "origin": "ev_data.json (legacy import)"}
            ],
        }
        if conflict:
            vehicle["data_issue"] = conflict
        vehicles.append(vehicle)

        for category in reference.categories:
            key = category.legacy_key
            if not key or key in DERIVABLE_KEYS:
                continue
            flag = entry.get(key, "-")
            if flag == "-":
                continue    # ไม่มีข้อกล่าวอ้าง — ให้ resolve ตีความตาม coverage_status

            claim: dict = {
                "vehicle_id": vehicle_id,
                "category_id": category.id,
                "checked_at": LEGACY_CHECKED_AT,
                "checked_by": LEGACY_CHECKED_BY,
                "note": "",
            }
            if flag == "y":
                claim.update(eligibility="eligible", basis="official_list",
                             confidence="high", source_url=category.source_url)
            elif flag == "i":
                claim.update(eligibility="eligible", basis="spec_inference",
                             confidence="medium", source_url=category.source_url,
                             note="อนุมานจาก spec — แพลตฟอร์มไม่เปิดเผย model list ของไทย")
            elif flag == "p":
                claim.update(eligibility="unverified", basis="manual",
                             confidence="low", source_url="",
                             note="รุ่นใหม่ ยังไม่พบในรายการทางการ")
            else:
                raise SystemExit(
                    f"ค่าธงที่ไม่รู้จัก {flag!r} ที่ {brand} {model} คอลัมน์ {key} "
                    f"— ข้อมูลเดิมผิด ต้องแก้ก่อนย้าย"
                )

            if category.tiers and tier and flag == "y":
                claim["tier"] = tier
            claims.append(claim)

    return vehicles, claims, notices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="แสดงสรุปอย่างเดียว ไม่เขียนไฟล์")
    args = parser.parse_args()

    reference = load_reference()
    legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
    vehicles, claims, notices = migrate(legacy, reference)

    legacy_cells = len(legacy) * len([c for c in reference.categories if c.legacy_key])
    dropped = len(legacy) * len(DERIVABLE_KEYS)

    print(f"อ่านข้อมูลเดิม      {len(legacy)} รุ่น × "
          f"{len([c for c in reference.categories if c.legacy_key])} คอลัมน์ "
          f"= {legacy_cells} ช่อง")
    print(f"L1 vehicles        {len(vehicles)} แถว")
    print(f"L2 claims          {len(claims)} แถว "
          f"(ทิ้งช่องที่กฎคำนวณได้ {dropped} ช่อง)")
    with_source = sum(1 for c in claims if c.get("source_url"))
    print(f"   มี source_url    {with_source}/{len(claims)}")
    print(f"   มี checked_at    {sum(1 for c in claims if c.get('checked_at'))}/{len(claims)}")
    tiers = sum(1 for c in claims if c.get("tier"))
    print(f"   ระบุ tier ได้     {tiers} แถว (เดิมเป็นข้อความอิสระในฟิลด์ note)")

    if notices:
        print(f"\nพบข้อมูลขัดแย้งที่ต้องให้คนตัดสิน {len(notices)} จุด:")
        for notice in notices:
            print(f"  • {notice}")

    if args.dry_run:
        print("\n--dry-run: ไม่เขียนไฟล์")
        return 0

    write_jsonl(VEHICLES_PATH, vehicles)
    write_jsonl(ELIGIBILITY_PATH, claims)
    print(f"\nเขียนแล้ว → {VEHICLES_PATH.relative_to(ROOT)}")
    print(f"           {ELIGIBILITY_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
