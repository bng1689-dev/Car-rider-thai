"""โครงสร้างข้อมูลกลางของทุกชั้น (L0–L4)

ไฟล์นี้เป็นที่เดียวที่นิยามว่า "ข้อมูลหน้าตาอย่างไร" — ชั้นอื่นอ้างอิงจากที่นี่
ไม่มีการอ่านไฟล์หรือ logic ทางธุรกิจในไฟล์นี้
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# ── ชุดค่าที่ยอมรับ (enum) ────────────────────────────────────────────────
# ระบบเดิมไม่มีการบังคับชุดค่า — พิมพ์ "yy" แทน "y" แล้วผ่านไปได้เงียบ ๆ
# และให้ผลผิดคนละแบบใน 3 output

ELIGIBILITY = ("eligible", "ineligible", "unverified")
"""ผลการพิจารณา — แยกจาก 'ที่มา' และ 'ความเชื่อมั่น' (เดิมยุบรวมใน y/i/p/-)"""

BASIS = ("official_list", "manual", "spec_inference", "rule_derived", "coverage_sweep")
"""ที่มาของข้อสรุป · เรียงตามลำดับความน่าเชื่อถือ (ดู resolve.PRECEDENCE)

coverage_sweep = สรุปจาก 'ไม่พบในรายการที่สำรวจครบแล้ว' — เป็นการอนุมานจาก
การไม่มีหลักฐาน จึงอ่อนที่สุด และใช้ได้เฉพาะหมวดที่ประกาศ coverage_status:
surveyed เท่านั้น"""

CONFIDENCE = ("high", "medium", "low")

COVERAGE_STATUS = ("surveyed", "partial", "not_surveyed")

LAUNCH_STATUS = ("on_sale", "announced", "expected")

POWERTRAIN = ("bev", "phev", "hev", "ice")

SIZE_CLASS = ("compact", "standard", "large")

DERIVE_ON_PASS = ("eligible", "none")
DERIVE_ON_FAIL = ("ineligible", "none")


# ── L0 REFERENCE ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    name_th: str
    commission_pct: float
    publishes_model_list: bool
    source_url: str
    as_of: str


@dataclass(frozen=True)
class BodyType:
    id: str
    label: str
    label_th: str
    aliases: tuple[str, ...] = ()
    eligible_for_ridehailing: bool = True


@dataclass(frozen=True)
class Category:
    id: str
    platform: str
    legacy_key: str
    label: str
    label_th: str
    order: int
    has_official_list: bool
    coverage_status: str
    criteria: dict[str, Any]
    derive_on_pass: str
    derive_on_fail: str
    source_url: str
    as_of: str
    tiers: tuple[str, ...] = ()
    age_max_years: int | None = None


@dataclass
class Reference:
    """L0 ทั้งชั้น พร้อม index สำหรับค้นหา"""
    platforms: list[Platform]
    categories: list[Category]
    body_types: list[BodyType]

    def __post_init__(self) -> None:
        self.platform_by_id = {p.id: p for p in self.platforms}
        self.category_by_id = {c.id: c for c in self.categories}
        self.category_by_legacy_key = {c.legacy_key: c for c in self.categories}
        self.body_type_by_id = {b.id: b for b in self.body_types}
        # ตารางเทียบคำพ้อง — ใช้ตอน migrate และตอน validate
        self.body_type_by_alias = {
            alias: b.id for b in self.body_types for alias in b.aliases
        }

    def categories_of(self, platform_id: str) -> list[Category]:
        return sorted(
            (c for c in self.categories if c.platform == platform_id),
            key=lambda c: c.order,
        )


# ── L1 FACTS ─────────────────────────────────────────────────────────────

@dataclass
class Launch:
    """เวลาเปิดตัว — เดิมกระจายอยู่ 2 ที่ (status + note) จนขัดกันเอง"""
    status: str
    year: int | None = None
    quarter: int | None = None
    month: int | None = None


@dataclass
class Vehicle:
    """คุณสมบัติของรถรุ่นหนึ่ง — ตอบคำถาม 'รถคันนี้เป็นอย่างไร' เท่านั้น
    ไม่ตอบว่า 'ขับหมวดไหนได้' (คนละคำถาม จึงอยู่คนละตาราง — ดู Claim)
    """
    vehicle_id: str
    brand: str
    model: str
    body_type: str
    seats: int
    powertrain: str
    launch: Launch
    size_class: str | None = None
    doors: int | None = None        # None = ยังไม่ทราบ (ไม่ใช่ "ไม่มีประตู")
    specs: dict[str, Any] = field(default_factory=dict)
    note: str = ""
    data_issue: str = ""   # ความขัดแย้งในข้อมูลที่ต้องให้คนตัดสิน (ห้ามเดาแทน)
    sources: list[dict[str, str]] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return f"{self.brand} {self.model}"


# ── L2 CLAIMS ────────────────────────────────────────────────────────────

@dataclass
class Claim:
    """ข้อกล่าวอ้างหนึ่งข้อ = รถหนึ่งคัน × หมวดหนึ่งหมวด

    รูปแบบยาว (long) แทนคอลัมน์กว้าง 10 คอลัมน์ของระบบเดิม
    เพิ่มหมวดใหม่ = เพิ่มแถวใน categories.yaml ไฟล์เดียว ไม่ต้องแตะโค้ด
    """
    vehicle_id: str
    category_id: str
    eligibility: str
    basis: str
    confidence: str = "medium"
    tier: str | None = None
    source_url: str = ""
    checked_at: str = ""
    checked_by: str = ""
    note: str = ""


# ── L4 RESOLVED ──────────────────────────────────────────────────────────

@dataclass
class Resolved:
    """ผลสุดท้ายหลังรวมกฎ + ข้อกล่าวอ้าง + ลำดับความสำคัญ

    output ทุกชนิดอ่านจากที่นี่เท่านั้น จึงไม่มีทางตอบไม่ตรงกันได้
    (ระบบเดิมมี logic กระจายอยู่ 3 ที่ และตอบไม่ตรงกันจริงเมื่อข้อมูลผิด)
    """
    vehicle_id: str
    brand: str
    model: str
    platform: str
    category_id: str
    category_label: str
    eligibility: str
    basis: str | None
    confidence: str | None
    tier: str | None = None
    source_url: str = ""
    checked_at: str = ""
    staleness_days: int | None = None
    is_stale: bool = False
    rule_conflict: str = ""     # กฎขัดกับข้อกล่าวอ้าง → สัญญาณว่ากฎต้องแก้
    reason: str = ""            # เหตุผลที่อ่านออก ใช้ตอน debug และใน export

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
