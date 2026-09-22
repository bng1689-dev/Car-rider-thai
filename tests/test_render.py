"""ตัวเรนเดอร์ — เน้นช่องโหว่การฉีดโค้ดที่ระบบเดิมเปิดไว้

ข้อมูลวันนี้คัดด้วยมือ ความเสี่ยงต่ำ แต่แผนใน README คือ
"ดึง Grab model list อัตโนมัติ" — วันที่ข้อมูลมาจาก scraper
ช่องเหล่านี้กลายเป็นช่องโหว่ใช้งานได้ทันที
"""
import json
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

from evbuild.render import fill_template, html_escape, json_for_script
from evbuild.render import html as render_html
from evbuild.resolve import resolve_all
from tests import make_claim, make_reference, make_vehicle

HOSTILE_MODEL = '</script><img src=x onerror=alert(1)>"\'&'


class TestEscaping(unittest.TestCase):
    def test_html_escape_covers_all_five(self):
        self.assertEqual(html_escape("<a href=\"x\">&'"),
                         "&lt;a href=&quot;x&quot;&gt;&amp;&#39;")

    def test_json_for_script_neutralises_script_close(self):
        """json.dumps ไม่ escape '<' — สตริง '</script>' ทำให้หน้าเว็บพังทันที"""
        payload = json_for_script({"model": HOSTILE_MODEL})
        self.assertNotIn("</script>", payload)
        self.assertNotIn("<", payload)
        self.assertNotIn(">", payload)
        # ยังต้อง parse กลับได้ค่าเดิมเป๊ะ
        self.assertEqual(json.loads(payload)["model"], HOSTILE_MODEL)

    def test_json_for_script_handles_line_separators(self):
        payload = json_for_script({"note": "a b c"})
        self.assertNotIn(" ", payload)
        self.assertEqual(json.loads(payload)["note"], "a b c")

    def test_thai_text_survives_round_trip(self):
        payload = json_for_script({"note": "รถกระบะ — ทั้ง 2 แอปไม่รับ"})
        self.assertEqual(json.loads(payload)["note"], "รถกระบะ — ทั้ง 2 แอปไม่รับ")


class TestFillTemplate(unittest.TestCase):
    def test_replaces_only_once(self):
        """str.replace() แทนที่ทุกตำแหน่ง — placeholder ซ้ำจะได้ข้อมูลซ้ำเงียบ ๆ"""
        result = fill_template("A/*__X__*/B/*__X__*/C", {"/*__X__*/": "1"})
        self.assertEqual(result, "A1B/*__X__*/C")

    def test_missing_placeholder_raises(self):
        with self.assertRaises(ValueError):
            fill_template("no placeholder here", {"/*__X__*/": "1"})


class TestSearchPageOutput(unittest.TestCase):
    def test_hostile_model_name_cannot_break_out_of_script(self):
        reference = make_reference()
        vehicle = make_vehicle(vehicle_id="evil", model=HOSTILE_MODEL, body_type="suv")
        claims = [make_claim(vehicle_id="evil", category_id="grab.premium")]
        resolved = resolve_all(reference, [vehicle], claims, as_of=date(2025, 9, 15))

        with tempfile.TemporaryDirectory() as tmp:
            path = render_html.build(reference, [vehicle], resolved,
                                     as_of=date(2025, 9, 15), stale_days=90,
                                     out_dir=Path(tmp))
            page = path.read_text(encoding="utf-8")

        # ต้องมี <script> เปิด/ปิด เท่าที่ template กำหนด ไม่มีตัวเกินจากข้อมูล
        self.assertEqual(page.count("<script"), 3)
        self.assertEqual(page.count("</script>"), 3)

        block = re.search(r'id="ev-data">(.*?)</script>', page, re.S).group(1)
        # ในบล็อกข้อมูลต้องไม่มี < หรือ > ดิบเลย — จึงสร้างแท็กใหม่ไม่ได้
        # ข้อความ onerror= ที่เหลืออยู่เป็นแค่ตัวอักษรใน JSON string ไม่ใช่ attribute
        self.assertNotIn("<", block)
        self.assertNotIn(">", block)
        # และข้อมูลยังถอดกลับได้ตรงต้นฉบับเป๊ะ
        self.assertEqual(json.loads(block)[0]["model"], HOSTILE_MODEL)

    def test_page_contains_provenance_metadata(self):
        reference = make_reference()
        vehicle = make_vehicle(vehicle_id="x", body_type="suv")
        resolved = resolve_all(reference, [vehicle], [], as_of=date(2025, 9, 15))
        with tempfile.TemporaryDirectory() as tmp:
            path = render_html.build(reference, [vehicle], resolved,
                                     as_of=date(2025, 9, 15), stale_days=90,
                                     out_dir=Path(tmp))
            page = path.read_text(encoding="utf-8")
        meta = json.loads(re.search(r'id="ev-meta">(.*?)</script>', page, re.S).group(1))
        self.assertEqual(meta["as_of"], "2025-09-15")
        self.assertEqual(meta["stale_days"], 90)
        self.assertTrue(any(c["id"] == "grab.van" for c in meta["not_surveyed"]))


class TestCsvExport(unittest.TestCase):
    def test_i2_export_only_contains_real_links(self):
        """i2: หนึ่งแถว = หนึ่งความสัมพันธ์ที่มีอยู่จริง — 'ไม่ผ่าน' ไม่ใช่ความสัมพันธ์"""
        import csv

        from evbuild.render import csvx

        reference = make_reference()
        vehicle = make_vehicle(vehicle_id="x", body_type="suv")
        resolved = resolve_all(reference, [vehicle], [], as_of=date(2025, 9, 15))
        with tempfile.TemporaryDirectory() as tmp:
            paths = csvx.build(reference, [vehicle], resolved,
                               as_of=date(2025, 9, 15), stale_days=90,
                               out_dir=Path(tmp))
            i2_path = next(p for p in paths if p.name == "i2-links.csv")
            with i2_path.open(encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))

        self.assertTrue(rows)
        self.assertTrue(all(r["Link_Type"] == "Eligibility" for r in rows))
        self.assertNotIn("ไม่ผ่าน", {r["Link_Label"] for r in rows})
        # ทุกความสัมพันธ์ต้องมีที่มาและวันที่กำกับ
        for row in rows:
            self.assertTrue(row["Attribute_Basis"])


if __name__ == "__main__":
    unittest.main()
