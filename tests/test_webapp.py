"""เว็บแอป — ข้อมูลที่ฝัง · ความปลอดภัย · สัญญาของแพลตฟอร์ม · การนำผลตรวจกลับเข้าระบบ"""
import json
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

from evbuild.loader import ELIGIBILITY_PATH, load_all, read_jsonl
from evbuild.render import webapp
from evbuild.resolve import resolve_all
from tests import make_claim, make_reference, make_vehicle
from tools import import_verifications as imp

AS_OF = date(2025, 9, 15)
HOSTILE = '</script><img src=x onerror=alert(1)>"\'&'


def data_block(page: str) -> dict:
    return json.loads(re.search(r'id="ev-data">(.*?)</script>', page, re.S).group(1))


class TestPayloadFromRealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference, cls.vehicles, claims = load_all()
        cls.resolved = resolve_all(cls.reference, cls.vehicles, claims, as_of=AS_OF)
        cls.payload = webapp.build_payload(cls.reference, cls.vehicles, cls.resolved,
                                           AS_OF, 90, exports=[])

    def test_every_conclusion_reaches_the_app(self):
        cells = sum(len(v) for v in self.payload["cells"].values())
        self.assertEqual(cells, len(self.resolved))
        self.assertEqual(len(self.payload["vehicles"]), len(self.vehicles))

    def test_queue_is_computed_in_python_not_in_the_page(self):
        groups = {g["key"]: g for g in self.payload["queue"]}
        self.assertEqual(len(groups["unverified:grab.suv"]["items"]), 64)
        self.assertEqual(len(groups["not_surveyed:grab.van"]["items"]), 14)
        self.assertEqual(len(groups["conflict"]["items"]), 2)
        self.assertEqual(len(groups["data_issue"]["items"]), 2)

    def test_loose_category_is_not_exploded_into_items(self):
        """Bolt Premium: แทบทุกรุ่นผ่านเกณฑ์เครื่อง — แตกเป็นงานรายคันก็ไม่ได้บอกอะไร"""
        premium = next(g for g in self.payload["queue"] if g["key"] == "not_surveyed:bolt.premium")
        self.assertTrue(premium["loose"])
        self.assertEqual(premium["items"], [])
        self.assertGreater(premium["candidate_count"], 100)

    def test_queue_follows_platform_order(self):
        """ลำดับตาม platforms.yaml (Grab ก่อน Bolt) ไม่ใช่ตามตัวอักษร"""
        keys = [g["key"] for g in self.payload["queue"] if g["kind"] == "not_surveyed"]
        self.assertLess(keys.index("not_surveyed:grab.van"), keys.index("not_surveyed:bolt.premium"))

    def test_claimed_vehicles_are_not_listed_as_untouched(self):
        for group in self.payload["queue"]:
            if group["kind"] != "not_surveyed":
                continue
            with self.subTest(group=group["key"]):
                for vid in group["items"]:
                    self.assertNotIn(group["category_id"], self.payload["cells"].get(vid, {}))

    def test_vehicle_ids_are_valid_db_path_segments(self):
        """ผลตรวจเก็บที่ verifications/<vehicle_id>:<category_id> — ต้องผ่านไวยากรณ์ path ของ db"""
        segment = re.compile(r"^[A-Za-z0-9_\-.~:@+]{1,200}$")
        for vehicle in self.payload["vehicles"]:
            for category in self.payload["categories"]:
                doc_id = f'{vehicle["id"]}:{category["id"]}'
                self.assertRegex(doc_id, segment)

    def test_labels_come_from_the_single_python_source(self):
        from evbuild import view
        self.assertEqual(self.payload["labels"]["basis"], view.BASIS_LABEL)
        self.assertEqual(self.payload["labels"]["eligibility"], view.ELIGIBILITY_LABEL)


class TestPageContract(unittest.TestCase):
    """template ต้องเป็นเนื้อหา body ล้วน — แพลตฟอร์มห่อโครงหน้าให้เองตอนเผยแพร่"""

    @classmethod
    def setUpClass(cls):
        cls.template = (webapp.TEMPLATES / "webapp.html").read_text(encoding="utf-8")

    def test_no_document_skeleton(self):
        for tag in ("<!doctype", "<html", "<head>", "<body"):
            self.assertNotIn(tag, self.template.lower())

    def test_title_within_first_8kb(self):
        self.assertRegex(self.template[:8192], r"<title>[^<]+</title>")

    def test_only_allowed_external_hosts(self):
        hosts = set(re.findall(r'(?:src|href)="https://([^/"]+)', self.template))
        self.assertLessEqual(hosts, {"fonts.googleapis.com", "fonts.gstatic.com"})

    def test_no_blocked_dialogs_or_download_links(self):
        """alert/confirm/prompt และ <a download> ไม่ทำงานในกรอบของแพลตฟอร์ม"""
        script = self.template.split("<script>", 1)[1]
        for call in ("alert(", "confirm(", "prompt(", "window.print"):
            self.assertNotIn(call, script)
        self.assertNotIn(" download", self.template.split("<script", 1)[0])

    def test_dark_tokens_defined_for_both_theme_paths(self):
        self.assertIn('@media (prefers-color-scheme: dark)', self.template)
        self.assertIn(':root:not([data-theme="light"])', self.template)
        self.assertIn(':root[data-theme="dark"]', self.template)


class TestBuildOutput(unittest.TestCase):
    def test_hostile_text_cannot_escape_the_data_block(self):
        reference = make_reference()
        vehicle = make_vehicle(vehicle_id="evil", model=HOSTILE, body_type="suv")
        claims = [make_claim(vehicle_id="evil", category_id="grab.premium", note=HOSTILE)]
        resolved = resolve_all(reference, [vehicle], claims, as_of=AS_OF)
        with tempfile.TemporaryDirectory() as tmp:
            paths = webapp.build(reference, [vehicle], resolved, as_of=AS_OF,
                                 stale_days=90, out_dir=Path(tmp))
            page = paths[0].read_text(encoding="utf-8")
            exported = [p.name for p in paths[1:]]

        self.assertEqual(page.count("</script>"), 2)      # บล็อกข้อมูล + สคริปต์ของหน้า
        block = re.search(r'id="ev-data">(.*?)</script>', page, re.S).group(1)
        self.assertNotIn("<", block)
        self.assertEqual(data_block(page)["vehicles"][0]["model"], HOSTILE)
        self.assertIn("i2-links.csv", exported)

    def test_export_manifest_matches_files_on_disk(self):
        reference = make_reference()
        vehicle = make_vehicle(vehicle_id="x", body_type="suv")
        resolved = resolve_all(reference, [vehicle], [], as_of=AS_OF)
        with tempfile.TemporaryDirectory() as tmp:
            paths = webapp.build(reference, [vehicle], resolved, as_of=AS_OF,
                                 stale_days=90, out_dir=Path(tmp))
            manifest = data_block(paths[0].read_text(encoding="utf-8"))["exports"]
            app_dir = Path(tmp) / "webapp"
            published = {p.resolve() for p in paths[1:]}
            for entry in manifest:
                with self.subTest(file=entry["filename"]):
                    if "data_b64" in entry:
                        # ฝังในหน้า — ต้องถอดกลับได้ครบทุกไบต์ และไม่อยู่ในรายการไฟล์ประกอบ
                        import base64
                        self.assertEqual(len(base64.b64decode(entry["data_b64"])), entry["size"])
                        self.assertNotIn("path", entry)
                    else:
                        on_disk = app_dir / entry["path"]
                        self.assertTrue(on_disk.exists())
                        self.assertEqual(on_disk.stat().st_size, entry["size"])
                        self.assertIn(on_disk.resolve(), published)

    def test_office_documents_are_embedded_not_published(self):
        """แพลตฟอร์มไม่เสิร์ฟ .xlsx เป็นไฟล์ประกอบ — ต้องฝังในหน้าแทน"""
        reference = make_reference()
        vehicle = make_vehicle(vehicle_id="x", body_type="suv")
        resolved = resolve_all(reference, [vehicle], [], as_of=AS_OF)
        with tempfile.TemporaryDirectory() as tmp:
            paths = webapp.build(reference, [vehicle], resolved, as_of=AS_OF,
                                 stale_days=90, out_dir=Path(tmp))
            manifest = data_block(paths[0].read_text(encoding="utf-8"))["exports"]
        xlsx = next(e for e in manifest if e["filename"].endswith(".xlsx"))
        self.assertIn("data_b64", xlsx)
        self.assertFalse(any(p.suffix == ".xlsx" for p in paths[1:]))


class TestImportVerifications(unittest.TestCase):
    """ผลตรวจจากแอปต้องกลับเข้าระบบได้ โดยผ่านกติกาเดียวกับ evbuild validate"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.target = self.dir / "eligibility.jsonl"
        self.target.write_text(ELIGIBILITY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        self.before = self.target.read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _import(self, rows, dry_run=False, name="in.json"):
        path = self.dir / name
        if name.endswith(".json"):
            path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        else:
            path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                            encoding="utf-8")
        return imp.run(path, dry_run=dry_run, eligibility_path=self.target)

    def _rows(self):
        return [rec for _n, rec in read_jsonl(self.target)]

    @staticmethod
    def _verified(**overrides):
        row = {"vehicle_id": "tesla-model-y", "category_id": "grab.suv",
               "eligibility": "eligible", "basis": "official_list", "confidence": "high",
               "source_url": "https://grabdriverth.com/", "checked_at": "2026-09-23",
               "checked_by": "james", "note": ""}
        row.update(overrides)
        return row

    def test_new_cell_is_added(self):
        self.assertEqual(self._import([self._verified()]), 0)
        rows = [r for r in self._rows()
                if (r["vehicle_id"], r["category_id"]) == ("tesla-model-y", "grab.suv")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["eligibility"], "eligible")

    def test_existing_cell_is_replaced_in_place(self):
        """BYD Atto 2 × Grab SUV มีข้อกล่าวอ้าง unverified อยู่แล้ว — ต้องถูกแทน ไม่ใช่ซ้อน"""
        original = self._rows()
        position = next(i for i, r in enumerate(original)
                        if (r["vehicle_id"], r["category_id"]) == ("byd-atto-2", "grab.suv"))
        self.assertEqual(self._import([self._verified(vehicle_id="byd-atto-2")]), 0)
        rows = self._rows()
        same_cell = [r for r in rows if (r["vehicle_id"], r["category_id"]) == ("byd-atto-2", "grab.suv")]
        self.assertEqual(len(same_cell), 1)
        self.assertEqual(rows[position]["eligibility"], "eligible")
        self.assertEqual(len(rows), len(original))

    def test_invalid_row_writes_nothing(self):
        """ทั้งหมดหรือไม่มีเลย — แถวดีหนึ่งแถว + แถวผิดหนึ่งแถว = ไม่เขียนอะไร"""
        rows = [self._verified(), self._verified(vehicle_id="byd-seal", source_url="")]
        self.assertEqual(self._import(rows), 1)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before)

    def test_unknown_vehicle_writes_nothing(self):
        self.assertEqual(self._import([self._verified(vehicle_id="not-a-car")]), 1)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before)

    def test_dry_run_writes_nothing(self):
        self.assertEqual(self._import([self._verified()], dry_run=True), 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before)

    def test_jsonl_input_is_accepted(self):
        self.assertEqual(self._import([self._verified()], name="in.jsonl"), 0)

    def test_last_row_wins_within_one_file(self):
        rows = [self._verified(eligibility="eligible"),
                self._verified(eligibility="ineligible", checked_at="2026-09-23")]
        self.assertEqual(self._import(rows), 0)
        cell = [r for r in self._rows()
                if (r["vehicle_id"], r["category_id"]) == ("tesla-model-y", "grab.suv")]
        self.assertEqual([r["eligibility"] for r in cell], ["ineligible"])

    def test_tier_is_validated(self):
        bad = self._verified(vehicle_id="bmw-i5", category_id="grab.exec", tier="xxl")
        self.assertEqual(self._import([bad]), 1)
        good = self._verified(vehicle_id="bmw-i5", category_id="grab.exec", tier="m")
        self.assertEqual(self._import([good]), 0)

    def test_imported_row_changes_the_resolved_answer(self):
        """ปิดวงจร: นำเข้าแล้ว resolve ต้องให้คำตอบใหม่จริง"""
        self.assertEqual(self._import([self._verified()]), 0)
        reference, vehicles, _claims = load_all()
        from evbuild.loader import load_claims
        claims = load_claims(self.target)
        resolved = resolve_all(reference, vehicles, claims, as_of=AS_OF)
        row = next(r for r in resolved
                   if (r.vehicle_id, r.category_id) == ("tesla-model-y", "grab.suv"))
        self.assertEqual((row.eligibility, row.basis), ("eligible", "official_list"))


if __name__ == "__main__":
    unittest.main()
