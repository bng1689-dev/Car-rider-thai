#!/usr/bin/env python3
"""เทียบผลลัพธ์ระบบใหม่กับข้อมูลเดิมทั้ง 117 × 10 = 1170 ช่อง

นี่คือด่านความปลอดภัยของการย้ายระบบ — ห้ามลบไฟล์เดิมจนกว่าตัวนี้จะผ่าน
ใช้เป็นทั้งรายงานให้คนอ่าน และเป็น oracle ของ tests/test_regression.py

การเทียบทำที่ระดับ "ความหมาย" (ผ่าน / ไม่ผ่าน / ยังไม่รู้)
ไม่ใช่ที่ระดับตัวอักษร y/i/p/- เพราะระบบใหม่แยก 'ที่มา' ออกจาก 'ผลการพิจารณา'
แล้ว การที่ GrabCar เปลี่ยนจาก y (อ้างว่ามาจาก official list) เป็น
rule_derived คือการแก้ให้ตรงความจริง ไม่ใช่การถดถอย
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
from tools.migrate_legacy import LEGACY_PATH, slugify  # noqa: E402

# ความหมายของธงเดิม เมื่อแปลเป็นคำศัพท์ของระบบใหม่
LEGACY_MEANING = {
    "y": "eligible",
    "i": "eligible",
    "p": "unverified",
    "-": "ineligible",
}


def compare() -> tuple[list[dict], list[dict]]:
    """คืน (regressions, intended_changes)"""
    reference, vehicles, claims = load_all()
    resolved = resolve_all(reference, vehicles, claims)
    index = {(r.vehicle_id, r.category_id): r for r in resolved}
    legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))

    regressions: list[dict] = []
    intended: list[dict] = []

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
            # ยอมรับได้: เดิมบอก "ไม่ผ่าน" แต่จริง ๆ คือ "ไม่เคยตรวจ"
            # ระบบใหม่เลิกกลบความไม่รู้ให้ดูเหมือนคำตอบ
            if was == "ineligible" and now == "unverified":
                intended.append(record)
            else:
                regressions.append(record)

    return regressions, intended


def main() -> int:
    regressions, intended = compare()

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

    print()
    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
