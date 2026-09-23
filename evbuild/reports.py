"""รายงานที่ระบบเดิมทำไม่ได้เลย

ระบบเดิมใช้ "-" ตัวเดียวแทนทั้ง "ตรวจแล้วไม่ผ่าน" และ "ยังไม่เคยตรวจ"
เมื่อแยกสองอย่างนี้ไม่ได้ ก็ไม่มีทางรู้ว่างานตรวจสอบยังค้างอยู่ตรงไหน
ชั้น L2/L4 แยกไว้แล้ว รายงานพวกนี้จึงเกิดขึ้นได้
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from . import view
from .model import Reference, Resolved, Vehicle

LIST_LIMIT = 12


def coverage(
    reference: Reference, vehicles: list[Vehicle], resolved: list[Resolved]
) -> list[str]:
    """หมวดไหน/รุ่นไหนยังไม่ได้ตรวจ — พ่นออกมาเป็น checklist ใช้งานต่อได้"""
    lines: list[str] = ["ความครบถ้วนของการสำรวจ (coverage)", "=" * 60]

    by_category: dict[str, Counter] = defaultdict(Counter)
    for row in resolved:
        by_category[row.category_id][row.eligibility] += 1

    gaps = {g["category"].id: g for g in view.survey_gaps(reference, vehicles, resolved)}
    total = len(vehicles)
    for category in sorted(reference.categories, key=lambda c: (c.platform, c.order)):
        counts = by_category.get(category.id, Counter())
        rows = sum(counts.values())
        lines.append(
            f"\n{category.id:<16} {category.label:<16} [{category.coverage_status}]"
        )
        if category.coverage_status == "not_surveyed":
            gap = gaps[category.id]
            candidates = gap["candidates"]
            # ถ้อยคำมาจากข้อมูลจริง ไม่ใช่จากธง coverage_status
            lines.append("  " + view.survey_gap_summary(gap))
            for r in gap["pending"][:LIST_LIMIT]:
                lines.append(f"     • {r.brand} {r.model} — มีข้อกล่าวอ้างแล้ว (รอตรวจสอบ)")
            if candidates:
                lines.append(f"  ยังไม่แตะเลย {len(candidates)} รุ่น:")
                for v in candidates[:LIST_LIMIT]:
                    lines.append(f"     - {v.display_name} ({v.seats} ที่นั่ง)")
                if len(candidates) > LIST_LIMIT:
                    lines.append(f"     … และอีก {len(candidates) - LIST_LIMIT} รุ่น "
                                 f"(ดูทั้งหมดในชีต 'งานค้าง' ของไฟล์ xlsx)")
                # เกณฑ์หลวมเกินกว่าจะคัดกรองได้จริง → บอกตรง ๆ ว่ารายการนี้ยังไม่มีประโยชน์
                if len(candidates) > total * 0.8:
                    lines.append("  ⚠ เกณฑ์ของหมวดนี้ยังหลวมเกินไป (แทบทุกรุ่นผ่าน) "
                                 "— ต้องเติม criteria ใน categories.yaml ก่อน")
            continue

        lines.append(
            f"  ผ่าน {counts['eligible']:>3} · ไม่ผ่าน {counts['ineligible']:>3} "
            f"· ยังไม่รู้ {counts['unverified']:>3}   (รวม {rows} แถว)"
        )
        if counts["unverified"]:
            pending = [r for r in resolved
                       if r.category_id == category.id and r.eligibility == "unverified"]
            lines.append(f"  รอตรวจสอบ {len(pending)} รุ่น:")
            for r in pending[:LIST_LIMIT]:
                lines.append(f"     - {r.brand} {r.model}")
            if len(pending) > LIST_LIMIT:
                lines.append(f"     … และอีก {len(pending) - LIST_LIMIT} รุ่น")

    # ช่องว่างของข้อมูลในชั้น L1
    missing_doors = [v for v in vehicles if v.doors is None]
    if missing_doors:
        lines += [
            "", "-" * 60,
            f"ข้อมูลรถที่ยังขาด: จำนวนประตู {len(missing_doors)}/{total} รุ่น",
            "  เกณฑ์ doors_in จึงตรวจไม่ได้ — กฎยังสรุปว่าผ่าน แต่ลดความเชื่อมั่น",
            "  เป็น medium แทน high (ไม่ตีความว่า 'ตก' เพราะไม่รู้ ≠ ไม่ผ่าน)",
        ]
    return lines


def stale(resolved: list[Resolved], days: int, as_of: date) -> list[str]:
    """ข้อกล่าวอ้างที่เก่าเกินกำหนด — ข้อมูลไม่มีวันที่กำกับคือข้อมูลที่อ้างอิงไม่ได้"""
    stale_rows = [r for r in resolved if r.is_stale]
    undated = [r for r in resolved if r.staleness_days is None]

    lines = [
        f"ความสดของข้อมูล ณ {as_of.isoformat()} (เพดาน {days} วัน)",
        "=" * 60,
        f"เกินเพดาน  {len(stale_rows)} / {len(resolved)} แถว",
        f"ไม่มีวันที่ {len(undated)} แถว",
    ]
    if stale_rows:
        worst = sorted(stale_rows, key=lambda r: -(r.staleness_days or 0))
        lines.append("\nเก่าที่สุด:")
        for r in worst[:15]:
            lines.append(
                f"  {r.staleness_days:>5} วัน  {r.brand} {r.model} × {r.category_label} "
                f"({r.basis})"
            )
        if len(worst) > 15:
            lines.append(f"  … และอีก {len(worst) - 15} แถว")
    return lines


def qa(reference: Reference, vehicles: list[Vehicle], resolved: list[Resolved]) -> list[str]:
    """ความผิดปกติที่ต้องให้คนตัดสิน — ระบบชี้จุดให้ แต่ไม่ตัดสินแทน"""
    lines = ["ข้อสังเกตที่ต้องให้คนตัดสิน (QA)", "=" * 60]

    conflicts = [r for r in resolved if r.rule_conflict]
    lines.append(f"\n1. กฎขัดกับข้อกล่าวอ้าง — {len(conflicts)} จุด")
    if conflicts:
        lines.append("   (ข้อกล่าวอ้างชนะตามลำดับความสำคัญ แต่บันทึกไว้เพราะ")
        lines.append("    กฎที่ขัดกับความจริงคือกฎที่ต้องแก้)")
        for r in conflicts:
            lines.append(f"   • {r.brand} {r.model} × {r.category_label}")
            lines.append(f"     {r.rule_conflict}")
    else:
        lines.append("   ไม่พบ")

    flagged = [v for v in vehicles if v.data_issue]
    lines.append(f"\n2. ความไม่สอดคล้องภายในข้อมูลรถ — {len(flagged)} จุด")
    if flagged:
        lines.append("   (ระบบชี้จุดให้ แต่ไม่ตัดสินแทน — การเดาแทนคนคือการแต่งข้อมูล)")
        for v in flagged:
            lines.append(f"   • {v.display_name}: {v.data_issue}")
    else:
        lines.append("   ไม่พบ")

    # หมวดที่ข้อกล่าวอ้างไม่เข้ารูปเป็นกฎเดียว → เตือนว่ายังต้องพึ่งวิจารณญาณคน
    lines.append("\n3. หมวดที่ยังไม่มีเกณฑ์เครื่องครบ")
    for category in reference.categories:
        if category.derive_on_pass == "none" and len(category.criteria) <= 1:
            eligible = sum(1 for r in resolved
                           if r.category_id == category.id and r.eligibility == "eligible")
            lines.append(
                f"   • {category.id} ({category.label}) — ผ่าน {eligible} รุ่น "
                f"จากการอนุมานรายคัน ไม่ได้มาจากกฎเดียวที่เขียนเป็น criteria ได้"
            )
    return lines


def summary(reference: Reference, vehicles: list[Vehicle], resolved: list[Resolved]) -> list[str]:
    counts = Counter(r.eligibility for r in resolved)
    basis_counts = Counter(r.basis for r in resolved if r.basis)
    lines = [
        f"รถ {len(vehicles)} รุ่น × หมวด {len(reference.categories)} หมวด "
        f"→ ข้อสรุป {len(resolved)} แถว",
        f"  ผ่าน {counts['eligible']} · ไม่ผ่าน {counts['ineligible']} "
        f"· ยังไม่รู้ {counts['unverified']}",
        "  ที่มาของข้อสรุป: " + " · ".join(
            f"{basis} {n}" for basis, n in basis_counts.most_common()
        ),
    ]
    return lines
