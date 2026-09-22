"""L3 — กฎการจัดหมวด

กฎทั้งหมดเป็น "ข้อมูล" (criteria ใน categories.yaml) ไม่ใช่โค้ด
ไฟล์นี้มีแค่ตัวประเมิน criteria แบบทั่วไป จึงไม่มีกฎซ่อนอยู่ในโค้ดเลย
เพิ่มหมวดใหม่ = เพิ่มแถวใน YAML · เปลี่ยนเกณฑ์ = แก้ YAML

เดิมกฎเหล่านี้อยู่ใน README เป็นร้อยแก้ว คนจึงต้องบังคับใช้เองทีละช่อง
รวม 351 ช่องที่พิสูจน์แล้วว่าคำนวณได้ 100% (gcar / bbasic / bgreen)
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import Category, Reference, Vehicle

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"


@dataclass
class Verdict:
    """ผลการประเมิน criteria ของหมวดหนึ่งกับรถหนึ่งคัน"""
    result: str                      # PASS | FAIL
    failed: list[str]                # เกณฑ์ที่ตก
    unknown: list[str]               # เกณฑ์ที่ประเมินไม่ได้เพราะข้อมูลขาด

    @property
    def is_certain(self) -> bool:
        """ประเมินได้ครบทุกเกณฑ์ (ไม่มีข้อมูลขาด)"""
        return not self.unknown

    def describe(self) -> str:
        if self.failed:
            return "ตกเกณฑ์: " + ", ".join(self.failed)
        if self.unknown:
            return "ผ่านเท่าที่ตรวจได้ · ข้อมูลขาด: " + ", ".join(self.unknown)
        return "ผ่านทุกเกณฑ์"


# ── ตัวประเมินรายเกณฑ์ ───────────────────────────────────────────────────
# แต่ละตัวคืน PASS / FAIL / UNKNOWN
# UNKNOWN = ข้อมูลของรถไม่พอจะตัดสิน — ห้ามแปลว่า "ตก" เด็ดขาด
# (นี่คือความผิดพลาดที่ระบบเดิมทำ: "-" ตัวเดียวแทนทั้ง "ไม่ผ่าน" และ "ไม่รู้")

def _check_in(value, allowed) -> str:
    if value is None:
        return UNKNOWN
    return PASS if value in allowed else FAIL


def _check_not_in(value, blocked) -> str:
    if value is None:
        return UNKNOWN
    return FAIL if value in blocked else PASS


def _check_min(value, minimum) -> str:
    if value is None:
        return UNKNOWN
    return PASS if value >= minimum else FAIL


def _check_max(value, maximum) -> str:
    if value is None:
        return UNKNOWN
    return PASS if value <= maximum else FAIL


CRITERIA_EVALUATORS = {
    "powertrain_in":     lambda v, arg: _check_in(v.powertrain, arg),
    "body_type_in":      lambda v, arg: _check_in(v.body_type, arg),
    "body_type_exclude": lambda v, arg: _check_not_in(v.body_type, arg),
    "size_class_in":     lambda v, arg: _check_in(v.size_class, arg),
    "doors_in":          lambda v, arg: _check_in(v.doors, arg),
    "seats_min":         lambda v, arg: _check_min(v.seats, arg),
    "seats_max":         lambda v, arg: _check_max(v.seats, arg),
}

SUPPORTED_CRITERIA = frozenset(CRITERIA_EVALUATORS)


def evaluate(vehicle: Vehicle, category: Category) -> Verdict:
    """ประเมินรถหนึ่งคันกับเกณฑ์ของหมวดหนึ่ง"""
    failed: list[str] = []
    unknown: list[str] = []

    for key, arg in category.criteria.items():
        evaluator = CRITERIA_EVALUATORS.get(key)
        if evaluator is None:
            # validate จับไว้ก่อนถึงตรงนี้แล้ว — กันไว้อีกชั้นเผื่อเรียกตรง
            raise ValueError(f"เกณฑ์ที่ไม่รู้จัก: {key} (หมวด {category.id})")
        outcome = evaluator(vehicle, arg)
        if outcome == FAIL:
            failed.append(f"{key}={arg}")
        elif outcome == UNKNOWN:
            unknown.append(key)

    return Verdict(result=FAIL if failed else PASS, failed=failed, unknown=unknown)


def body_type_blocks_ridehailing(vehicle: Vehicle, reference: Reference) -> bool:
    """ตัวถังที่ทั้งสองแอปไม่รับ (กระบะ) — นิยามอยู่ใน body_types.yaml
    เดิมเป็น hardcode `e["gcar"] == "-"` กระจายอยู่ใน build.py และ template
    """
    body = reference.body_type_by_id.get(vehicle.body_type)
    return body is not None and not body.eligible_for_ridehailing


def derive(vehicle: Vehicle, category: Category, reference: Reference):
    """สรุปผลจากกฎอย่างเดียว (ยังไม่รวมข้อกล่าวอ้างของคน)

    คืน (eligibility, confidence, reason) หรือ None ถ้ากฎไม่ให้ข้อสรุป
    """
    if body_type_blocks_ridehailing(vehicle, reference):
        return "ineligible", "high", "ตัวถังไม่รับงานเรียกรถ (กระบะ)"

    verdict = evaluate(vehicle, category)

    if verdict.result == FAIL:
        if category.derive_on_fail == "ineligible":
            return "ineligible", "high", verdict.describe()
        return None

    if category.derive_on_pass == "eligible":
        # ข้อมูลขาดบางส่วน → ยังสรุปว่าผ่านได้ แต่ลดความเชื่อมั่นและบันทึกไว้
        confidence = "high" if verdict.is_certain else "medium"
        return "eligible", confidence, verdict.describe()

    return None
