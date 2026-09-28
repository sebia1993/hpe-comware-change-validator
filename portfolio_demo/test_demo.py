import io
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from streamlit.testing.v1 import AppTest
from portfolio_demo.runtime import DemoRuntime


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.r = DemoRuntime()
        self.addCleanup(self.r.close)

    def test_workflow_rules_unknown_recovery_and_export(self):
        r = self.r
        with patch(
            "socket.create_connection", side_effect=AssertionError("No network")
        ):
            self.assertFalse(r.check().has_errors)
            r.capture("작업 전")
            self.assertEqual(r.baseline, 0)
            r.capture("백본3 OFF 중")
            self.assertEqual(r.pair, (0, 1))
            self.assertTrue(
                any(
                    x["Severity"] == "Critical" and x["Classification"] == "Unexpected"
                    for x in r.rows
                )
            )
            self.assertTrue(any(x["Severity"] == "Warning" for x in r.rows))
            self.assertEqual(sum(x["Classification"] == "Unknown" for x in r.rows), 11)
            r.compare(0, 1, planned_off=True)
            self.assertTrue(
                any(
                    x["Severity"] == "Critical" and x["Classification"] == "Expected"
                    for x in r.rows
                )
            )
            self.assertNotIn(str(r.root), r.html)
            self.assertIn("예상되지 않은 긴급/주의", r.html)
            self.assertEqual(
                sum(x["Severity"] == "Unknown" for x in r.rows),
                sum(i.severity == "Unknown" for i in r.summary.items),
            )
            self.assertIn('data-filter="Unknown"', r.html)
            with ZipFile(io.BytesIO(r.zip_bytes)) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("reports/diff_report.html", archive.namelist())
                self.assertNotIn(
                    str(r.root), archive.read("reports/diff_report.html").decode()
                )
            r.capture("복구 후")
            self.assertEqual(r.pair, (0, 2))
            self.assertTrue(all(x["Classification"] == "Unchanged" for x in r.rows))
            r.compare(1, 2)
            self.assertEqual(sum(x["Classification"] == "Unknown" for x in r.rows), 11)
            r.capture(
                "사용자 지정", "VLAN rollout", vlan=True, resource=True, timeout=True
            )
            self.assertEqual(r.pair, (0, 3))
            r.compare(0, 3, planned_vlan=True)
            self.assertEqual(sum(x["Classification"] == "Expected" for x in r.rows), 4)
            self.assertTrue(
                any(
                    x["Command"] == "cpu_usage"
                    and x["Severity"] == "Critical"
                    and x["Classification"] == "Unexpected"
                    for x in r.rows
                )
            )
            self.assertEqual(sum(x["Classification"] == "Unknown" for x in r.rows), 1)
            self.assertTrue(any(i.changed_lines for i in r.summary.items))
            r.capture("작업 전")
            self.assertEqual(r.baseline, 4)
            self.assertIsNone(r.summary)
            r.capture("복구 후")
            self.assertEqual(r.pair, (4, 5))
            self.assertTrue(
                {
                    "Preflight",
                    "Collect Started",
                    "Snapshot Saved",
                    "Baseline Selected",
                    "Auto Compare",
                    "Manual Compare",
                    "Collection Error",
                    "Report Generated",
                }
                <= {x["Event"] for x in r.logs}
            )

    def test_isolation_bounds_and_cleanup(self):
        other = DemoRuntime()
        self.addCleanup(other.close)
        self.r.capture("작업 전")
        self.assertFalse(other.catalog)
        self.assertNotEqual(other.root, self.r.root)
        with self.assertRaises(ValueError):
            self.r.compare(-1, 0)
        with self.assertRaises(ValueError):
            self.r.capture("invalid")
        for _ in range(19):
            self.r.capture("작업 전")
        with self.assertRaises(ValueError):
            self.r.capture("복구 후")
        root = self.r.root
        self.r.close()
        self.assertFalse(root.exists())
        self.assertTrue(other.root.exists())

    def test_streamlit_collection_compare_reset(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()

        def button(label):
            return next(b for b in app.button if b.label == label)

        def select(label):
            return next(s for s in app.selectbox if s.label == label)

        button("설정 점검").click().run()
        button("상태 수집 시작").click().run()
        select("작업 단계").select("백본3 OFF 중").run()
        button("상태 수집 시작").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.runtime.pair, (0, 1))
        app.radio[0].set_value("비교 결과").run()
        self.assertFalse(app.exception)
        next(
            c for c in app.checkbox if c.label == "BB3 OFF 영향을 계획된 변경으로 등록"
        ).check().run()
        button("선택 항목 비교").click().run()
        self.assertTrue(app.session_state.runtime.options[0])
        root = app.session_state.runtime.root
        button("Demo Reset").click().run()
        self.assertFalse(root.exists())
        self.assertFalse(app.session_state.runtime.catalog)
        self.assertFalse(app.exception)
        app.radio[0].set_value("비교 결과").run()
        button("샘플 검증 생성").click().run()
        self.assertEqual(app.session_state.runtime.pair, (0, 1))
        self.assertIsNotNone(app.session_state.runtime.summary)
        self.assertFalse(app.exception)

    def test_execution_trace_snapshot_diff_classification_and_sample(self):
        r = self.r
        updates = []
        r.execution.on_change = lambda: updates.append(
            [s.status for s in r.execution.steps]
        )
        with r.execution.operation("작업 전후 검증"):
            r.capture("작업 전")
            r.capture("백본3 OFF 중")
        steps = {s.id: s for s in r.execution.steps}
        self.assertTrue(
            {"preflight", "collect", "snapshot", "diff", "classification", "report"}
            <= steps.keys()
        )
        self.assertEqual(
            [
                s.evidence["snapshot_id"]
                for s in r.execution.steps
                if s.id == "snapshot"
            ],
            [1, 2],
        )
        self.assertEqual(steps["diff"].evidence["items"], len(r.summary.items))
        counts = steps["classification"].evidence["classification"]
        for label, count in counts.items():
            self.assertEqual(
                count, sum(row["Classification"] == label for row in r.rows)
            )
        self.assertGreater(counts["Unknown"], 0)
        self.assertEqual(steps["classification"].status, "warning")
        self.assertEqual(steps["report"].evidence["zip_bytes"], len(r.zip_bytes))
        self.assertTrue(any("running" in update for update in updates))
        r.capture("복구 후")
        step = next(s for s in r.execution.steps if s.id == "classification")
        self.assertEqual(step.evidence["classification"]["Unchanged"], len(r.rows))
        self.assertEqual(step.evidence["classification"]["Unknown"], 0)
        app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        app.radio[0].set_value("비교 결과").run()
        next(b for b in app.button if b.label == "샘플 검증 생성").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                "실행 과정" in m.value and "ReportWriter" in m.value
                for m in app.markdown
            )
        )
        self.assertTrue(app.session_state.runtime.rows)


if __name__ == "__main__":
    unittest.main()
