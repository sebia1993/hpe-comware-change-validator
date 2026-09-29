import io
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from streamlit.testing.v1 import AppTest
from portfolio_demo.fixture_collector import COMMANDS, DATA, DEVICES
from portfolio_demo.runtime import DemoRuntime
from portfolio_demo.scenario_view import temporal_comparison_rows
from portfolio_demo.scenario_runner import (
    ScenarioRunner,
    counts,
    conclusion,
    business_finding,
    SCENARIOS,
)


class FixtureFormatTests(unittest.TestCase):
    def test_official_format_synthetic_fixtures_have_comware_shapes(self):
        commands = DATA["commands"]
        self.assertIn(
            "Brief information on interface(s) under route mode:",
            commands["interface_brief"][2],
        )
        self.assertIn(
            "Aggregation Interface Type:",
            commands["link_aggregation_summary"][2],
        )
        self.assertIn("VLAN ID: 10", commands["vlan_summary"][2])
        self.assertIn("Neighbor Brief Information", commands["ospf_peer"][2])
        self.assertIn("Public Routing Table : OSPF", commands["ospf_routes"][2])
        self.assertIn("IPv4 Standby Information:", commands["vrrp_status"][2])
        self.assertIn("Unit CPU usage:", commands["cpu_usage"][2])
        self.assertIn("FreeRatio", commands["memory_usage"][2])
        self.assertIn("Power   1 State: Normal", commands["power_status"][2])
        self.assertIn("State : Normal", commands["fan_status"][2])


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
            self.assertEqual(
                sum(x["Classification"] == "Unknown" for x in r.rows),
                len(COMMANDS) + 1,
            )
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
            self.assertEqual(
                sum(x["Classification"] == "Unknown" for x in r.rows),
                len(COMMANDS) + 1,
            )
            r.capture(
                "사용자 지정", "VLAN rollout", vlan=True, resource=True, timeout=True
            )
            self.assertEqual(r.pair, (0, 3))
            r.compare(0, 3, planned_vlan=True)
            self.assertEqual(
                sum(x["Classification"] == "Expected" for x in r.rows),
                len(DEVICES),
            )
            self.assertTrue(
                any(
                    x["Command"] == "cpu_usage"
                    and x["Severity"] == "Critical"
                    and x["Classification"] == "Unexpected"
                    for x in r.rows
                )
            )
            self.assertEqual(sum(x["Classification"] == "Unknown" for x in r.rows), 2)
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

    def test_report_bundle_failure_clears_previous_downloads(self):
        r = self.r
        r.capture("작업 전")
        r.capture("사용자 지정", "VLAN rollout", vlan=True, planned_vlan=True)
        for repeat in ("report", "compare"):
            with self.subTest(repeat=repeat):
                self.assertTrue(r.html and r.zip_bytes)
                report_count = sum(log["Event"] == "Report Generated" for log in r.logs)
                with patch(
                    "portfolio_demo.runtime.create_share_report_bundle",
                    side_effect=OSError("archive blocked"),
                ):
                    with self.assertRaisesRegex(OSError, "archive blocked"):
                        if repeat == "report":
                            r.report_pending_comparison()
                        else:
                            r.compare(0, 1, planned_vlan=True)
                self.assertFalse(r.html)
                self.assertFalse(r.zip_bytes)
                report_steps = [s for s in r.execution.steps if s.id == "report"]
                self.assertEqual(report_steps[-1].status, "failure")
                self.assertFalse(report_steps[-1].evidence)
                self.assertEqual(
                    sum(log["Event"] == "Report Generated" for log in r.logs),
                    report_count,
                )
                self.assertTrue(r.rows)
                r.compare(0, 1, planned_vlan=True)
                self.assertTrue(r.html and r.zip_bytes)

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


def finish_autorun(app):
    for _ in range(16):
        if (
            "scenario_autorun" not in app.session_state
            or not app.session_state["scenario_autorun"]
        ):
            return app
        app.run()
    raise AssertionError("scenario autorun did not complete")


class ScenarioTests(unittest.TestCase):
    def runner(self, key):
        runner = ScenarioRunner()
        self.addCleanup(runner.runtime.close)
        runner.play(key)
        return runner

    def test_representative_calls_real_workflow_and_report(self):
        runner = ScenarioRunner()
        r = runner.runtime
        self.addCleanup(r.close)
        updates = []
        with (
            patch("socket.create_connection", side_effect=AssertionError("No network")),
            patch.object(r, "check", wraps=r.check) as check,
            patch.object(r, "capture", wraps=r.capture) as capture,
            patch.object(
                r, "prepare_comparison", wraps=r.prepare_comparison
            ) as prepare,
            patch.object(
                r,
                "classify_pending_comparison",
                wraps=r.classify_pending_comparison,
            ) as classify,
            patch.object(
                r,
                "report_pending_comparison",
                wraps=r.report_pending_comparison,
            ) as report,
        ):
            run = runner.play(
                "representative",
                lambda current: updates.append([s.status for s in current.run.steps]),
            )
        self.assertTrue(run.completed)
        self.assertTrue(check.called)
        self.assertEqual(capture.call_count, 2)
        prepare.assert_called_once_with(0, 1, False, True, automatic=True)
        classify.assert_called_once_with()
        report.assert_called_once_with()
        self.assertEqual(r.pair, (0, 1))
        self.assertEqual(len(r.catalog), 2)
        self.assertEqual(len(run.steps), 6)
        self.assertTrue(all(s.status in ("success", "warning") for s in run.steps))
        self.assertTrue(any("running" in update for update in updates))
        self.assertGreater(counts(r)["Expected"], 0)
        self.assertGreater(counts(r)["Unexpected"], 0)
        self.assertTrue(r.html)
        with ZipFile(io.BytesIO(r.zip_bytes)) as archive:
            self.assertIsNone(archive.testzip())
            # Snapshot/report text uses platform-native newlines on Windows.
            self.assertEqual(
                archive.read("reports/diff_report.html").decode().replace("\r\n", "\n"),
                r.html,
            )
        self.assertIsNone(r.execution.on_change)
        self.assertIsNotNone(r.execution.elapsed_ms)

    def test_state_machine_advances_one_real_phase_at_a_time(self):
        runner = ScenarioRunner()
        r = runner.runtime
        self.addCleanup(r.close)
        run = runner.start("representative")
        self.assertEqual(run.current_index, 0)
        self.assertEqual(run.steps[0].status, "running")
        self.assertFalse(r.catalog)
        self.assertFalse(r.execution.steps)

        expected = ("preflight", "before", "after", "diff", "classify", "report")
        trace_ids = []
        with patch("socket.create_connection", side_effect=AssertionError("No network")):
            for index, step_id in enumerate(expected):
                self.assertEqual(run.steps[index].id, step_id)
                runner.advance()
                trace_ids.extend(
                    ["collect", "snapshot"]
                    if step_id in ("before", "after")
                    else ["classification" if step_id == "classify" else step_id]
                )
                self.assertEqual([s.id for s in r.execution.steps], trace_ids)
                self.assertEqual(r.execution.depth, 0)
                self.assertIn(run.steps[index].status, ("success", "warning"))
                self.assertIsNotNone(run.steps[index].elapsed_ms)
                self.assertEqual(len(r.catalog), min(index, 2))
                self.assertEqual(r.pending_compare is not None, index >= 3)
                self.assertEqual(r.summary is not None, index >= 4)
                self.assertEqual(bool(r.html and r.zip_bytes), index == 5)
                if index + 1 < len(expected):
                    self.assertEqual(run.current_index, index + 1)
                    self.assertEqual(run.steps[index + 1].status, "running")
                    self.assertIsNone(r.execution.elapsed_ms)

        self.assertTrue(run.completed)
        self.assertEqual(run.current_index, 6)
        self.assertEqual(r.execution.elapsed_ms, run.elapsed_ms)
        self.assertEqual(r.execution.label, run.name)
        self.assertEqual(
            [s.evidence["snapshot_id"] for s in r.execution.steps if s.id == "snapshot"],
            [1, 2],
        )
        self.assertEqual(r.pair, (0, 1))
        retained = list(r.execution.steps)
        runner.advance()
        self.assertEqual(r.execution.steps, retained)
        # A later direct operation is independent of the completed scenario.
        r.check()
        self.assertEqual([s.id for s in r.execution.steps], ["preflight"])

    def test_incremental_failure_retains_evidence_and_restart_is_clean(self):
        runner = ScenarioRunner()
        self.addCleanup(lambda: runner.runtime.close())
        for failed_phase in (1, 5):
            with self.subTest(failed_phase=failed_phase):
                runner.start("representative")
                r = runner.runtime
                for _ in range(failed_phase):
                    runner.advance()
                retained = list(r.execution.steps)
                method = "capture" if failed_phase == 1 else "report_pending_comparison"
                with patch.object(r, method, side_effect=ValueError("phase blocked")):
                    with self.assertRaisesRegex(ValueError, "phase blocked"):
                        runner.advance()
                self.assertFalse(runner.run.completed)
                self.assertEqual(runner.run.steps[failed_phase].status, "failure")
                self.assertEqual(r.execution.steps[:-1], retained)
                self.assertEqual(r.execution.steps[-1].id, "execution_error")
                self.assertEqual(r.execution.steps[-1].status, "failure")
                self.assertEqual(r.execution.depth, 0)
                self.assertIsNotNone(r.execution.elapsed_ms)
                self.assertFalse(r.html or r.zip_bytes)
                failed_trace = list(r.execution.steps)
                runner.advance()
                self.assertEqual(r.execution.steps, failed_trace)
                # Failure releases trace nesting before an independent action.
                r.check()
                self.assertEqual([s.id for s in r.execution.steps], ["preflight"])
                old_root = r.root
                runner.start("normal")
                self.assertFalse(old_root.exists())
                self.assertFalse(runner.runtime.catalog)
                self.assertFalse(runner.runtime.rows)
                self.assertFalse(runner.runtime.execution.steps)
                for _ in range(6):
                    runner.advance()
                self.assertTrue(runner.run.completed)
                self.assertEqual(runner.runtime.pair, (0, 1))
                self.assertEqual(counts(runner.runtime)["Unexpected"], 0)
                self.assertEqual(
                    [
                        s.evidence["snapshot_id"]
                        for s in runner.runtime.execution.steps
                        if s.id == "snapshot"
                    ],
                    [1, 2],
                )

    def test_incremental_report_bundle_failure_exposes_no_downloads(self):
        runner = ScenarioRunner()
        self.addCleanup(runner.runtime.close)
        runner.start("normal")
        for _ in range(5):
            runner.advance()
        r = runner.runtime
        self.assertTrue(r.rows)
        self.assertEqual(runner.run.current_index, 5)
        with patch(
            "portfolio_demo.runtime.create_share_report_bundle",
            side_effect=OSError("archive blocked"),
        ):
            with self.assertRaisesRegex(OSError, "archive blocked"):
                runner.advance()
        self.assertFalse(runner.run.completed)
        self.assertEqual(runner.run.error, "archive blocked")
        self.assertEqual(runner.run.steps[5].status, "failure")
        self.assertFalse(r.html)
        self.assertFalse(r.zip_bytes)
        report = next(s for s in r.execution.steps if s.id == "report")
        self.assertEqual(report.status, "failure")
        self.assertEqual(report.detail, "OSError")
        self.assertFalse(report.evidence)
        self.assertEqual(r.execution.steps[-1].id, "execution_error")
        self.assertTrue(r.rows)
        self.assertIsNotNone(r.execution.elapsed_ms)
        self.assertEqual(r.execution.depth, 0)

    def test_representative_compares_same_devices_across_two_timepoints(self):
        runner = self.runner("representative")
        r = runner.runtime
        rows = temporal_comparison_rows(r)

        self.assertEqual(
            {row["동일 장비"] for row in rows},
            {"DEMO-BB3", "DEMO-BB4"},
        )
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["T0 수집 결과"], len(COMMANDS))
            self.assertEqual(row["T1 수집 결과"], len(COMMANDS))
            self.assertEqual(row["동일 항목 비교"], len(COMMANDS) + 1)
            self.assertNotEqual(row["T0 · 기준 시점"], "")
            self.assertNotEqual(row["T1 · 비교 시점"], "")

    def test_representative_has_broad_realistic_comparison_scope(self):
        runner = self.runner("representative")
        r = runner.runtime

        self.assertEqual(len(COMMANDS), 18)
        self.assertEqual(len(DEVICES), 2)
        self.assertEqual(len(r.rows), len(COMMANDS) * len(DEVICES) + len(DEVICES))

        categories = {row["Category"] for row in r.rows}
        self.assertTrue(
            {
                "basic",
                "hardware",
                "interface",
                "switching",
                "routing",
                "resource",
                "log",
                "connection",
            }
            <= categories
        )

        values = counts(r)
        self.assertGreater(values["Unchanged"], values["Expected"])
        self.assertGreater(values["Unexpected"], 5)
        self.assertEqual(values["Expected"], len(DEVICES))
        self.assertEqual(values["Unknown"], 0)

        changed_commands = {
            row["Command"]
            for row in r.rows
            if row["Classification"] in {"Expected", "Unexpected"}
        }
        self.assertTrue(
            {
                "interface_brief",
                "link_aggregation_summary",
                "link_aggregation_verbose",
                "vlan_summary",
                "stp_brief",
                "ospf_peer",
                "ospf_routes",
                "vrrp_status",
                "cpu_usage",
                "memory_usage",
                "alarm_status",
                "recent_log",
            }
            <= changed_commands
        )

    def test_normal_has_only_planned_or_unchanged_results(self):
        r = self.runner("normal").runtime
        values = counts(r)
        self.assertEqual(values["Unexpected"], 0)
        self.assertEqual(values["Unknown"], 0)
        self.assertGreater(values["Expected"], 0)
        self.assertFalse(
            any(
                row["Classification"] == "Unexpected"
                and row["Severity"] in ("Critical", "Warning")
                for row in r.rows
            )
        )
        self.assertTrue(
            any(
                row["Classification"] == "Expected"
                and row["Severity"] == "Warning"
                for row in r.rows
            )
        )
        self.assertIn("추가 확인이 필요한 이상은 발견되지 않았습니다", conclusion(r))

    def test_unexpected_mapping_refers_to_same_finding(self):
        r = self.runner("unexpected").runtime
        self.assertGreater(counts(r)["Unexpected"], 0)
        self.assertIn(str(counts(r)["Unexpected"]), conclusion(r))
        critical_cpu_rows = [
            row
            for row in r.rows
            if row["Command"] == "cpu_usage" and row["Severity"] == "Critical"
        ]
        self.assertTrue(critical_cpu_rows)
        for row in r.rows:
            view = business_finding(r, row)
            item = r.summary.items[view["index"]]
            self.assertEqual(view["device"], item.device_name)
            self.assertEqual(view["severity"], item.severity)
        for row in critical_cpu_rows:
            view = business_finding(r, row)
            self.assertIn("처리 자원", view["message"])
            self.assertIn("긴급 확인", view["message"])

    def test_failure_retains_unknown_in_rows_report_and_business_language(self):
        r = self.runner("failure").runtime
        self.assertGreater(counts(r)["Unknown"], 0)
        self.assertIn("판단할 수 없습니다", conclusion(r))
        self.assertIn("Unknown / Collection Error", r.html)
        before, after = (r.store.load_snapshot(path) for path in r.catalog)
        failed = {
            (item.device_name, item.command_id)
            for item in after.results
            if not item.success
        }
        self.assertTrue(failed)
        self.assertTrue(all(item.success for item in before.results))
        for row in r.rows:
            if (row["Device"], row["Command"]) in failed:
                self.assertEqual(
                    (row["Classification"], row["Severity"]), ("Unknown", "Unknown")
                )
                self.assertEqual(row["After"], "[Collection Error / Unknown]")
                self.assertIn("판단할 수 없습니다", business_finding(r, row)["message"])
                self.assertEqual(r.summary.items[row["Index"]].severity, "Unknown")

    def test_counts_and_trace_match_all_real_scenario_results(self):
        for key in SCENARIOS:
            runner = self.runner(key)
            r = runner.runtime
            values = counts(r)
            self.assertEqual(sum(values.values()), len(r.rows))
            self.assertEqual(len(r.rows), len(r.summary.items))
            classification = next(
                s for s in r.execution.steps if s.id == "classification"
            )
            self.assertEqual(classification.evidence["classification"], values)
            for row in r.rows:
                item = r.summary.items[row["Index"]]
                self.assertEqual(row["Severity"], item.severity)
                if row["Classification"] == "Expected":
                    self.assertEqual(item.expectation, "expected")
            self.assertEqual(
                [
                    s.evidence["snapshot_id"]
                    for s in r.execution.steps
                    if s.id == "snapshot"
                ],
                [1, 2],
            )
            report = next(s for s in r.execution.steps if s.id == "report")
            self.assertEqual(report.evidence["html_bytes"], len(r.html.encode()))
            self.assertEqual(report.evidence["zip_bytes"], len(r.zip_bytes))
            self.assertTrue(all(s.status != "running" for s in r.execution.steps))

    def test_preflight_failure_is_not_reported_as_completion(self):
        runner = ScenarioRunner()
        self.addCleanup(runner.runtime.close)
        with patch.object(
            runner.runtime, "check", side_effect=ValueError("preflight blocked")
        ):
            with self.assertRaises(ValueError):
                runner.play("normal")
        self.assertFalse(runner.run.completed)
        self.assertEqual(runner.run.steps[0].status, "failure")
        self.assertFalse(runner.runtime.html)
        self.assertFalse(runner.runtime.catalog)

    def test_one_click_ui_summary_trace_reports_and_advanced_preserved(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.sidebar.button)
        self.assertTrue(
            any("프로젝트 목적" in markdown.value for markdown in app.markdown)
        )
        self.assertTrue(
            any(
                "이 데모에서 보여주는 것" in markdown.value
                for markdown in app.markdown
            )
        )
        next(
            b for b in app.button if b.label == "▶ 대표 네트워크 작업 검증 보기"
        ).click().run()
        finish_autorun(app)
        self.assertFalse(app.exception)
        r = app.session_state.runtime
        self.addCleanup(r.close)
        self.assertTrue(app.session_state.scenario_runner.run.completed)
        self.assertTrue(any("COMPLETED" in item.value for item in app.success))
        self.assertEqual(
            [s.evidence["snapshot_id"] for s in r.execution.steps if s.id == "snapshot"],
            [1, 2],
        )
        self.assertEqual(r.execution.steps[0].id, "preflight")
        self.assertEqual(r.execution.steps[-1].id, "report")
        metrics = {m.label: m.value for m in app.metric}
        self.assertEqual(metrics["작업 계획과 일치"], str(counts(r)["Expected"]))
        self.assertEqual(metrics["추가 확인 필요"], str(counts(r)["Unexpected"]))
        self.assertEqual(metrics["전체 비교 항목"], str(len(r.rows)))
        self.assertEqual(metrics["대상 장비"], str(len(DEVICES)))
        self.assertEqual(metrics["점검 분야"], "8")
        self.assertTrue(
            any(
                "핵심 비교 방식 · 같은 장비의 T0 ↔ T1" in markdown.value
                for markdown in app.markdown
            )
        )
        self.assertTrue(
            any("가장 먼저 확인할 결과" in markdown.value for markdown in app.markdown)
        )
        self.assertTrue(
            any(
                phrase in markdown.value
                for markdown in app.markdown
                for phrase in (
                    "계획에 없던 변화",
                    "수집하지 못해",
                    "등록된 작업 계획과 일치",
                )
            )
        )
        self.assertTrue(
            any("Scenario Timeline" in m.proto.body for m in app.get("html"))
        )
        self.assertTrue(any("Execution Trace" in m.value for m in app.markdown))
        self.assertTrue(any("처리 자원" in m.value for m in app.markdown))
        self.assertTrue(r.html and r.zip_bytes)
        labels = {button.label for button in app.get("download_button")}
        self.assertTrue({"HTML 보고서 다운로드", "ZIP 다운로드"} <= labels)
        technical = next(e for e in app.expander if e.label == "기술 상세 / 직접 조작")
        self.assertTrue(
            any(b.label == "상태 수집 시작" for b in technical.get("button"))
        )
        catalog = list(r.catalog)
        app.run()
        self.assertEqual(app.session_state.runtime.catalog, catalog)
        app.radio[0].set_value("비교 결과").run()
        self.assertFalse(app.exception)
        self.assertTrue(any(s.label == "기준 스냅샷" for s in app.selectbox))
        next(b for b in app.button if b.label == "선택 항목 비교").click().run()
        self.assertNotIn("scenario_runner", app.session_state)
        self.assertFalse(app.exception)

    def test_ui_scenarios_reset_results_and_keep_counts_separate(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        for label, key in (
            ("정상 작업 완료", "normal"),
            ("예상하지 못한 변화", "unexpected"),
            ("일부 정보 수집 실패", "failure"),
        ):
            old = app.session_state.runtime.root
            next(b for b in app.button if b.label == label).click().run()
            finish_autorun(app)
            self.assertFalse(app.exception)
            self.assertFalse(old.exists())
            r = app.session_state.runtime
            self.assertEqual(len(r.catalog), 2)
            self.assertEqual(app.session_state.scenario_runner.run.key, key)
            metrics = {m.label: m.value for m in app.metric}
            for technical, business in (
                ("Unchanged", "정상 유지"),
                ("Expected", "작업 계획과 일치"),
                ("Unexpected", "추가 확인 필요"),
                ("Unknown", "정보 부족으로 판단 불가"),
            ):
                self.assertEqual(metrics[business], str(counts(r)[technical]))
            messages = [m.value for m in (*app.success, *app.warning)]
            self.assertIn(conclusion(r), messages)
        r.close()


if __name__ == "__main__":
    unittest.main()


class GuidedFlowTests(unittest.TestCase):
    def test_navigation_keeps_execution_identity_and_results_on_rerun(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        next(
            b for b in app.button if b.label == "▶ 대표 네트워크 작업 검증 보기"
        ).click().run()
        finish_autorun(app)
        self.assertFalse(app.exception)
        token = app.session_state.guided_run_id
        runner = app.session_state.scenario_runner
        runtime = app.session_state.runtime
        html = next(
            h.proto.body for h in app.get("html") if 'id="guided-flow"' in h.proto.body
        )
        self.assertIn('data-phase="result"', html)
        self.assertIn('aria-label="실행 단계 선택"', html)
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(token, app.session_state.guided_run_id)
        self.assertIs(runner, app.session_state.scenario_runner)
        self.assertIs(runtime, app.session_state.runtime)
        next(
            b for b in app.button if b.label == "▶ 대표 네트워크 작업 검증 보기"
        ).click().run()
        finish_autorun(app)
        self.assertNotEqual(token, app.session_state.guided_run_id)
