"""สร้างเอกสารวิเคราะห์ PDF จากชั้น L4

ต่างจากระบบเดิมสองอย่าง
  1. ทุกค่าที่ต่อเข้า HTML ผ่าน html_escape() (เดิมใช้ %-format ตรง ๆ)
  2. เพิ่มหัวข้อ "ที่มาและความสดของข้อมูล" — เอกสารที่ใช้ประกอบการตัดสินใจ
     ต้องบอกได้ว่าข้อมูลแต่ละส่วนมาจากไหนและตรวจครั้งสุดท้ายเมื่อไร
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

from .. import view
from ..model import Reference, Resolved, Vehicle
from . import OUTPUTS, TEMPLATES, fill_template, html_escape

STYLE = """<style>
.evtable{font-size:8.5pt;} .evtable td{padding:4px 6px;}
.evtable .mdl{font-weight:700;color:#16244d;}
.evtable .gc{font-size:8pt;} .evtable .bc{font-size:8pt;color:#7a6a2e;}
.brandrow td{background:#16244d !important;color:#fff;font-weight:700;font-size:9.5pt;padding:5px 8px;}
.stg{font-size:7.5pt;padding:1px 6px;border-radius:8px;font-weight:700;}
.st-sale{background:#e0f5e9;color:#00803a;} .st-announced{background:#fdf2d9;color:#a67a00;}
.st-expected{background:#fde8d9;color:#c0560a;} .pk{color:#c0392b;font-size:8pt;}
.unv{color:#c0392b;} .prov{font-size:8.5pt;}
.prov td{padding:4px 6px;} .prov .n{text-align:right;font-variant-numeric:tabular-nums;}
</style>"""


def _category_text(entries: list[dict]) -> str:
    if not entries:
        return "—"
    parts = []
    for entry in entries:
        label = html_escape(entry["label"])
        if entry["eligibility"] == "unverified":
            parts.append(f'<span class="unv">{label}?</span>')
        else:
            parts.append(label)
    return ", ".join(parts)


def _ev_table(rows: list[dict]) -> str:
    body = ""
    current_brand = None
    for row in rows:
        if row["brand"] != current_brand:
            current_brand = row["brand"]
            body += f'<tr class="brandrow"><td colspan="6">{html_escape(current_brand)}</td></tr>'
        blocked = all(not row[p] for p in ("grab", "bolt"))
        grab_text = ('<span class="pk">ไม่เข้าเกณฑ์ทั้งสองแอป</span>' if blocked
                     else _category_text(row["grab"]))
        bolt_text = "—" if blocked else _category_text(row["bolt"])
        body += (
            f'<tr><td class="mdl">{html_escape(row["model"])}</td>'
            f'<td class="c">{html_escape(row["body"])}</td>'
            f'<td class="c">{html_escape(row["seats"])}</td>'
            f'<td class="c"><span class="stg st-{html_escape(row["launch_status"])}">'
            f'{html_escape(row["launch_short"])}</span></td>'
            f'<td class="gc">{grab_text}</td><td class="bc">{bolt_text}</td></tr>'
        )
    return body


def _provenance_section(
    reference: Reference, vehicles: list[Vehicle], resolved: list[Resolved],
    as_of: date, stale_days: int,
) -> str:
    basis_counts = Counter(r.basis for r in resolved)
    total = len(resolved)
    rows = ""
    for basis, label in view.BASIS_LABEL.items():
        n = basis_counts.get(basis, 0)
        if not n:
            continue
        pct = 100 * n / total if total else 0
        rows += (f'<tr><td>{html_escape(label)}</td>'
                 f'<td class="n">{n:,}</td><td class="n">{pct:.1f}%</td></tr>')
    unverified = sum(1 for r in resolved if r.eligibility == "unverified")
    if unverified:
        rows += (f'<tr><td>ยังไม่ได้ตรวจ</td><td class="n">{unverified:,}</td>'
                 f'<td class="n">{100 * unverified / total:.1f}%</td></tr>')

    stale_count = sum(1 for r in resolved if r.is_stale)
    # ถ้อยคำมาจากข้อมูลจริง ไม่ใช่จากธง coverage_status — ตัวช่วยเดียวกับที่
    # รายงาน coverage และชีต "งานค้าง" ใช้ จึงนับไม่ตรงกันไม่ได้
    not_surveyed = "".join(
        f"<li>{html_escape(view.survey_gap_summary(gap))}</li>"
        for gap in view.survey_gaps(reference, vehicles, resolved)
    )

    conflicts = [r for r in resolved if r.rule_conflict]
    conflict_html = ""
    if conflicts:
        items = "".join(
            f"<li>{html_escape(r.brand)} {html_escape(r.model)} × "
            f"{html_escape(r.category_label)} — {html_escape(r.rule_conflict)}</li>"
            for r in conflicts
        )
        conflict_html = (
            f"<p><strong>กฎขัดกับข้อกล่าวอ้าง {len(conflicts)} จุด</strong> "
            f"(ข้อกล่าวอ้างชนะตามลำดับความสำคัญ แต่บันทึกไว้เพราะกฎที่ขัดกับ"
            f"ความจริงคือกฎที่ต้องแก้)</p><ul>{items}</ul>"
        )

    return f"""
<div class="pagebreak"></div>
<h2><span class="num">8</span>ที่มาและความสดของข้อมูล</h2>
<p>ข้อสรุปทั้งหมด <strong>{total:,} แถว</strong> (รถ {len(vehicles)} รุ่น ×
หมวด {len(reference.categories)} หมวด) · ข้อมูล ณ {html_escape(as_of.isoformat())}
· เพดานความสด {stale_days} วัน · เกินเพดาน <strong>{stale_count:,} แถว</strong></p>
<table class="data prov"><thead><tr>
<th style="width:52%">ที่มาของข้อสรุป</th><th class="c" style="width:24%">จำนวนแถว</th>
<th class="c" style="width:24%">สัดส่วน</th></tr></thead><tbody>{rows}</tbody></table>
{f'<p><strong>หมวดที่ประกาศว่ายังไม่ได้สำรวจ</strong></p><ul>{not_surveyed}</ul>' if not_surveyed else ''}
{conflict_html}
<div class="note-box"><strong>วิธีอ่าน:</strong> ข้อสรุปที่มาจาก "คำนวณจากกฎ"
ไม่ได้อ่อนกว่าข้อสรุปที่มาจากรายการทางการ — เป็นคนละชนิดของหลักฐาน
กฎบอกว่ารถ "เข้าเกณฑ์" · รายการทางการบอกว่าแพลตฟอร์ม "รับจริง"
เครื่องหมาย <strong>?</strong> ในตารางหมายถึงยังไม่ได้ตรวจ ไม่ใช่ไม่ผ่าน</div>
"""


def build(
    reference: Reference,
    vehicles: list[Vehicle],
    resolved: list[Resolved],
    as_of: date,
    stale_days: int,
    out_dir: Path = OUTPUTS,
) -> Path:
    from weasyprint import HTML

    rows = view.build_rows(reference, vehicles, resolved)
    unverified = sum(1 for r in resolved if r.eligibility == "unverified")

    ev_section = STYLE + f"""
<div class="pagebreak"></div>
<h2><span class="num">7</span>ตารางรถ EV (BEV) ในไทย × หมวดบริการ</h2>
<p>รวมรถยนต์ไฟฟ้าล้วน (BEV) ที่จำหน่ายและเตรียมเปิดตัวในไทย
<strong>{len(rows)} รุ่น</strong> · เครื่องหมาย <strong>?</strong> =
ยังไม่ได้ตรวจกับรายการทางการ (ไม่ใช่ "ไม่ผ่าน") รวม {unverified} ช่อง</p>
<table class="data evtable"><thead><tr>
<th style="width:22%">รุ่น</th><th class="c" style="width:16%">ตัวถัง</th>
<th class="c" style="width:7%">ที่นั่ง</th><th class="c" style="width:13%">สถานะ</th>
<th style="width:21%">หมวด Grab</th><th style="width:21%">หมวด Bolt ⟡</th>
</tr></thead><tbody>{_ev_table(rows)}</tbody></table>
<div class="note-box"><strong>สรุปจากตาราง:</strong>
BEV ทุกรุ่นยกเว้นรถกระบะไฟฟ้า ผ่าน GrabCar + Bolt Basic/Green โดยอัตโนมัติ —
ข้อสรุปนี้มาจากกฎที่เขียนไว้ใน categories.yaml ไม่ใช่การกรอกมือทีละช่อง ·
{html_escape(view.platform_note(reference, "bolt"))}</div>
""" + _provenance_section(reference, vehicles, resolved, as_of, stale_days)

    template = (TEMPLATES / "analysis_body.html").read_text(encoding="utf-8")
    html = fill_template(template, {"<!--EV_SECTION-->": ev_section})

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "analysis.pdf"
    HTML(string=html).write_pdf(path)
    return path
