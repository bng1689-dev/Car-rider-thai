"""ตัวช่วยสำหรับเทสต์

เทสต์ทั้งหมดใช้ unittest ของ stdlib — รันได้ด้วย `python -m unittest` โดยไม่ต้องลง
อะไรเพิ่ม ยกเว้น test_render_xlsx ที่ต้องมี openpyxl (ข้ามให้อัตโนมัติถ้าไม่มี)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evbuild.loader import load_reference  # noqa: E402
from evbuild.model import Claim, Launch, Reference, Vehicle  # noqa: E402

_REFERENCE: Reference | None = None


def make_reference() -> Reference:
    """โหลด L0 จริงครั้งเดียวแล้วใช้ซ้ำ — เทสต์ควรตรวจกฎที่ใช้งานจริง
    ไม่ใช่กฎจำลองที่อาจเพี้ยนไปจากของจริง
    """
    global _REFERENCE
    if _REFERENCE is None:
        _REFERENCE = load_reference()
    return _REFERENCE


def make_vehicle(**overrides) -> Vehicle:
    base = dict(
        vehicle_id="test-car",
        brand="Test",
        model="Car",
        body_type="sedan",
        seats=5,
        powertrain="bev",
        launch=Launch(status="on_sale"),
        size_class="standard",
        doors=None,
    )
    base.update(overrides)
    return Vehicle(**base)


def make_claim(**overrides) -> Claim:
    base = dict(
        vehicle_id="test-car",
        category_id="grab.premium",
        eligibility="eligible",
        basis="official_list",
        confidence="high",
        source_url="https://grabdriverth.com/",
        checked_at="2025-09-15",
        checked_by="tester",
    )
    base.update(overrides)
    return Claim(**base)
