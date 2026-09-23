"""สร้างเว็บแอป — หน้าเดียวที่เปิดในเบราว์เซอร์ได้ พร้อมไฟล์ส่งออกข้างกัน

    outputs/webapp/index.html       ตัวแอป (ข้อมูลและไฟล์ xlsx ฝังอยู่ในหน้า)
    outputs/webapp/exports/*        pdf · csv ชุดเดียวกับที่ build สร้าง — เผยแพร่คู่กับหน้า

ตามหลักของระบบ: ตรรกะทั้งหมดอยู่ฝั่ง Python — คิวงานตรวจสอบ ช่องว่างการสำรวจ
เหตุผลของแต่ละข้อสรุป ถูกคำนวณที่นี่แล้วส่งให้แอปเป็นข้อมูล ตัวแอปมีหน้าที่
แสดงผลและรับผลตรวจที่คนบันทึกเท่านั้น จึงตอบไม่ตรงกับ report / xlsx ไม่ได้

template เป็นเนื้อหาส่วน body ล้วน ๆ (ไม่มี <html>/<head>/<body>) เพราะ
แพลตฟอร์มที่โฮสต์แอปห่อโครงหน้าให้เองตอนเผยแพร่
"""
from __future__ import annotations

import base64
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from .. import view
from ..model import Reference, Resolved, Vehicle
from ..resolve import index_by_vehicle
from . import OUTPUTS, TEMPLATES, fill_template, json_for_script

# หมวดที่ผ่านเกณฑ์เครื่องเกินสัดส่วนนี้ของรถทั้งหมด = เกณฑ์หลวมเกินกว่าจะคัดกรองได้
# ไม่แตกเป็นงานรายคัน (มิฉะนั้นคิวจะเต็มไปด้วยงานที่ไม่ได้บอกอะไร)
LOOSE_CRITERIA_RATIO = 0.8

# ชนิดไฟล์ที่แพลตฟอร์มไม่เสิร์ฟเป็นไฟล์ประกอบของหน้า (เอกสาร Office)
# ฝังเป็น base64 ในข้อมูลของหน้าแทน แล้วให้ผู้ใช้บันทึกผ่านความสามารถ downloads
# ชนิดอื่น (pdf, csv) เผยแพร่เป็นไฟล์ประกอบ แอปโหลดเมื่อกดดาวน์โหลดเท่านั้น หน้าจึงเบา
EMBEDDED_SUFFIXES = {".xlsx"}

# ไฟล์ที่แอปให้ดาวน์โหลด — (ตัวเรนเดอร์, ชื่อไฟล์, คำอธิบาย)
EXPORTS = (
    ("xlsx", "EV-Grab-Bolt-Thailand.xlsx",
     "Excel 3 ชีต — เมทริกซ์ · ข้อกล่าวอ้างพร้อมที่มา · งานค้าง"),
    ("pdf", "analysis.pdf",
     "เอกสารวิเคราะห์ฉบับเต็ม พร้อมหัวข้อที่มาและความสดของข้อมูล"),
    ("csv", "i2-links.csv",
     "ตาราง entity-link สำหรับนำเข้า i2 Analyst's Notebook"),
    ("csv", "resolved.csv",
     "ข้อสรุปทุกแถวรูปแบบยาว พร้อมที่มา ความเชื่อมั่น และวันที่ตรวจ"),
)


def _cell(row: Resolved) -> dict[str, Any]:
    """หนึ่งช่องของเมทริกซ์ — ละฟิลด์ว่างเพื่อลดขนาดหน้า"""
    cell: dict[str, Any] = {"eligibility": row.eligibility}
    for key, value in (
        ("basis", row.basis),
        ("confidence", row.confidence),
        ("tier", row.tier),
        ("checked_at", row.checked_at),
        ("source_url", row.source_url),
        ("reason", row.reason),
        ("conflict", row.rule_conflict),
    ):
        if value:
            cell[key] = value
    return cell


def build_queue(
    reference: Reference, vehicles: list[Vehicle], resolved: list[Resolved]
) -> list[dict[str, Any]]:
    """งานที่ต้องให้คนตรวจ แบ่งเป็นกลุ่มตามชนิดของงาน

    kind:
      unverified    ยังไม่รู้ผล — ข้อกล่าวอ้าง "รอตรวจ" · หมวดที่สำรวจบางส่วน
                    · หรือรถที่เพิ่มเข้าชุดข้อมูลหลังการสำรวจหมวดนั้น
      not_surveyed  หมวดที่ยังไม่มีใครสำรวจ แต่มีรถเข้าเกณฑ์เครื่อง (เช่น GrabVan)
      conflict      กฎขัดกับข้อกล่าวอ้าง — ควรตรวจกับรายการจริงอีกครั้ง
      data_issue    ข้อมูลรถขัดกันเอง — แก้ในไฟล์ข้อมูลรถ ไม่ใช่งานบันทึกสิทธิ์
    """
    ordered = [c for p in reference.platforms for c in reference.categories_of(p.id)]
    groups: list[dict[str, Any]] = []

    for category in ordered:
        pending = [r.vehicle_id for r in resolved
                   if r.category_id == category.id and r.eligibility == "unverified"]
        if pending:
            groups.append({
                "kind": "unverified",
                "key": f"unverified:{category.id}",
                "category_id": category.id,
                "title": f"รอตรวจ {category.label}",
                "detail": ("ยังไม่รู้ว่าผ่านหรือไม่ — ตรวจกับรายการจริงแล้วบันทึกผล "
                           "(เหตุผลที่ยังไม่รู้ของแต่ละรุ่นอยู่ในรายละเอียดของช่องนั้น)"),
                "items": pending,
            })

    total = len(vehicles)
    for gap in view.survey_gaps(reference, vehicles, resolved):
        category = gap["category"]
        candidates = [v.vehicle_id for v in gap["candidates"]]
        loose = len(candidates) > total * LOOSE_CRITERIA_RATIO
        groups.append({
            "kind": "not_surveyed",
            "key": f"not_surveyed:{category.id}",
            "category_id": category.id,
            "title": f"สำรวจ {category.label}",
            "detail": ("เกณฑ์ของหมวดนี้ยังหลวมเกินไป แทบทุกรุ่นผ่านเกณฑ์เครื่อง "
                       "จึงยังไม่แตกเป็นงานรายคัน — ต้องเติมเกณฑ์ใน categories.yaml ก่อน"
                       if loose else
                       "ทั้งหมวดยังไม่มีใครสำรวจ รุ่นเหล่านี้ผ่านเกณฑ์เครื่องแล้ว รอตรวจกับรายการจริง"),
            "loose": loose,
            "candidate_count": len(candidates),
            "items": [] if loose else candidates,
        })

    conflicts = [r for r in resolved if r.rule_conflict]
    if conflicts:
        groups.append({
            "kind": "conflict",
            "key": "conflict",
            "title": "กฎขัดกับข้อกล่าวอ้าง",
            "detail": ("ข้อกล่าวอ้างชนะตามลำดับความสำคัญอยู่แล้ว แต่ควรยืนยันกับรายการจริงอีกครั้ง "
                       "ถ้ารายการจริงยืนยัน แปลว่ากฎต้องแก้"),
            "items": [{"vehicle_id": r.vehicle_id, "category_id": r.category_id}
                      for r in conflicts],
        })

    issues = [v for v in vehicles if v.data_issue]
    if issues:
        groups.append({
            "kind": "data_issue",
            "key": "data_issue",
            "title": "ข้อมูลรถขัดกันเอง",
            "detail": ("ไม่ใช่งานบันทึกสิทธิ์ — ต้องตัดสินว่าค่าไหนถูกแล้วแก้ใน data/vehicles.jsonl "
                       "ระบบไม่เดาแทน เพราะการเดาแทนคนคือการแต่งข้อมูล"),
            "items": [v.vehicle_id for v in issues],
        })

    return groups


def build_payload(
    reference: Reference,
    vehicles: list[Vehicle],
    resolved: list[Resolved],
    as_of: date,
    stale_days: int,
    exports: list[dict[str, Any]],
) -> dict[str, Any]:
    index = index_by_vehicle(resolved)
    checked_dates = sorted({r.checked_at for r in resolved if r.checked_at})

    return {
        "meta": {
            "built_on": as_of.isoformat(),
            "data_checked_latest": checked_dates[-1] if checked_dates else "",
            "stale_days": stale_days,
            "vehicle_count": len(vehicles),
            "conclusion_count": len(resolved),
        },
        "platforms": [
            {
                "id": p.id,
                "name": p.name,
                "commission_pct": p.commission_pct,
                "publishes_model_list": p.publishes_model_list,
                "source_url": p.source_url,
                "note": view.platform_note(reference, p.id),
            }
            for p in reference.platforms
        ],
        "categories": [
            {
                "id": c.id,
                "platform": c.platform,
                "label": c.label,
                "label_th": c.label_th,
                "has_official_list": c.has_official_list,
                "coverage_status": c.coverage_status,
                "tiers": list(c.tiers),
                "source_url": c.source_url,
            }
            for p in reference.platforms for c in reference.categories_of(p.id)
        ],
        "labels": {
            "eligibility": view.ELIGIBILITY_LABEL,
            "basis": view.BASIS_LABEL,
        },
        "vehicles": [
            {
                "id": v.vehicle_id,
                "brand": v.brand,
                "model": v.model,
                "body": view.body_label(v, reference),
                "seats": v.seats,
                "doors": v.doors,
                "launch_status": v.launch.status,
                "launch_text": view.launch_text(v),
                "note": v.note,
                "data_issue": v.data_issue,
                "specs": v.specs,
            }
            for v in vehicles
        ],
        "cells": {
            vehicle_id: {cid: _cell(row) for cid, row in cells.items()}
            for vehicle_id, cells in index.items()
        },
        "queue": build_queue(reference, vehicles, resolved),
        "exports": exports,
    }


def _build_exports(
    reference: Reference,
    vehicles: list[Vehicle],
    resolved: list[Resolved],
    as_of: date,
    stale_days: int,
    exports_dir: Path,
) -> list[dict[str, Any]]:
    """สร้างไฟล์ส่งออกด้วยตัวเรนเดอร์ตัวจริง — ไฟล์ในแอปจึงเหมือนที่ build สร้างทุกไบต์"""
    from . import csvx, pdf, xlsx

    renderers = {"xlsx": xlsx.build, "pdf": pdf.build, "csv": csvx.build}
    exports_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for kind in dict.fromkeys(kind for kind, _name, _desc in EXPORTS):
            try:
                renderers[kind](reference, vehicles, resolved,
                                as_of=as_of, stale_days=stale_days, out_dir=tmp_dir)
            except ImportError:
                continue   # ขาด dependency เสริม (weasyprint) — ข้ามเฉพาะไฟล์นั้น

        manifest = []
        for kind, name, description in EXPORTS:
            source = tmp_dir / name
            if not source.exists():
                continue
            entry = {
                "filename": name,
                "kind": kind,
                "description": description,
                "size": source.stat().st_size,
            }
            if source.suffix in EMBEDDED_SUFFIXES:
                entry["data_b64"] = base64.b64encode(source.read_bytes()).decode("ascii")
            else:
                shutil.copyfile(source, exports_dir / name)
                entry["path"] = f"exports/{name}"
            manifest.append(entry)
    return manifest


def build(
    reference: Reference,
    vehicles: list[Vehicle],
    resolved: list[Resolved],
    as_of: date,
    stale_days: int,
    out_dir: Path = OUTPUTS,
) -> list[Path]:
    app_dir = out_dir / "webapp"
    exports_dir = app_dir / "exports"
    if exports_dir.exists():
        shutil.rmtree(exports_dir)   # ไม่ให้ไฟล์เก่าจาก build ก่อนหน้าค้างอยู่

    exports = _build_exports(reference, vehicles, resolved, as_of, stale_days, exports_dir)
    payload = build_payload(reference, vehicles, resolved, as_of, stale_days, exports)

    template = (TEMPLATES / "webapp.html").read_text(encoding="utf-8")
    page = fill_template(template, {"/*__DATA__*/": json_for_script(payload)})

    app_dir.mkdir(parents=True, exist_ok=True)
    index_path = app_dir / "index.html"
    index_path.write_text(page, encoding="utf-8")
    # คืนเฉพาะไฟล์ที่ต้องเผยแพร่คู่กับหน้า (ไฟล์ที่ฝังไว้แล้วไม่ต้อง)
    return [index_path] + [app_dir / e["path"] for e in exports if "path" in e]
