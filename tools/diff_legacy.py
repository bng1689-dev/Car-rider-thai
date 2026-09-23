#!/usr/bin/env python3
"""เทียบผลลัพธ์ระบบใหม่กับข้อมูลเดิมทั้ง 117 × 10 = 1170 ช่อง

นี่คือด่านความปลอดภัยของการย้ายระบบ — ห้ามลบไฟล์เดิมจนกว่าตัวนี้จะผ่าน
ใช้เป็นทั้งรายงานให้คนอ่าน และเป็น oracle ของ tests/test_regression.py

การเทียบทำที่ระดับ "ความหมาย" (ผ่าน / ไม่ผ่าน / ยังไม่รู้)
ไม่ใช่ที่ระดับตัวอักษร y/i/p/- เพราะระบบใหม่แยก 'ที่มา' ออกจาก 'ผลการพิจารณา'
แล้ว การที่ GrabCar เปลี่ยนจาก y (อ้างว่ามาจาก official list) เป็น
rule_derived คือการแก้ให้ตรงความจริง ไม่ใช่การถดถอย

ช่องที่ข้อสรุปมาจากข้อกล่าวอ้างที่ตรวจหลังวันย้ายระบบ (เช่น ผลตรวจจากเว็บแอป)
ไม่นับเป็นการถดถอย แต่แสดงแยกเป็น "อัปเดต" พร้อมวันที่ตรวจ — ข้อมูลเดิมเป็น
ภาพ ณ วันเดียว ถ้าถือเป็นความจริงตลอดไป งานตรวจสอบทุกชิ้นจะทำให้ CI ล้ม
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evbuild.loader import load_all  # noqa: E402
from evbuild.resolve import resolve_all  # noqa: E402
from tools.migrate_legacy import LEGACY_CHECKED_AT, LEGACY_PATH, slugify  # noqa: E402

# ที่มาที่เป็นข้อกล่าวอ้างจากคนหรือรายการจริง (ไม่ใช่กฎหรือการอนุมานจากการสำรวจ)
CLAIM_BASES = {"official_list", "manual", "spec_inference"}

# ความหมายของธงเดิม เมื่อแปลเป็นคำศัพท์ของระบบใหม่
LEGACY_MEANING = {
    "y": "eligible",
    "i": "eligible",
    "p": "unverified",
    "-": "ineligible",
}


def updated_after_migration(row) -> bool:
    """ข้อสรุปมาจากข้อกล่าวอ้างที่ตรวจหลังวันย้ายระบบ = ข้อเท็จจริงใหม่พร้อมหลักฐาน

    เช่น ผลตรวจที่นำเข้าจากเว็บแอปเปลี่ยนช่อง "รอตรวจ" เดิมให้เป็น "ผ่าน"
    นั่นคืองานที่ระบบนี้สร้างมาให้ทำ ไม่ใช่การย้ายระบบที่ทำความหมายเพี้ยน
    """
    return (row is not None and row.basis in CLAIM_BASES
            and (row.checked_at or "") > LEGACY_CHECKED_AT)


def compare() -> tuple[list[dict], list[dict], list[dict]]:
    """คืน (regressions, intended_changes, updated_after_migration)"""
    reference, vehicles, claims = load_all()
    resolved = resolve_all(reference, vehicles, claims)
    index = {(r.vehicle_id, r.category_id): r for r in resolved}
    legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))

    regressions: list[dict] = []
    intended: list[dict] = []
    updated: list[dict] = []

    for entry in legacy:
        vehicle_id = slugify(entry["brand"], entry["model"])
        for category in reference.categories:
            if not category.legacy_key:
                continue
            flag = entry.get(category.legacy_key, "-")
            was = LEGACY_MEANING[flag]
            row = index.get((vehicle_id, category.id))
            now = row.eligibility if row else "ineligible"

            if was == now:
                continue

            record = {
                "vehicle": f"{entry['brand']} {entry['model']}",
                "category": category.id,
                "legacy_flag": flag,
                "was": was,
                "now": now,
                "basis": row.basis if row else None,
                "reason": row.reason if row else "ไม่มีแถว (หมวดยังไม่ได้สำรวจ)",
            }
            if updated_after_migration(row):
                record["checked_at"] = row.checked_at
                updated.append(record)
            # ยอมรับได้: เดิมบอก "ไม่ผ่าน" แต่จริง ๆ คือ "ไม่เคยตรวจ"
            # ระบบใหม่เลิกกลบความไม่รู้ให้ดูเหมือนคำตอบ
            elif was == "ineligible" and now == "unverified":
                intended.append(record)
            else:
                regressions.append(record)

    return regressions, intended, updated


def main() -> int:
    regressions, intended, updated = compare()

    print("เทียบผลลัพธ์ระบบใหม่ vs ข้อมูลเดิม (117 รุ่น × 10 คอลัมน์ = 1170 ช่อง)")
    print("=" * 68)
    print(f"\nการถดถอย (ต้องเป็น 0)          : {len(regressions)}")
    for r in regressions[:20]:
        print(f"  ✗ {r['vehicle']} × {r['category']}: {r['was']} → {r['now']}")
    if len(regressions) > 20:
        print(f"  … และอีก {len(regressions) - 20} จุด")

    print(f"\nการเปลี่ยนแปลงที่ตั้งใจ         : {len(intended)}")
    if intended:
        print('  เดิมแสดงเป็น "-" (ไม่ผ่าน) ทั้งที่ความจริงคือ "ยังไม่เคยตรวจ"')
        print("  ระบบใหม่แสดงตามความจริง จึงเห็นงานที่ยังค้างอยู่")
        by_category = Counter(r["category"] for r in intended)
        for category, n in by_category.most_common():
            print(f"    {category:<14} {n:>3} ช่อง")
        print("\n  ตัวอย่าง:")
        for r in intended[:10]:
            print(f"    • {r['vehicle']} × {r['category']}")

    print(f"\nอัปเดตด้วยผลตรวจหลังย้ายระบบ  : {len(updated)}")
    if updated:
        print("  ข้อกล่าวอ้างใหม่กว่าข้อมูลเดิม พร้อมที่มาและวันที่ — ไม่นับเป็นการถดถอย")
        for r in updated:
            print(f"    • {r['vehicle']} × {r['category']}: {r['was']} → {r['now']} "
                  f"({r['basis']}, {r['checked_at']})")

    print()
    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
