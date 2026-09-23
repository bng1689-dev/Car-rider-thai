"""สร้างหน้าค้นหา (standalone HTML) จากชั้น L4"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .. import view
from ..model import Reference, Resolved, Vehicle
from . import OUTPUTS, TEMPLATES, fill_template, json_for_script


def build(
    reference: Reference,
    vehicles: list[Vehicle],
    resolved: list[Resolved],
    as_of: date,
    stale_days: int,
    out_dir: Path = OUTPUTS,
) -> Path:
    rows = view.build_rows(reference, vehicles, resolved)

    meta = {
        "as_of": as_of.isoformat(),
        "stale_days": stale_days,
        "stale_count": sum(1 for r in resolved if r.is_stale),
        "claim_count": len(resolved),
        "not_surveyed": view.not_surveyed_categories(reference),
        "platforms": [
            {
                "id": p.id,
                "name": p.name,
                "commission_pct": p.commission_pct,
                "note": view.platform_note(reference, p.id),
            }
            for p in reference.platforms
        ],
    }

    template = (TEMPLATES / "search.html").read_text(encoding="utf-8")
    html = fill_template(
        template,
        {
            "/*__DATA__*/": json_for_script(rows),
            "/*__META__*/": json_for_script(meta),
        },
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "search.html"
    path.write_text(html, encoding="utf-8")
    return path
