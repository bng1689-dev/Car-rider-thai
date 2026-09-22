"""แปลงชั้น L4 ให้อยู่ในรูปที่ตัวเรนเดอร์ใช้ได้

ตัวเรนเดอร์ทุกตัว (xlsx / html / pdf / csv) อ่านจากที่นี่เหมือนกันหมด
จึงไม่มีทางแสดงผลขัดกันเองได้ — ระบบเดิมมี logic การแสดงผลกระจายอยู่ 3 ที่
(build.py grab_cats/bolt_cats · หัวตาราง xlsx · JS ใน template) และตอบ
ไม่ตรงกันจริงเมื่อข้อมูลมีค่าผิด
"""
from __future__ import annotations

from typing import Any

from .model import Reference, Resolved, Vehicle
from .resolve import index_by_vehicle

# ป้ายที่ผู้ใช้เห็น — นิยามที่เดียว
ELIGIBILITY_LABEL = {
    "eligible": "ผ่าน",
    "ineligible": "ไม่ผ่าน",
    "unverified": "รอตรวจสอบ",
}

BASIS_LABEL = {
    "official_list": "ยืนยันจากรายการทางการ",
    "manual": "บันทึกโดยผู้จัดทำ",
    "spec_inference": "อนุมานจาก spec",
    "rule_derived": "คำนวณจากกฎ",
    "coverage_sweep": "ไม่พบในรายการที่สำรวจครบแล้ว",
}

# สีของ pill — เรียงตามความน่าเชื่อถือของที่มา ไม่ใช่ตามผลการพิจารณา
BASIS_STYLE = {
    "official_list": "y",
    "manual": "m",
    "spec_inference": "i",
    "rule_derived": "r",
    "coverage_sweep": "r",
}

LAUNCH_LABEL = {
    "on_sale": ("ขายแล้ว", "sale"),
    "announced": ("เปิดตัว", "announced"),
    "expected": ("คาด", "expected"),
}


def launch_text(vehicle: Vehicle, short: bool = False) -> str:
    label, _cls = LAUNCH_LABEL.get(vehicle.launch.status, (vehicle.launch.status, ""))
    year = vehicle.launch.year
    if year is None:
        return label
    if short:
        return str(year)
    if vehicle.launch.quarter:
        return f"{label} Q{vehicle.launch.quarter}/{year}"
    return f"{label} {year}"


def launch_css(vehicle: Vehicle) -> str:
    return LAUNCH_LABEL.get(vehicle.launch.status, ("", "sale"))[1]


def body_label(vehicle: Vehicle, reference: Reference) -> str:
    """ป้ายตัวถังที่คนอ่าน — รวมขนาดเข้ากับประเภท เช่น 'SUV (เล็ก)'
    ข้อมูลสองมิติถูกเก็บแยกกัน แต่แสดงรวมกันได้เมื่อต้องการ
    """
    body = reference.body_type_by_id.get(vehicle.body_type)
    label = body.label if body else vehicle.body_type
    size_suffix = {"compact": " เล็ก", "large": " ใหญ่"}.get(vehicle.size_class or "", "")
    return label + size_suffix


def category_entry(row: Resolved, reference: Reference) -> dict[str, Any]:
    category = reference.category_by_id[row.category_id]
    label = category.label
    if row.tier:
        label = f"{label} {row.tier.upper()}"
    return {
        "category_id": row.category_id,
        "label": label,
        "eligibility": row.eligibility,
        "eligibility_label": ELIGIBILITY_LABEL[row.eligibility],
        "basis": row.basis,
        "basis_label": BASIS_LABEL.get(row.basis or "", "ยังไม่ได้ตรวจ"),
        "style": BASIS_STYLE.get(row.basis or "", "p"),
        "tier": row.tier,
        "confidence": row.confidence,
        "checked_at": row.checked_at,
        "is_stale": row.is_stale,
        "source_url": row.source_url,
        "conflict": row.rule_conflict,
    }


def build_rows(
    reference: Reference, vehicles: list[Vehicle], resolved: list[Resolved]
) -> list[dict[str, Any]]:
    """หนึ่งรายการต่อรถหนึ่งคัน พร้อมหมวดที่ "ควรแสดง" ของแต่ละแพลตฟอร์ม

    แสดงเฉพาะ eligible และ unverified — ineligible ไม่แสดง (เหมือนระบบเดิม
    ที่ข้าม "-") แต่ต่างกันตรงที่ตอนนี้ระบบ *รู้* ว่าอันไหนคือไม่ผ่านจริง
    และอันไหนคือยังไม่เคยตรวจ
    """
    index = index_by_vehicle(resolved)
    platform_ids = [p.id for p in reference.platforms]
    rows: list[dict[str, Any]] = []

    for vehicle in vehicles:
        cells = index.get(vehicle.vehicle_id, {})
        row: dict[str, Any] = {
            "id": vehicle.vehicle_id,
            "brand": vehicle.brand,
            "model": vehicle.model,
            "body": body_label(vehicle, reference),
            "body_type": vehicle.body_type,
            "seats": vehicle.seats,
            "launch_status": vehicle.launch.status,
            "launch_text": launch_text(vehicle),
            "launch_short": launch_text(vehicle, short=True),
            "launch_css": launch_css(vehicle),
            "note": vehicle.note,
            "data_issue": vehicle.data_issue,
            "specs": vehicle.specs,
        }
        for platform_id in platform_ids:
            entries = []
            for category in reference.categories_of(platform_id):
                cell = cells.get(category.id)
                if cell is None or cell.eligibility == "ineligible":
                    continue
                entries.append(category_entry(cell, reference))
            row[platform_id] = entries
        rows.append(row)

    return rows


def platform_note(reference: Reference, platform_id: str) -> str:
    """คำอธิบายระดับแพลตฟอร์ม — แทนการเขียน 'i' ซ้ำ 117 ครั้งในข้อมูลดิบ"""
    platform = reference.platform_by_id[platform_id]
    if platform.publishes_model_list:
        return f"{platform.name} เปิดเผย model list ของไทย — หมวดที่ยืนยันได้มาจากรายการจริง"
    return (f"{platform.name} ไม่เปิดเผย model list ของไทย — "
            f"ทุกหมวดเป็นการอนุมานจาก spec")


def not_surveyed_categories(reference: Reference) -> list[dict[str, str]]:
    """หมวดที่ยังไม่ได้สำรวจ — รายงานที่ระดับหมวด ไม่สาด "?" ลงรถทุกคัน"""
    return [
        {"id": c.id, "label": c.label, "platform": c.platform}
        for c in reference.categories
        if c.coverage_status == "not_surveyed"
    ]
