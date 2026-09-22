"""การตรวจข้อมูล — ต้องจับความผิดที่ระบบเดิมปล่อยผ่านเงียบ ๆ"""
import unittest

from evbuild.validate import Validator, validate_claims, validate_reference, validate_vehicles
from tests import make_claim, make_reference, make_vehicle


def issues_for(fn, *args) -> Validator:
    v = Validator()
    fn(*args, v)
    return v


class TestRealDataIsClean(unittest.TestCase):
    def test_reference_files_have_no_errors(self):
        v = issues_for(validate_reference, make_reference())
        self.assertEqual([str(i) for i in v.errors], [])


class TestVehicleValidation(unittest.TestCase):
    def setUp(self):
        self.reference = make_reference()

    def _errors(self, vehicles):
        return issues_for(validate_vehicles, self.reference, vehicles).errors

    def test_duplicate_vehicle_id(self):
        errors = self._errors([make_vehicle(), make_vehicle()])
        self.assertTrue(any("ซ้ำ" in e.message for e in errors))

    def test_unknown_body_type(self):
        errors = self._errors([make_vehicle(body_type="spaceship")])
        self.assertTrue(any("body_types.yaml" in e.message for e in errors))

    def test_bad_seats(self):
        self.assertTrue(self._errors([make_vehicle(seats=0)]))
        self.assertTrue(self._errors([make_vehicle(seats="five")]))

    def test_bad_doors(self):
        self.assertTrue(self._errors([make_vehicle(doors=7)]))
        self.assertEqual(self._errors([make_vehicle(doors=None)]), [])

    def test_announced_requires_year(self):
        from evbuild.model import Launch
        errors = self._errors([make_vehicle(launch=Launch(status="announced"))])
        self.assertTrue(any("year" in e.message for e in errors))


class TestClaimValidation(unittest.TestCase):
    def setUp(self):
        self.reference = make_reference()
        self.vehicles = [make_vehicle()]

    def _errors(self, claims):
        return issues_for(validate_claims, self.reference, self.vehicles, claims).errors

    def test_typo_in_enum_is_caught(self):
        """ระบบเดิม: พิมพ์ 'yy' แทน 'y' แล้วผ่านไปได้ ให้ผลผิดคนละแบบใน 3 output"""
        errors = self._errors([make_claim(eligibility="eligibl")])
        self.assertTrue(any("eligibility" in e.message for e in errors))

    def test_unknown_basis(self):
        self.assertTrue(self._errors([make_claim(basis="ได้ยินมา")]))

    def test_dangling_vehicle_reference(self):
        errors = self._errors([make_claim(vehicle_id="ไม่มีรถคันนี้")])
        self.assertTrue(any("vehicles.jsonl" in e.message for e in errors))

    def test_dangling_category_reference(self):
        errors = self._errors([make_claim(category_id="grab.helicopter")])
        self.assertTrue(any("categories.yaml" in e.message for e in errors))

    def test_official_list_requires_provenance(self):
        """กฎที่เปลี่ยน 'ควรบันทึกที่มานะ' ให้เป็นสิ่งที่ระบบบังคับ"""
        errors = self._errors([make_claim(source_url="")])
        self.assertTrue(any("source_url" in e.message for e in errors))
        errors = self._errors([make_claim(checked_at="")])
        self.assertTrue(any("checked_at" in e.message for e in errors))

    def test_bad_date_format(self):
        errors = self._errors([make_claim(checked_at="15/09/2025")])
        self.assertTrue(any("YYYY-MM-DD" in e.message for e in errors))

    def test_tier_must_belong_to_category(self):
        errors = self._errors([make_claim(category_id="grab.exec", tier="xxl")])
        self.assertTrue(any("tier" in e.message for e in errors))

    def test_tier_rejected_on_category_without_tiers(self):
        errors = self._errors([make_claim(category_id="grab.premium", tier="lite")])
        self.assertTrue(any("tiers" in e.message for e in errors))

    def test_valid_tier_passes(self):
        self.assertEqual(self._errors([make_claim(category_id="grab.exec", tier="m")]), [])


class TestCrossLayerLogic(unittest.TestCase):
    def test_premium_without_base_category_is_an_error(self):
        from datetime import date

        from evbuild.resolve import resolve_all
        from evbuild.validate import validate_logic

        reference = make_reference()
        pickup = make_vehicle(vehicle_id="rd6", body_type="pickup")
        # อ้างว่าผ่าน Premium ทั้งที่เป็นกระบะ = ขัดกับ GrabCar ที่ไม่ผ่าน
        claims = [make_claim(vehicle_id="rd6", category_id="grab.premium")]
        resolved = resolve_all(reference, [pickup], claims, as_of=date(2025, 9, 15))
        v = Validator()
        validate_logic(reference, [pickup], resolved, v)
        self.assertTrue(any("ขัดกันเอง" in e.message for e in v.errors))


if __name__ == "__main__":
    unittest.main()
