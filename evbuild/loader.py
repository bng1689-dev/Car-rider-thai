"""อ่านข้อมูลจากดิสก์เข้าสู่โครงสร้างใน model.py

รูปแบบไฟล์
  L0  YAML    — แก้ด้วยมือบ่อย ใส่คอมเมนต์อธิบายเกณฑ์ได้
  L1  JSONL   — 1 บรรทัด = 1 รถ · diff ใน git อ่านง่าย ไม่กระทบแถวอื่น
  L2  JSONL   — 1 บรรทัด = 1 ข้อกล่าวอ้าง
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import yaml

from .model import BodyType, Category, Claim, Launch, Platform, Reference, Vehicle

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REFERENCE_DIR = DATA / "reference"
VEHICLES_PATH = DATA / "vehicles.jsonl"
ELIGIBILITY_PATH = DATA / "eligibility.jsonl"


class DataError(Exception):
    """ข้อมูลอ่านไม่ได้หรือผิดรูปแบบจนไปต่อไม่ได้"""


# ── helpers ──────────────────────────────────────────────────────────────

def _read_yaml(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise DataError(f"ไม่พบไฟล์อ้างอิง: {path}")
    with path.open(encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        raise DataError(f"{path.name}: ต้องเป็น list ที่ระดับบนสุด")
    return loaded


def read_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """คืน (เลขบรรทัด, record) — เลขบรรทัดใช้ชี้จุดผิดตอน validate"""
    if not path.exists():
        raise DataError(f"ไม่พบไฟล์ข้อมูล: {path}")
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw or raw.startswith("//"):
                continue
            try:
                yield lineno, json.loads(raw)
            except json.JSONDecodeError as exc:
                raise DataError(f"{path.name}:{lineno} JSON ผิดรูปแบบ — {exc}") from exc


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


# ── L0 ───────────────────────────────────────────────────────────────────

def load_reference(reference_dir: Path = REFERENCE_DIR) -> Reference:
    platforms = [
        Platform(
            id=r["id"],
            name=r["name"],
            name_th=r.get("name_th", r["name"]),
            commission_pct=r["commission_pct"],
            publishes_model_list=bool(r.get("publishes_model_list", False)),
            source_url=r.get("source_url", ""),
            as_of=str(r.get("as_of", "")),
        )
        for r in _read_yaml(reference_dir / "platforms.yaml")
    ]

    body_types = [
        BodyType(
            id=r["id"],
            label=r.get("label", r["id"]),
            label_th=r.get("label_th", r.get("label", r["id"])),
            aliases=tuple(r.get("aliases", ())),
            eligible_for_ridehailing=bool(r.get("eligible_for_ridehailing", True)),
        )
        for r in _read_yaml(reference_dir / "body_types.yaml")
    ]

    categories = []
    for r in _read_yaml(reference_dir / "categories.yaml"):
        derive = r.get("derive") or {}
        categories.append(
            Category(
                id=r["id"],
                platform=r["platform"],
                legacy_key=r.get("legacy_key", ""),
                label=r.get("label", r["id"]),
                label_th=r.get("label_th", r.get("label", r["id"])),
                order=int(r.get("order", 0)),
                has_official_list=bool(r.get("has_official_list", False)),
                coverage_status=r.get("coverage_status", "not_surveyed"),
                criteria=dict(r.get("criteria") or {}),
                derive_on_pass=derive.get("on_pass", "none"),
                derive_on_fail=derive.get("on_fail", "none"),
                source_url=r.get("source_url", ""),
                as_of=str(r.get("as_of", "")),
                tiers=tuple(r.get("tiers", ())),
                age_max_years=r.get("age_max_years"),
            )
        )

    return Reference(platforms=platforms, categories=categories, body_types=body_types)


# ── L1 / L2 ──────────────────────────────────────────────────────────────

def load_vehicles(path: Path = VEHICLES_PATH) -> list[Vehicle]:
    vehicles = []
    for _lineno, rec in read_jsonl(path):
        launch = rec.get("launch") or {}
        vehicles.append(
            Vehicle(
                vehicle_id=rec["vehicle_id"],
                brand=rec["brand"],
                model=rec["model"],
                body_type=rec["body_type"],
                seats=rec["seats"],
                powertrain=rec.get("powertrain", "bev"),
                launch=Launch(
                    status=launch.get("status", "on_sale"),
                    year=launch.get("year"),
                    quarter=launch.get("quarter"),
                    month=launch.get("month"),
                ),
                size_class=rec.get("size_class"),
                doors=rec.get("doors"),
                specs=dict(rec.get("specs") or {}),
                note=rec.get("note", ""),
                data_issue=rec.get("data_issue", ""),
                added_at=rec.get("added_at", ""),
                sources=list(rec.get("sources") or []),
            )
        )
    return vehicles


def load_claims(path: Path = ELIGIBILITY_PATH) -> list[Claim]:
    claims = []
    for _lineno, rec in read_jsonl(path):
        claims.append(
            Claim(
                vehicle_id=rec["vehicle_id"],
                category_id=rec["category_id"],
                eligibility=rec["eligibility"],
                basis=rec["basis"],
                confidence=rec.get("confidence", "medium"),
                tier=rec.get("tier"),
                source_url=rec.get("source_url", ""),
                checked_at=rec.get("checked_at", ""),
                checked_by=rec.get("checked_by", ""),
                note=rec.get("note", ""),
            )
        )
    return claims


def load_all() -> tuple[Reference, list[Vehicle], list[Claim]]:
    return load_reference(), load_vehicles(), load_claims()
