"""ขั้นตรวจความถูกต้อง — ทำงานก่อนสร้าง output เสมอ

เหตุผลที่ต้องมี: ระบบเดิมไม่บังคับชุดค่าใด ๆ พิมพ์ "yy" แทน "y" แล้ว
  xlsx  → ตัวอักษรสีดำ กลืนกับข้อความปกติ
  html  → ตกไปเป็น pill แดง "รอตรวจสอบ"
  pdf   → หายไปจากตาราง
ผิดคนละแบบทั้งสาม output และไม่มีอันไหนแจ้งเตือน

ที่นี่: ข้อมูลผิด = ล้มก่อนสร้างไฟล์ พร้อมชี้จุดที่ผิด
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import model as M
from .model import Claim, Reference, Vehicle
from .rules import SUPPORTED_CRITERIA

ERROR, WARN = "ERROR", "WARN"


@dataclass
class Issue:
    level: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.where}: {self.message}"


class Validator:
    def __init__(self) -> None:
        self.issues: list[Issue] = []

    def error(self, where: str, message: str) -> None:
        self.issues.append(Issue(ERROR, where, message))

    def warn(self, where: str, message: str) -> None:
        self.issues.append(Issue(WARN, where, message))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == WARN]

    def ok(self, strict: bool = False) -> bool:
        return not self.errors and (not strict or not self.warnings)


def _valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


# ── L0 ───────────────────────────────────────────────────────────────────

def validate_reference(ref: Reference, v: Validator) -> None:
    seen_platform: set[str] = set()
    for p in ref.platforms:
        where = f"platforms.yaml[{p.id}]"
        if p.id in seen_platform:
            v.error(where, "id ซ้ำ")
        seen_platform.add(p.id)
        if not p.source_url:
            v.error(where, "ต้องมี source_url")
        if not _valid_date(p.as_of):
            v.error(where, f"as_of ต้องเป็น YYYY-MM-DD (พบ {p.as_of!r})")

    seen_alias: dict[str, str] = {}
    for b in ref.body_types:
        where = f"body_types.yaml[{b.id}]"
        for alias in b.aliases:
            if alias in seen_alias:
                v.error(where, f"คำพ้อง {alias!r} ซ้ำกับ {seen_alias[alias]}")
            seen_alias[alias] = b.id

    seen_cat: set[str] = set()
    seen_legacy: dict[str, str] = {}
    for c in ref.categories:
        where = f"categories.yaml[{c.id}]"
        if c.id in seen_cat:
            v.error(where, "id ซ้ำ")
        seen_cat.add(c.id)
        if c.platform not in seen_platform:
            v.error(where, f"อ้างถึงแพลตฟอร์มที่ไม่มีอยู่: {c.platform!r}")
        if c.legacy_key:
            if c.legacy_key in seen_legacy:
                v.error(where, f"legacy_key {c.legacy_key!r} ซ้ำกับ {seen_legacy[c.legacy_key]}")
            seen_legacy[c.legacy_key] = c.id
        if c.coverage_status not in M.COVERAGE_STATUS:
            v.error(where, f"coverage_status ไม่ถูกต้อง: {c.coverage_status!r}")
        if c.derive_on_pass not in M.DERIVE_ON_PASS:
            v.error(where, f"derive.on_pass ไม่ถูกต้อง: {c.derive_on_pass!r}")
        if c.derive_on_fail not in M.DERIVE_ON_FAIL:
            v.error(where, f"derive.on_fail ไม่ถูกต้อง: {c.derive_on_fail!r}")
        for key, arg in c.criteria.items():
            if key not in SUPPORTED_CRITERIA:
                v.error(where, f"เกณฑ์ที่ rules engine ไม่รู้จัก: {key!r}")
            elif key.endswith(("_in", "_exclude")) and not isinstance(arg, list):
                v.error(where, f"เกณฑ์ {key} ต้องเป็น list (พบ {type(arg).__name__})")
        for key in ("body_type_in", "body_type_exclude"):
            for body_id in c.criteria.get(key, []) or []:
                if body_id not in ref.body_type_by_id:
                    v.error(where, f"{key} อ้างถึงตัวถังที่ไม่มีอยู่: {body_id!r}")
        if not c.source_url:
            v.error(where, "ต้องมี source_url")
        if not _valid_date(c.as_of):
            v.error(where, f"as_of ต้องเป็น YYYY-MM-DD (พบ {c.as_of!r})")
        # หมวดที่ไม่มี list ทางการ แต่ประกาศว่าสำรวจครบ = ขัดกันเอง
        if c.coverage_status == "surveyed" and c.derive_on_pass == "none" \
                and not c.has_official_list:
            v.warn(where, "ประกาศ surveyed แต่ไม่มี official list — "
                          "ข้อสรุป 'ไม่ผ่าน' จะมาจากการอนุมานล้วน")


# ── L1 ───────────────────────────────────────────────────────────────────

def validate_vehicles(ref: Reference, vehicles: list[Vehicle], v: Validator) -> None:
    seen: dict[str, str] = {}
    missing_doors: list[str] = []
    for veh in vehicles:
        where = f"vehicles.jsonl[{veh.vehicle_id}]"
        if veh.vehicle_id in seen:
            v.error(where, "vehicle_id ซ้ำ")
        seen[veh.vehicle_id] = veh.display_name

        if veh.body_type not in ref.body_type_by_id:
            v.error(where, f"body_type ไม่มีใน body_types.yaml: {veh.body_type!r}")
        if veh.powertrain not in M.POWERTRAIN:
            v.error(where, f"powertrain ไม่ถูกต้อง: {veh.powertrain!r}")
        if veh.size_class is not None and veh.size_class not in M.SIZE_CLASS:
            v.error(where, f"size_class ไม่ถูกต้อง: {veh.size_class!r}")
        if not isinstance(veh.seats, int) or not 2 <= veh.seats <= 9:
            v.error(where, f"seats ต้องเป็นจำนวนเต็ม 2–9 (พบ {veh.seats!r})")
        if veh.doors is not None and veh.doors not in (2, 3, 4, 5):
            v.error(where, f"doors ต้องเป็น 2/3/4/5 หรือ null (พบ {veh.doors!r})")
        if veh.launch.status not in M.LAUNCH_STATUS:
            v.error(where, f"launch.status ไม่ถูกต้อง: {veh.launch.status!r}")
        if veh.launch.quarter is not None and veh.launch.quarter not in (1, 2, 3, 4):
            v.error(where, f"launch.quarter ต้องเป็น 1–4 (พบ {veh.launch.quarter!r})")
        if veh.launch.status in ("announced", "expected") and veh.launch.year is None:
            v.error(where, f"launch.status={veh.launch.status} ต้องระบุ year")
        # ไม่มีวันที่นี้ = บอกไม่ได้ว่าการสำรวจหมวดไหนเคยตรวจรุ่นนี้แล้ว
        if not _valid_date(veh.added_at):
            v.error(where, f"added_at ต้องเป็น YYYY-MM-DD (พบ {veh.added_at!r}) "
                           "— วันที่เพิ่มรุ่นนี้เข้าชุดข้อมูล")

        if veh.doors is None:
            missing_doors.append(veh.vehicle_id)

    # ข้อมูลที่ยังขาด — ไม่ใช่ความผิด แต่ต้องมองเห็น
    # รวบเป็นคำเตือนเดียว ไม่ทวนซ้ำทีละแถว (รายชื่อเต็มอยู่ใน report coverage)
    if missing_doors:
        v.warn(
            "vehicles.jsonl",
            f"ยังไม่ทราบจำนวนประตู {len(missing_doors)}/{len(vehicles)} รุ่น "
            f"— เกณฑ์ doors_in จึงตรวจไม่ได้ (ดู `report coverage`)",
        )


# ── L2 ───────────────────────────────────────────────────────────────────

def validate_claims(
    ref: Reference, vehicles: list[Vehicle], claims: list[Claim], v: Validator
) -> None:
    vehicle_ids = {veh.vehicle_id for veh in vehicles}
    seen: set[tuple[str, str, str]] = set()

    for i, c in enumerate(claims, start=1):
        where = f"eligibility.jsonl[{c.vehicle_id} × {c.category_id}]"

        if c.vehicle_id not in vehicle_ids:
            v.error(where, f"อ้างถึงรถที่ไม่มีใน vehicles.jsonl: {c.vehicle_id!r}")
        category = ref.category_by_id.get(c.category_id)
        if category is None:
            v.error(where, f"อ้างถึงหมวดที่ไม่มีใน categories.yaml: {c.category_id!r}")
            continue

        if c.eligibility not in M.ELIGIBILITY:
            v.error(where, f"eligibility ไม่ถูกต้อง: {c.eligibility!r}")
        if c.basis not in M.BASIS:
            v.error(where, f"basis ไม่ถูกต้อง: {c.basis!r}")
        if c.confidence not in M.CONFIDENCE:
            v.error(where, f"confidence ไม่ถูกต้อง: {c.confidence!r}")

        key = (c.vehicle_id, c.category_id, c.basis)
        if key in seen:
            v.warn(where, f"มีข้อกล่าวอ้างซ้ำที่ basis เดียวกัน ({c.basis}) — "
                          "resolve จะเลือกอันที่ checked_at ใหม่กว่า")
        seen.add(key)

        # tier ใส่ได้เฉพาะหมวดที่ประกาศชั้นย่อยไว้
        if c.tier is not None:
            if not category.tiers:
                v.error(where, f"หมวด {category.id} ไม่ได้ประกาศ tiers แต่ข้อกล่าวอ้างระบุ tier={c.tier!r}")
            elif c.tier not in category.tiers:
                v.error(where, f"tier {c.tier!r} ไม่อยู่ใน {list(category.tiers)}")

        # กฎที่เปลี่ยน "ควรจะบันทึกที่มานะ" ให้เป็นสิ่งที่ระบบบังคับ
        if c.basis == "official_list":
            if not c.source_url:
                v.error(where, "basis=official_list ต้องมี source_url")
            if not c.checked_at:
                v.error(where, "basis=official_list ต้องมี checked_at")
        if c.checked_at and not _valid_date(c.checked_at):
            v.error(where, f"checked_at ต้องเป็น YYYY-MM-DD (พบ {c.checked_at!r})")
        if c.eligibility == "unverified" and c.basis != "manual":
            v.warn(where, f"eligibility=unverified คู่กับ basis={c.basis!r} "
                          "— ปกติควรเป็น manual (คนบันทึกว่ายังไม่ได้ตรวจ)")

    # หมวดที่ประกาศว่า "ยังไม่ได้สำรวจ" แต่มีข้อกล่าวอ้างแล้ว = ประกาศไม่ตรงข้อมูล
    # รายงานจะยังนับข้อกล่าวอ้างเหล่านี้ถูกต้อง แต่ coverage_status ควรถูกแก้
    # เป็น partial เพื่อให้รถที่เหลือขึ้นเป็น "รอตรวจสอบ" รายคัน
    claimed_categories = {c.category_id for c in claims}
    for category in ref.categories:
        if category.coverage_status == "not_surveyed" and category.id in claimed_categories:
            count = sum(1 for c in claims if c.category_id == category.id)
            v.warn(
                f"categories.yaml[{category.id}]",
                f"ประกาศ not_surveyed แต่มีข้อกล่าวอ้างแล้ว {count} แถว "
                "— พิจารณาเปลี่ยนเป็น partial",
            )


# ── ตรรกะข้ามชั้น ────────────────────────────────────────────────────────

def validate_logic(ref: Reference, vehicles: list[Vehicle], resolved, v: Validator) -> None:
    """ตรวจความขัดแย้งเชิงตรรกะหลัง resolve

    ตัวอย่าง: ผ่าน Grab Premium แต่ไม่ผ่าน GrabCar เป็นไปไม่ได้
    (Premium เป็นหมวดยกระดับจากหมวดพื้นฐาน)
    """
    base_of = {"grab": "grab.car", "bolt": "bolt.basic"}
    index: dict[tuple[str, str], str] = {
        (r.vehicle_id, r.category_id): r.eligibility for r in resolved
    }
    by_id = {veh.vehicle_id: veh for veh in vehicles}

    for (vehicle_id, category_id), eligibility in index.items():
        category = ref.category_by_id[category_id]
        base_id = base_of.get(category.platform)
        if base_id is None or category_id == base_id:
            continue
        if eligibility != "eligible":
            continue
        base_eligibility = index.get((vehicle_id, base_id))
        if base_eligibility == "ineligible":
            name = by_id[vehicle_id].display_name
            v.error(
                f"logic[{vehicle_id}]",
                f"{name}: ผ่าน {category.label} แต่ไม่ผ่าน "
                f"{ref.category_by_id[base_id].label} — ขัดกันเอง",
            )

    for row in resolved:
        if row.rule_conflict:
            v.warn(
                f"conflict[{row.vehicle_id} × {row.category_id}]",
                f"{row.brand} {row.model}: {row.rule_conflict}",
            )


def validate_structure(ref, vehicles, claims, v: Validator | None = None) -> Validator:
    """ตรวจรูปร่างของข้อมูลล้วน ๆ — ไม่ต้องผ่าน resolve ก่อน

    ต้องเรียกตัวนี้ให้จบและไม่มี error ก่อน resolve เสมอ เพราะ rules engine
    สมมติว่าชนิดข้อมูลถูกต้องแล้ว (เช่น seats เป็นจำนวนเต็ม) — ถ้าปล่อยให้
    resolve ทำงานก่อน ข้อมูลผิดชนิดจะทำให้พังด้วย traceback แทนที่จะได้
    ข้อความบอกจุดที่ผิด ซึ่งขัดกับสัญญาของคำสั่ง validate เอง
    """
    v = v or Validator()
    validate_reference(ref, v)
    validate_vehicles(ref, vehicles, v)
    validate_claims(ref, vehicles, claims, v)
    return v


def validate_all(ref, vehicles, claims, resolved=None) -> Validator:
    v = validate_structure(ref, vehicles, claims)
    if resolved is not None:
        validate_logic(ref, vehicles, resolved, v)
    return v
