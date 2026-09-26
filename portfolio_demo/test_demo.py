from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_demo.logic import SCENARIOS, run_demo
from streamlit.testing.v1 import AppTest


class DemoTests(unittest.TestCase):
    def test_all_scenarios_through_ui_without_network(self):
        for scenario in SCENARIOS:
            with (
                self.subTest(scenario=scenario),
                patch(
                    "socket.create_connection", side_effect=AssertionError("No network")
                ),
            ):
                app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run(
                    timeout=20
                )
                self.assertFalse(app.exception)
                app.selectbox[0].select(scenario).run()
                next(b for b in app.button if b.label == "분석 실행").click().run(
                    timeout=20
                )
                self.assertFalse(app.exception)
                self.assertTrue(app.metric)
                self.assertTrue(app.dataframe)
                # Re-render must retain the result without re-running analysis.
                app.run()
                self.assertFalse(app.exception)
                self.assertIn("result", app.session_state)

    def test_expected_unexpected_critical_and_no_change(self):
        normal = run_demo("expected")
        self.assertEqual(normal["status"], "Validation Passed")
        self.assertEqual(normal["counts"]["Expected"], 2)
        self.assertEqual(normal["counts"]["Unknown"], 0)
        unexpected = run_demo("unexpected")
        self.assertEqual(unexpected["counts"]["Unexpected"], 2)
        critical = run_demo("critical")
        self.assertGreaterEqual(critical["counts"]["Critical"], 3)
        self.assertEqual(run_demo("no_change")["counts"]["Unexpected"], 0)
        failed = run_demo("collection_failed")
        self.assertEqual(failed["status"], "Unknown / Collection Error")
        self.assertEqual(failed["counts"]["Critical"], 0)
        self.assertEqual(failed["counts"]["Unknown"], 1)
        for result in (normal, unexpected, critical, failed):
            self.assertEqual(len(result["rows"]), 10)
            self.assertIn("<!doctype html", result["html"].lower())
            self.assertNotIn("comware-demo-", result["html"])


if __name__ == "__main__":
    unittest.main()
