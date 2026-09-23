"""L3/L4 — รวมกฎเข้ากับข้อกล่าวอ้าง แล้วตัดสินผลสุดท้าย

ลำดับความสำคัญ (สูง → ต่ำ)
    official_list > manual > spec_inference > rule_derived > coverage_sweep

หลักสำคัญ: ข้อเท็จจริงจาก list ทางการชนะกฎที่เราอนุมานเองเสมอ
และเมื่อทั้งสองขัดกัน ระบบจะ "บันทึกไว้" (rule_conflict) แทนที่จะกลบเงียบ —
เพราะกฎที่ขัดกับความจริงคือกฎที่ต้องแก้ ไม่ใช่ความจริงที่ต้องแก้
ระบบเดิมเขียนสถานการณ์นี้ลงข้อมูลไม่ได้เลย
"""
from __future__ import annotations

from datetime import date, datetime

from .model import Category, Claim, Reference, Resolved, Vehicle
from .rules import derive

PRECEDENCE = {
    "official_list": 4,
    "manual": 3,
    "spec_inference": 2,
    "rule_derived": 1,
    "coverage_sweep": 0,
}

DEFAULT_STALE_DAYS = 90


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _staleness(checked_at: str, as_of: date, stale_days: int) -> tuple[int | None, bool]:
    checked = _parse_date(checked_at)
    if checked is None:
        return None, False
    days = (as_of - checked).days
    return days, days > stale_days


def covered_by_survey(vehicle: Vehicle, category: Category) -> bool:
    """การสำรวจหมวดที่เสร็จ ณ category.as_of ครอบคลุมรถคันนี้หรือไม่

    การสำรวจพูดแทนได้เฉพาะรถที่อยู่ในชุดข้อมูลแล้ว ณ วันสำรวจ รถที่เพิ่มเข้ามา
    ทีหลังไม่เคยถูกตรวจกับรายการ ถ้าตีความการไม่มีข้อกล่าวอ้างว่า "ไม่ผ่าน"
    ก็คือการกลบความไม่รู้ให้ดูเหมือนคำตอบ — ปัญหาเดียวกับ "-" ของระบบเดิม
    ไม่รู้วันที่เพิ่ม = ถือว่าไม่ครอบคลุม (ไม่รู้ ≠ ไม่ผ่าน)
    """
    added = _parse_date(vehicle.added_at)
    surveyed = _parse_date(category.as_of)
    return added is not None and surveyed is not None and added <= surveyed


def _best_claim(claims: list[Claim]) -> Claim:
    """ข้อกล่าวอ้างหลายข้อต่อช่องเดียวกัน — เอาที่น่าเชื่อถือที่สุด
    เสมอกันให้เอาที่ตรวจล่าสุด
    """
    return max(
        claims,
        key=lambda c: (PRECEDENCE.get(c.basis, -1), c.checked_at or ""),
    )


def resolve_cell(
    vehicle: Vehicle,
    category: Category,
    claims: list[Claim],
    reference: Reference,
) -> tuple[str, str | None, str | None, str | None, str, str, str] | None:
    """ตัดสินหนึ่งช่อง (รถ × หมวด)

    คืน (eligibility, basis, confidence, tier, source_url, checked_at, reason)
    หรือ None เมื่อไม่ควรมีแถวเลย (หมวดที่ยังไม่ได้สำรวจ)
    """
    rule = derive(vehicle, category, reference)

    if claims:
        claim = _best_claim(claims)
        return (
            claim.eligibility,
            claim.basis,
            claim.confidence,
            claim.tier,
            claim.source_url or category.source_url,
            claim.checked_at,
            claim.note or f"ข้อกล่าวอ้าง ({claim.basis})",
        )

    if rule is not None:
        eligibility, confidence, reason = rule
        return (eligibility, "rule_derived", confidence, None,
                category.source_url, category.as_of, reason)

    # ไม่มีข้อกล่าวอ้าง และกฎไม่ให้ข้อสรุป → ตีความตามความครบถ้วนของการสำรวจ
    if category.coverage_status == "surveyed":
        if covered_by_survey(vehicle, category):
            return ("ineligible", "coverage_sweep", "medium", None,
                    category.source_url, category.as_of,
                    "สำรวจหมวดนี้ครบแล้ว ไม่พบรุ่นนี้ในรายการ")
        reason = (
            f"เพิ่มเข้าชุดข้อมูลเมื่อ {vehicle.added_at} หลังการสำรวจหมวดนี้ "
            f"({category.as_of}) — ยังไม่เคยตรวจกับรายการจริง"
            if _parse_date(vehicle.added_at) else
            f"ไม่ทราบวันที่เพิ่มเข้าชุดข้อมูล — บอกไม่ได้ว่าการสำรวจหมวดนี้ "
            f"({category.as_of}) เคยตรวจรุ่นนี้แล้วหรือไม่"
        )
        return ("unverified", None, None, None, category.source_url, "", reason)

    if category.coverage_status == "partial":
        return ("unverified", None, None, None,
                category.source_url, "", "เข้าเกณฑ์เครื่อง แต่ยังไม่ได้ตรวจกับรายการจริง")

    # not_surveyed — ไม่สร้างแถว · รายงานที่ระดับหมวดแทน
    # (ถ้าสร้างแถว จะได้เครื่องหมาย "?" สาดลงรถทุกคันโดยไม่ให้สารสนเทศเพิ่ม)
    return None


def detect_conflict(
    vehicle: Vehicle,
    category: Category,
    claims: list[Claim],
    reference: Reference,
) -> str:
    """กฎบอกอย่าง ข้อกล่าวอ้างบอกอีกอย่าง → คืนข้อความอธิบาย (ว่างถ้าไม่ขัด)"""
    if not claims:
        return ""
    rule = derive(vehicle, category, reference)
    if rule is None:
        return ""
    claim = _best_claim(claims)
    rule_eligibility, _confidence, rule_reason = rule
    if claim.eligibility == "unverified" or claim.eligibility == rule_eligibility:
        return ""
    return (
        f"กฎสรุป '{rule_eligibility}' ({rule_reason}) "
        f"แต่ข้อกล่าวอ้างจาก {claim.basis} สรุป '{claim.eligibility}'"
    )


def resolve_all(
    reference: Reference,
    vehicles: list[Vehicle],
    claims: list[Claim],
    as_of: date | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> list[Resolved]:
    """สร้างชั้น L4 ทั้งหมด — output ทุกชนิดอ่านจากผลลัพธ์นี้เท่านั้น"""
    as_of = as_of or date.today()

    by_cell: dict[tuple[str, str], list[Claim]] = {}
    for claim in claims:
        by_cell.setdefault((claim.vehicle_id, claim.category_id), []).append(claim)

    ordered_categories = sorted(
        reference.categories, key=lambda c: (c.platform, c.order)
    )

    resolved: list[Resolved] = []
    for vehicle in vehicles:
        for category in ordered_categories:
            cell_claims = by_cell.get((vehicle.vehicle_id, category.id), [])
            outcome = resolve_cell(vehicle, category, cell_claims, reference)
            if outcome is None:
                continue
            eligibility, basis, confidence, tier, source_url, checked_at, reason = outcome
            days, stale = _staleness(checked_at, as_of, stale_days)
            resolved.append(
                Resolved(
                    vehicle_id=vehicle.vehicle_id,
                    brand=vehicle.brand,
                    model=vehicle.model,
                    platform=category.platform,
                    category_id=category.id,
                    category_label=category.label,
                    eligibility=eligibility,
                    basis=basis,
                    confidence=confidence,
                    tier=tier,
                    source_url=source_url,
                    checked_at=checked_at,
                    staleness_days=days,
                    is_stale=stale,
                    rule_conflict=detect_conflict(vehicle, category, cell_claims, reference),
                    reason=reason,
                )
            )
    return resolved


def index_by_vehicle(resolved: list[Resolved]) -> dict[str, dict[str, Resolved]]:
    """{vehicle_id: {category_id: Resolved}} — ใช้โดยตัวเรนเดอร์ทุกตัว"""
    index: dict[str, dict[str, Resolved]] = {}
    for row in resolved:
        index.setdefault(row.vehicle_id, {})[row.category_id] = row
    return index
