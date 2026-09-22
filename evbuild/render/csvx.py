"""ส่งออก CSV — รูปแบบยาว และรูปแบบ entity-link สำหรับ i2

ชั้น L4 เป็น long format อยู่แล้ว การส่งออกจึงเหลือแค่การ map ชื่อคอลัมน์
ตารางกว้างแบบระบบเดิมต้อง pivot ก่อนเสมอ
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .. import view
from ..model import Reference, Resolved, Vehicle
from . import OUTPUTS

LONG_HEADERS = [
    "vehicle_id", "brand", "model", "platform", "category_id", "category_label",
    "tier", "eligibility", "basis", "confidence", "checked_at",
    "staleness_days", "is_stale", "source_url", "reason", "rule_conflict",
]

# i2 Analyst's Notebook: หนึ่งแถว = หนึ่งความสัมพันธ์ พร้อมแหล่งที่มาและวันที่
I2_HEADERS = [
    "Entity1_Type", "Entity1_Label", "Entity2_Type", "Entity2_Label",
    "Link_Type", "Link_Direction", "Link_Label",
    "Attribute_Basis", "Attribute_Confidence", "Date_Checked", "Source", "Notes",
]


def build(
    reference: Reference,
    vehicles: list[Vehicle],
    resolved: list[Resolved],
    as_of: date,
    stale_days: int,
    out_dir: Path = OUTPUTS,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    long_path = out_dir / "resolved.csv"
    with long_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=LONG_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in resolved:
            record = row.to_dict()
            record["is_stale"] = "1" if row.is_stale else "0"
            writer.writerow(record)
    written.append(long_path)

    # ส่งออกเฉพาะความสัมพันธ์ที่ "มีอยู่จริง" — ไม่ผ่าน ไม่ใช่ความสัมพันธ์
    i2_path = out_dir / "i2-links.csv"
    with i2_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(I2_HEADERS)
        for row in resolved:
            if row.eligibility == "ineligible":
                continue
            category = reference.category_by_id[row.category_id]
            platform = reference.platform_by_id[row.platform]
            writer.writerow([
                "Vehicle Model", f"{row.brand} {row.model}",
                "Service Category", f"{platform.name} {category.label}",
                "Eligibility",
                "Entity1 -> Entity2",
                view.ELIGIBILITY_LABEL[row.eligibility] + (f" ({row.tier.upper()})" if row.tier else ""),
                view.BASIS_LABEL.get(row.basis or "", "ยังไม่ได้ตรวจ"),
                row.confidence or "",
                row.checked_at,
                row.source_url,
                row.rule_conflict or row.reason,
            ])
    written.append(i2_path)

    return written
