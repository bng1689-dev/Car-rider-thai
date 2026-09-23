"""ด่านความปลอดภัยของการย้ายระบบ

เทียบผลลัพธ์ทั้ง 117 × 10 = 1170 ช่องกับข้อมูลเดิม
ตราบใดที่ ev-project/ev_data.json ยังอยู่ เทสต์ชุดนี้จะคอยยืนยันว่า
สถาปัตยกรรมใหม่ไม่ได้ทำข้อสรุปเดิมหายหรือเพี้ยน
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

from evbuild.loader import load_all, load_reference, write_jsonl
from evbuild.resolve import resolve_all
from tests import make_claim
from tools import migrate_legacy
from tools.diff_legacy import compare
from tools.migrate_legacy import (
    DERIVABLE_KEYS, LEGACY_CHECKED_AT, LEGACY_PATH, migrate, rows_not_reproduced, slugify,
)


class TestNoRegression(unittest.TestCase):
    def test_zero_regressions_across_all_cells(self):
        regressions, _intended, _updated = compare()
        self.assertEqual(
            regressions, [],
            "ผลลัพธ์เพี้ยนจากข้อมูลเดิม:\n" + "\n".join(
                f"  {r['vehicle']} × {r['category']}: {r['was']} → {r['now']}"
                for r in regressions[:20]
            ),
        )

    def test_intended_changes_are_only_unknown_surfacing(self):
        """การเปลี่ยนแปลงที่ยอมรับได้มีแบบเดียว:
        เดิมแสดง '-' (ดูเหมือนไม่ผ่าน) ทั้งที่ความจริงคือยังไม่เคยตรวจ
        """
        _regressions, intended, _updated = compare()
        self.assertTrue(intended, "ควรมีช่องที่ถูกเปิดเผยว่ายังไม่ได้ตรวจ")
        for change in intended:
            self.assertEqual((change["was"], change["now"]),
                             ("ineligible", "unverified"))

    def _compare_with(self, extra_claim):
        reference, vehicles, claims = load_all()
        with patch("tools.diff_legacy.load_all",
                   return_value=(reference, vehicles, claims + [extra_claim])):
            return compare()

    def test_later_verification_is_an_update_not_a_regression(self):
        """ผลตรวจหลังย้ายระบบเปลี่ยนช่อง "รอตรวจ" เดิมเป็น "ผ่าน" ได้ — ต้องไม่ทำให้ CI ล้ม"""
        legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
        entry = next(e for e in legacy if e["gsuv"] == "p")
        verified = make_claim(vehicle_id=slugify(entry["brand"], entry["model"]),
                              category_id="grab.suv", checked_at="2026-09-23")

        regressions, _intended, updated = self._compare_with(verified)
        self.assertEqual(regressions, [])
        self.assertIn(
            (f"{entry['brand']} {entry['model']}", "grab.suv", "unverified", "eligible"),
            [(u["vehicle"], u["category"], u["was"], u["now"]) for u in updated])

    def test_claim_not_newer_than_legacy_still_counts_as_regression(self):
        """ด่านไม่หลวมลง: ข้อกล่าวอ้างที่ไม่ได้ใหม่กว่าข้อมูลเดิมแต่เปลี่ยนความหมาย = ถดถอย"""
        legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
        entry = next(e for e in legacy if e["bcomf"] == "i")
        contradicting = make_claim(vehicle_id=slugify(entry["brand"], entry["model"]),
                                   category_id="bolt.comfort", eligibility="ineligible",
                                   checked_at=LEGACY_CHECKED_AT)

        regressions, _intended, updated = self._compare_with(contradicting)
        self.assertEqual([(r["category"], r["was"], r["now"]) for r in regressions],
                         [("bolt.comfort", "eligible", "ineligible")])
        self.assertNotIn(("bolt.comfort", f"{entry['brand']} {entry['model']}"),
                         [(u["category"], u["vehicle"]) for u in updated])

    def test_every_legacy_confirmation_survives(self):
        """ธง y และ i เดิมทุกช่อง ต้องยังเป็น eligible ในระบบใหม่"""
        reference, vehicles, claims = load_all()
        resolved = resolve_all(reference, vehicles, claims, as_of=date(2025, 9, 15))
        index = {(r.vehicle_id, r.category_id): r for r in resolved}
        legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))

        checked = 0
        for entry in legacy:
            vehicle_id = slugify(entry["brand"], entry["model"])
            for category in reference.categories:
                if not category.legacy_key:
                    continue
                if entry.get(category.legacy_key) not in ("y", "i"):
                    continue
                checked += 1
                row = index.get((vehicle_id, category.id))
                self.assertIsNotNone(
                    row, f"{entry['brand']} {entry['model']} × {category.id} หายไป")
                self.assertEqual(
                    row.eligibility, "eligible",
                    f"{entry['brand']} {entry['model']} × {category.id}")
        # 348 ช่องที่กฎคำนวณเอง (gcar/bbasic/bgreen อย่างละ 116)
        # + 161 ช่องที่มาจากข้อกล่าวอ้าง (gprem 12 · gsuv 15 · gexec 6 · bcomf 90 · bxl 38)
        self.assertEqual(checked, 509)


class TestDerivableColumnsAreGone(unittest.TestCase):
    """3 คอลัมน์ที่พิสูจน์แล้วว่าคำนวณได้ 100% ต้องไม่อยู่ในข้อมูลดิบอีก"""

    def test_no_claims_for_derivable_categories(self):
        reference, _vehicles, claims = load_all()
        derivable_ids = {
            c.id for c in reference.categories if c.legacy_key in DERIVABLE_KEYS
        }
        offenders = [c for c in claims if c.category_id in derivable_ids]
        self.assertEqual(
            offenders, [],
            "หมวดเหล่านี้ต้องมาจากกฎ ไม่ใช่ข้อมูลกรอกมือ: "
            + ", ".join(sorted(derivable_ids)),
        )

    def test_those_categories_still_resolve_for_every_vehicle(self):
        reference, vehicles, claims = load_all()
        resolved = resolve_all(reference, vehicles, claims, as_of=date(2025, 9, 15))
        for legacy_key in DERIVABLE_KEYS:
            category = reference.category_by_legacy_key[legacy_key]
            rows = [r for r in resolved if r.category_id == category.id]
            self.assertEqual(len(rows), len(vehicles))
            self.assertTrue(all(r.basis == "rule_derived" for r in rows))

    def test_migration_output_counts(self):
        legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
        vehicles, claims, _notices = migrate(legacy, load_reference())
        self.assertEqual(len(vehicles), 117)
        self.assertEqual(len(claims), 200)

    def test_every_legacy_vehicle_is_still_present(self):
        """รุ่นที่เพิ่มหลังย้ายระบบมี added_at ใหม่กว่า — แยกออกจากกันได้เสมอ"""
        _reference, vehicles, _claims = load_all()
        legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
        from_legacy = {v.vehicle_id for v in vehicles if v.added_at == LEGACY_CHECKED_AT}
        self.assertEqual(from_legacy, {slugify(e["brand"], e["model"]) for e in legacy})

    def test_every_claim_carries_provenance(self):
        """สิ่งที่ข้อมูลเดิมไม่มีเลย: วันที่ตรวจระดับแถว"""
        _reference, _vehicles, claims = load_all()
        undated = [c for c in claims if not c.checked_at]
        self.assertEqual(undated, [])


class TestRerunningMigrationKeepsLaterWork(unittest.TestCase):
    """รัน migrate_legacy ซ้ำต้องไม่ลบรถที่เพิ่มหรือผลตรวจที่นำเข้าหลังย้ายระบบ"""

    def setUp(self):
        reference = load_reference()
        legacy = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
        self.vehicles, self.claims, _notices = migrate(legacy, reference)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vehicles_path = Path(self.tmp.name) / "vehicles.jsonl"
        self.claims_path = Path(self.tmp.name) / "eligibility.jsonl"
        write_jsonl(self.claims_path, self.claims)

    def _run(self) -> int:
        with patch.object(migrate_legacy, "VEHICLES_PATH", self.vehicles_path), \
                patch.object(migrate_legacy, "ELIGIBILITY_PATH", self.claims_path), \
                patch.object(sys, "argv", ["migrate_legacy.py"]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return migrate_legacy.main()

    def test_legacy_rows_alone_are_reproduced(self):
        write_jsonl(self.vehicles_path, self.vehicles)
        self.assertEqual(rows_not_reproduced(self.vehicles_path, self.vehicles), [])
        self.assertEqual(rows_not_reproduced(self.claims_path, self.claims), [])

    def test_refuses_to_overwrite_a_vehicle_added_later(self):
        newcomer = dict(self.vehicles[0], vehicle_id="later-model", added_at="2026-09-23")
        write_jsonl(self.vehicles_path, self.vehicles + [newcomer])
        before = self.vehicles_path.read_bytes()

        self.assertEqual(rows_not_reproduced(self.vehicles_path, self.vehicles), [newcomer])
        self.assertEqual(self._run(), 1)
        self.assertEqual(self.vehicles_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
