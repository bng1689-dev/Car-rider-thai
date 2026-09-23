"""กฎการจัดหมวด — ทดสอบตัวประเมิน criteria"""
import unittest

from evbuild.model import Category
from evbuild.rules import FAIL, PASS, derive, evaluate
from tests import make_reference, make_vehicle


def make_category(**overrides) -> Category:
    base = dict(
        id="test.cat", platform="grab", legacy_key="", label="Test", label_th="ทดสอบ",
        order=1, has_official_list=False, coverage_status="surveyed",
        criteria={}, derive_on_pass="none", derive_on_fail="none",
        source_url="https://example.invalid/", as_of="2025-09-15",
    )
    base.update(overrides)
    return Category(**base)


class TestCriteria(unittest.TestCase):
    def test_seats_min(self):
        category = make_category(criteria={"seats_min": 7})
        self.assertEqual(evaluate(make_vehicle(seats=7), category).result, PASS)
        self.assertEqual(evaluate(make_vehicle(seats=5), category).result, FAIL)

    def test_body_type_in(self):
        category = make_category(criteria={"body_type_in": ["suv", "mpv"]})
        self.assertEqual(evaluate(make_vehicle(body_type="suv"), category).result, PASS)
        self.assertEqual(evaluate(make_vehicle(body_type="sedan"), category).result, FAIL)

    def test_body_type_exclude(self):
        category = make_category(criteria={"body_type_exclude": ["pickup"]})
        self.assertEqual(evaluate(make_vehicle(body_type="pickup"), category).result, FAIL)
        self.assertEqual(evaluate(make_vehicle(body_type="sedan"), category).result, PASS)

    def test_unknown_is_not_failure(self):
        """ข้อมูลขาด ≠ ไม่ผ่าน — ความผิดพลาดหลักของสคีมาเดิมคือรวมสองอย่างนี้"""
        category = make_category(criteria={"doors_in": [4, 5]})
        verdict = evaluate(make_vehicle(doors=None), category)
        self.assertEqual(verdict.result, PASS)
        self.assertFalse(verdict.is_certain)
        self.assertIn("doors_in", verdict.unknown)

    def test_known_value_still_fails(self):
        category = make_category(criteria={"doors_in": [4, 5]})
        verdict = evaluate(make_vehicle(doors=2), category)
        self.assertEqual(verdict.result, FAIL)
        self.assertTrue(verdict.is_certain)

    def test_unsupported_criterion_raises(self):
        category = make_category(criteria={"colour_in": ["red"]})
        with self.assertRaises(ValueError):
            evaluate(make_vehicle(), category)


class TestDerive(unittest.TestCase):
    def setUp(self):
        self.reference = make_reference()

    def test_pickup_blocked_for_every_category(self):
        """กฎ 'กระบะทั้งสองแอปไม่รับ' อยู่ใน body_types.yaml ที่เดียว
        เดิมเป็น hardcode กระจายอยู่ใน build.py และ template
        """
        pickup = make_vehicle(body_type="pickup")
        for category in self.reference.categories:
            with self.subTest(category=category.id):
                eligibility, _confidence, _reason = derive(pickup, category, self.reference)
                self.assertEqual(eligibility, "ineligible")

    def test_on_pass_eligible(self):
        category = make_category(derive_on_pass="eligible",
                                 criteria={"body_type_exclude": ["pickup"]})
        result = derive(make_vehicle(), category, self.reference)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "eligible")

    def test_on_pass_none_gives_no_verdict(self):
        """ผ่านเกณฑ์เครื่องไม่พอ — หมวดที่ต้องขึ้นทะเบียนต้องมีข้อกล่าวอ้าง"""
        category = make_category(derive_on_pass="none",
                                 criteria={"body_type_exclude": ["pickup"]})
        self.assertIsNone(derive(make_vehicle(), category, self.reference))

    def test_confidence_drops_when_data_missing(self):
        category = make_category(derive_on_pass="eligible",
                                 criteria={"doors_in": [4, 5]})
        _eligibility, confidence, _reason = derive(
            make_vehicle(doors=None), category, self.reference)
        self.assertEqual(confidence, "medium")
        _eligibility, confidence, _reason = derive(
            make_vehicle(doors=4), category, self.reference)
        self.assertEqual(confidence, "high")


class TestRealRules(unittest.TestCase):
    """กฎจริงใน categories.yaml — 3 คอลัมน์ที่เคยกรอกมือ 351 ช่อง"""

    def setUp(self):
        self.reference = make_reference()

    def test_every_bev_gets_grabcar_and_bolt_basic_green(self):
        vehicle = make_vehicle(body_type="sedan", seats=5, powertrain="bev")
        for category_id in ("grab.car", "bolt.basic", "bolt.green"):
            with self.subTest(category=category_id):
                result = derive(vehicle, self.reference.category_by_id[category_id],
                                self.reference)
                self.assertEqual(result[0], "eligible")

    def test_bolt_green_requires_bev(self):
        petrol = make_vehicle(powertrain="ice")
        result = derive(petrol, self.reference.category_by_id["bolt.green"], self.reference)
        self.assertEqual(result[0], "ineligible")

    def test_sedan_fails_grab_suv(self):
        result = derive(make_vehicle(body_type="sedan"),
                        self.reference.category_by_id["grab.suv"], self.reference)
        self.assertEqual(result[0], "ineligible")

    def test_grab_van_needs_seven_seats(self):
        category = self.reference.category_by_id["grab.van"]
        self.assertEqual(
            derive(make_vehicle(seats=5), category, self.reference)[0], "ineligible")
        # 7 ที่นั่งผ่านเกณฑ์ แต่กฎยังไม่สรุปว่า "ผ่าน" เพราะ on_pass=none
        self.assertIsNone(derive(make_vehicle(seats=7), category, self.reference))


if __name__ == "__main__":
    unittest.main()
