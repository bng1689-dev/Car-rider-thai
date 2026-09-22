"""ด่านความปลอดภัยของการย้ายระบบ

เทียบผลลัพธ์ทั้ง 117 × 10 = 1170 ช่องกับข้อมูลเดิม
ตราบใดที่ ev-project/ev_data.json ยังอยู่ เทสต์ชุดนี้จะคอยยืนยันว่า
สถาปัตยกรรมใหม่ไม่ได้ทำข้อสรุปเดิมหายหรือเพี้ยน
"""
import json
import unittest
from datetime import date

from evbuild.loader import load_all
from evbuild.resolve import resolve_all
from tools.diff_legacy import compare
from tools.migrate_legacy import DERIVABLE_KEYS, LEGACY_PATH, slugify


class TestNoRegression(unittest.TestCase):
    def test_zero_regressions_across_all_cells(self):
        regressions, _intended = compare()
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
        _regressions, intended = compare()
        self.assertTrue(intended, "ควรมีช่องที่ถูกเปิดเผยว่ายังไม่ได้ตรวจ")
        for change in intended:
            self.assertEqual((change["was"], change["now"]),
                             ("ineligible", "unverified"))

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

    def test_claim_count_matches_expected(self):
        _reference, vehicles, claims = load_all()
        self.assertEqual(len(vehicles), 117)
        self.assertEqual(len(claims), 200)

    def test_every_claim_carries_provenance(self):
        """สิ่งที่ข้อมูลเดิมไม่มีเลย: วันที่ตรวจระดับแถว"""
        _reference, _vehicles, claims = load_all()
        undated = [c for c in claims if not c.checked_at]
        self.assertEqual(undated, [])


if __name__ == "__main__":
    unittest.main()
