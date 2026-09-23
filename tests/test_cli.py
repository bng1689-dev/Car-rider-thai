"""เทสต์ระดับคำสั่ง — ครอบสิ่งที่เทสต์ระดับฟังก์ชันมองไม่เห็น

เทสต์ชุดอื่นเรียก validator ตรง ๆ จึงไม่เคยเจอว่า `python -m evbuild validate`
พังด้วย traceback ก่อนที่ validator จะได้ทำงาน และไม่เคยเจอว่าตัวเลือกที่
README บอกไว้ ใช้ตามที่เขียนไม่ได้ ทั้งสองอย่างถูกพบจากการรีวิว
"""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from evbuild import cli, view
from evbuild.loader import ELIGIBILITY_PATH, VEHICLES_PATH
from evbuild.resolve import DEFAULT_STALE_DAYS


def run(argv: list[str]) -> tuple[int, str]:
    """เรียก CLI จริง คืน (exit code, ข้อความที่พิมพ์ออกมาทั้งหมด)"""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue() + err.getvalue()


class TestSharedOptionPositions(unittest.TestCase):
    """ตัวเลือกร่วมต้องใช้ได้ทั้งก่อนและหลังคำสั่งย่อย

    argparse รับตัวเลือกของ parser หลักเฉพาะก่อนคำสั่งย่อยเท่านั้น คำสั่งที่
    README เขียนไว้ (`report stale --days 90`) จึงเคยล้มด้วย
    "unrecognized arguments"

    เทสต์ชุดนี้เรียก cli.main() ตัวจริง แล้วดักที่ฟังก์ชันคำสั่ง เพื่อไม่ให้
    โครงสร้าง parser ในเทสต์เพี้ยนไปจากของจริงเมื่อมีคนแก้ main() ทีหลัง
    """

    def _args_for(self, argv: list[str]):
        captured = {}

        def spy(args):
            captured["args"] = args
            return 0

        originals = (cli.cmd_validate, cli.cmd_build, cli.cmd_report)
        cli.cmd_validate = cli.cmd_build = cli.cmd_report = spy
        try:
            code, _output = run(argv)
        finally:
            cli.cmd_validate, cli.cmd_build, cli.cmd_report = originals
        self.assertEqual(code, 0, f"แยกคำสั่ง {argv} ไม่ได้")
        return captured["args"]

    def test_flag_after_subcommand(self):
        self.assertEqual(self._args_for(["report", "stale", "--days", "90"]).days, 90)

    def test_flag_before_subcommand(self):
        self.assertEqual(self._args_for(["--days", "30", "report", "stale"]).days, 30)

    def test_subcommand_default_does_not_reset_root_value(self):
        """กับดักของ argparse: subparser ที่มี default ปกติจะเขียนทับค่าที่ตั้งไว้แล้ว"""
        self.assertEqual(self._args_for(["--strict", "validate"]).strict, True)
        self.assertEqual(
            self._args_for(["--as-of", "2025-09-15", "report", "qa"]).as_of,
            "2025-09-15",
        )

    def test_defaults_applied_when_absent(self):
        args = self._args_for(["report", "stale"])
        self.assertEqual(args.days, DEFAULT_STALE_DAYS)
        self.assertIsNone(args.as_of)
        self.assertFalse(args.strict)

    def test_build_out_defaults_to_none(self):
        self.assertIsNone(self._args_for(["build", "xlsx"]).out)

    def test_every_command_documented_in_readme_parses(self):
        readme_commands = [
            ["validate"],
            ["build"],
            ["build", "xlsx", "html"],
            ["report", "coverage"],
            ["report", "stale", "--days", "90"],
            ["report", "qa"],
            ["report", "summary", "--as-of", "2025-09-15"],
            ["validate", "--strict"],
            ["build", "csv", "--out", "/tmp/x"],
        ]
        for argv in readme_commands:
            with self.subTest(argv=" ".join(argv)):
                self._args_for(argv)


class TestValidateBeforeResolve(unittest.TestCase):
    """`validate` ต้องรายงานข้อมูลผิด ไม่ใช่พังด้วย traceback

    rules engine สมมติว่าชนิดข้อมูลถูกต้องแล้ว ถ้า resolve ทำงานก่อนตรวจ
    ข้อมูลผิดชนิดจะทำให้ TypeError/ValueError หลุดออกมา ซึ่งขัดกับสัญญา
    ของคำสั่งนี้โดยตรง
    """

    def setUp(self):
        self.originals = {
            VEHICLES_PATH: VEHICLES_PATH.read_text(encoding="utf-8"),
            ELIGIBILITY_PATH: ELIGIBILITY_PATH.read_text(encoding="utf-8"),
        }

    def tearDown(self):
        for path, text in self.originals.items():
            path.write_text(text, encoding="utf-8")

    def _corrupt_first_vehicle(self, **fields):
        lines = self.originals[VEHICLES_PATH].splitlines()
        record = json.loads(lines[0])
        record.update(fields)
        lines[0] = json.dumps(record, ensure_ascii=False, sort_keys=True)
        VEHICLES_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_string_seats_reports_error_not_traceback(self):
        self._corrupt_first_vehicle(seats="five")
        code, output = run(["validate"])
        self.assertEqual(code, 1)
        self.assertIn("seats", output)
        self.assertNotIn("Traceback", output)
        self.assertNotIn("TypeError", output)

    def test_unknown_body_type_reports_error(self):
        self._corrupt_first_vehicle(body_type="spaceship")
        code, output = run(["validate"])
        self.assertEqual(code, 1)
        self.assertIn("body_types.yaml", output)
        self.assertNotIn("Traceback", output)

    def test_bad_launch_status_reports_error(self):
        self._corrupt_first_vehicle(launch={"status": "maybe_someday"})
        code, output = run(["validate"])
        self.assertEqual(code, 1)
        self.assertIn("launch.status", output)
        self.assertNotIn("Traceback", output)

    def test_build_stops_before_writing_any_file(self):
        """ข้อมูลผิดต้องล้มก่อนสร้างไฟล์ ไม่ใช่ล้มกลางทางหลังเขียนไฟล์แรกไปแล้ว"""
        self._corrupt_first_vehicle(seats="five")
        with tempfile.TemporaryDirectory() as tmp:
            code, output = run(["build", "--out", tmp])
            self.assertEqual(code, 1)
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertNotIn("Traceback", output)

    def test_clean_data_still_passes(self):
        code, output = run(["validate"])
        self.assertEqual(code, 0)
        self.assertIn("ข้อมูลผ่านการตรวจทั้งหมด", output)



class TestSurveyGapAccounting(unittest.TestCase):
    """หมวด not_surveyed ที่มีข้อกล่าวอ้างแล้ว ต้องไม่ถูกบรรยายว่า "ไม่มีเลย"

    ข้อมูลจริงมีกรณีนี้อยู่: bolt.premium ประกาศ not_surveyed แต่มีข้อกล่าวอ้าง
    unverified ของ byd-denza-z9gt อยู่ 1 แถว รายงานจึงเคยบอกว่าไม่มีข้อกล่าวอ้าง
    เลย และรถคันเดียวกันโผล่สองครั้งในชีต "งานค้าง" ด้วยเหตุผลที่ขัดกันเอง
    """

    def setUp(self):
        from evbuild.loader import load_all
        from evbuild.resolve import resolve_all

        self.reference, self.vehicles, self.claims = load_all()
        self.resolved = resolve_all(self.reference, self.vehicles, self.claims,
                                    as_of=date(2025, 9, 15))
        self.gaps = view.survey_gaps(self.reference, self.vehicles, self.resolved)

    def test_fixture_still_has_the_tricky_case(self):
        """ถ้าข้อมูลเปลี่ยนจนไม่มีกรณีนี้แล้ว เทสต์ข้างล่างจะไร้ความหมาย — บอกให้รู้"""
        bolt_premium = next(g for g in self.gaps if g["category"].id == "bolt.premium")
        self.assertTrue(bolt_premium["claimed"],
                        "bolt.premium ควรมีข้อกล่าวอ้างอยู่ จึงจะทดสอบกรณีนี้ได้")

    def test_summary_wording_reflects_existing_claims(self):
        bolt_premium = next(g for g in self.gaps if g["category"].id == "bolt.premium")
        text = view.survey_gap_summary(bolt_premium)
        self.assertNotIn("ไม่มีข้อกล่าวอ้างแม้แต่แถวเดียว", text)
        self.assertIn("สำรวจแล้วบางส่วน", text)

    def test_summary_says_none_when_truly_none(self):
        grab_van = next(g for g in self.gaps if g["category"].id == "grab.van")
        self.assertEqual(grab_van["claimed"], 0)
        self.assertIn("ไม่มีข้อกล่าวอ้างแม้แต่แถวเดียว",
                      view.survey_gap_summary(grab_van))

    def test_claimed_vehicles_excluded_from_candidates(self):
        """รถที่มีข้อกล่าวอ้างแล้ว ไม่ใช่ "งานที่ยังไม่แตะ" — ห้ามนับซ้ำ"""
        for gap in self.gaps:
            claimed_ids = {
                c.vehicle_id for c in self.claims
                if c.category_id == gap["category"].id
            }
            candidate_ids = {v.vehicle_id for v in gap["candidates"]}
            with self.subTest(category=gap["category"].id):
                self.assertEqual(claimed_ids & candidate_ids, set())

    def test_work_queue_sheet_lists_each_vehicle_once_per_category(self):
        import openpyxl

        from evbuild.render import xlsx as render_xlsx

        with tempfile.TemporaryDirectory() as tmp:
            path = render_xlsx.build(self.reference, self.vehicles, self.resolved,
                                     as_of=date(2025, 9, 15),
                                     stale_days=90, out_dir=Path(tmp))
            sheet = openpyxl.load_workbook(path)["งานค้าง"]
            rows = [(r[0].value, r[2].value) for r in sheet.iter_rows(min_row=2)]

        self.assertTrue(rows)
        self.assertEqual(len(rows), len(set(rows)),
                         "มีรถซ้ำในหมวดเดียวกันในชีต 'งานค้าง'")

    def test_coverage_report_does_not_contradict_itself(self):
        from evbuild import reports

        text = "\n".join(reports.coverage(self.reference, self.vehicles, self.resolved))
        premium_block = text.split("bolt.premium")[1].split("\n\n")[0]
        self.assertNotIn("ไม่มีข้อกล่าวอ้างแม้แต่แถวเดียว", premium_block)

if __name__ == "__main__":
    unittest.main()
