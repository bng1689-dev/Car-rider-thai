"""การตัดสินผลสุดท้าย — ลำดับความสำคัญ ความครบถ้วน และความสด"""
import unittest
from datetime import date

from evbuild.resolve import PRECEDENCE, resolve_all, resolve_cell
from tests import make_claim, make_reference, make_vehicle


class TestPrecedence(unittest.TestCase):
    def setUp(self):
        self.reference = make_reference()
        self.vehicle = make_vehicle(body_type="suv")

    def test_order_is_strict(self):
        order = ["official_list", "manual", "spec_inference", "rule_derived", "coverage_sweep"]
        values = [PRECEDENCE[b] for b in order]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_official_list_beats_inference(self):
        category = self.reference.category_by_id["grab.premium"]
        claims = [
            make_claim(category_id="grab.premium", eligibility="ineligible",
                       basis="official_list"),
            make_claim(category_id="grab.premium", eligibility="eligible",
                       basis="spec_inference"),
        ]
        eligibility, basis, *_ = resolve_cell(self.vehicle, category, claims, self.reference)
        self.assertEqual((eligibility, basis), ("ineligible", "official_list"))

    def test_claim_beats_rule(self):
        """ข้อเท็จจริงจากรายการทางการชนะกฎที่เราอนุมานเอง"""
        category = self.reference.category_by_id["grab.suv"]
        sedan = make_vehicle(body_type="sedan")   # กฎจะบอกว่า ineligible
        claims = [make_claim(category_id="grab.suv", basis="official_list")]
        eligibility, basis, *_ = resolve_cell(sedan, category, claims, self.reference)
        self.assertEqual((eligibility, basis), ("eligible", "official_list"))

    def test_same_basis_newest_wins(self):
        category = self.reference.category_by_id["grab.premium"]
        claims = [
            make_claim(eligibility="ineligible", checked_at="2024-01-01"),
            make_claim(eligibility="eligible", checked_at="2025-09-15"),
        ]
        eligibility, *_ = resolve_cell(self.vehicle, category, claims, self.reference)
        self.assertEqual(eligibility, "eligible")


class TestCoverageStatus(unittest.TestCase):
    """หัวใจของการแยก 'ไม่ผ่าน' ออกจาก 'ไม่เคยตรวจ'"""

    def setUp(self):
        self.reference = make_reference()
        self.vehicle = make_vehicle(body_type="suv")

    def test_surveyed_absence_means_ineligible(self):
        category = self.reference.category_by_id["grab.premium"]
        eligibility, basis, *_ = resolve_cell(self.vehicle, category, [], self.reference)
        self.assertEqual((eligibility, basis), ("ineligible", "coverage_sweep"))

    def test_partial_absence_means_unverified(self):
        category = self.reference.category_by_id["grab.suv"]
        eligibility, basis, *_ = resolve_cell(self.vehicle, category, [], self.reference)
        self.assertEqual(eligibility, "unverified")
        self.assertIsNone(basis)

    def test_not_surveyed_produces_no_row(self):
        """ไม่สร้างแถวเลย — ไม่สาดเครื่องหมาย '?' ลงรถทุกคัน
        รายงานที่ระดับหมวดแทน (ดู report coverage)
        """
        category = self.reference.category_by_id["grab.van"]
        seven_seater = make_vehicle(body_type="mpv", seats=7)
        self.assertIsNone(resolve_cell(seven_seater, category, [], self.reference))

    def test_not_surveyed_still_rules_out_failures(self):
        """แม้หมวดยังไม่ได้สำรวจ กฎก็ยังตัดรถที่ตกเกณฑ์ชัด ๆ ออกได้"""
        category = self.reference.category_by_id["grab.van"]
        result = resolve_cell(make_vehicle(seats=5), category, [], self.reference)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ineligible")


class TestConflictAndStaleness(unittest.TestCase):
    def setUp(self):
        self.reference = make_reference()

    def test_conflict_recorded_not_hidden(self):
        sedan = make_vehicle(vehicle_id="mg-ep", body_type="sedan")
        claims = [make_claim(vehicle_id="mg-ep", category_id="grab.suv",
                             basis="official_list")]
        resolved = resolve_all(self.reference, [sedan], claims, as_of=date(2025, 9, 15))
        row = next(r for r in resolved if r.category_id == "grab.suv")
        self.assertEqual(row.eligibility, "eligible")       # ข้อกล่าวอ้างชนะ
        self.assertIn("ineligible", row.rule_conflict)      # แต่บันทึกความขัดแย้งไว้

    def test_unverified_claim_is_not_a_conflict(self):
        suv = make_vehicle(vehicle_id="x", body_type="suv")
        claims = [make_claim(vehicle_id="x", category_id="grab.suv",
                             eligibility="unverified", basis="manual",
                             source_url="", checked_at="")]
        resolved = resolve_all(self.reference, [suv], claims, as_of=date(2025, 9, 15))
        row = next(r for r in resolved if r.category_id == "grab.suv")
        self.assertEqual(row.rule_conflict, "")

    def test_staleness_measured_per_row(self):
        vehicle = make_vehicle(vehicle_id="x", body_type="suv")
        claims = [make_claim(vehicle_id="x", category_id="grab.premium",
                             checked_at="2025-01-01")]
        resolved = resolve_all(self.reference, [vehicle], claims,
                               as_of=date(2025, 9, 15), stale_days=90)
        row = next(r for r in resolved if r.category_id == "grab.premium")
        self.assertEqual(row.staleness_days, 257)
        self.assertTrue(row.is_stale)

    def test_fresh_claim_is_not_stale(self):
        vehicle = make_vehicle(vehicle_id="x", body_type="suv")
        claims = [make_claim(vehicle_id="x", category_id="grab.premium",
                             checked_at="2025-09-01")]
        resolved = resolve_all(self.reference, [vehicle], claims,
                               as_of=date(2025, 9, 15), stale_days=90)
        row = next(r for r in resolved if r.category_id == "grab.premium")
        self.assertFalse(row.is_stale)

    def test_pickup_gets_no_eligible_row_anywhere(self):
        pickup = make_vehicle(vehicle_id="rd6", body_type="pickup")
        resolved = resolve_all(self.reference, [pickup], [], as_of=date(2025, 9, 15))
        self.assertTrue(all(r.eligibility == "ineligible" for r in resolved))


if __name__ == "__main__":
    unittest.main()
