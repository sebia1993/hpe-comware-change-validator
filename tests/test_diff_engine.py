from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backbone_state_tracker.core.analysis_rules import analysis_rules_from_mapping
from backbone_state_tracker.core.connectivity import DEVICE_CONNECTIVITY_COMMAND_ID, make_connectivity_result_for_device
from backbone_state_tracker.core.diff_engine import DiffEngine
from backbone_state_tracker.core.models import CommandResult, Device
from backbone_state_tracker.core.snapshot import SnapshotStore


class DiffEngineTests(unittest.TestCase):
    def _snapshot(
        self,
        root: Path,
        label: str,
        output: str,
        command_id: str = "interface_brief",
        category: str = "interface",
        stage_slug: str = "",
    ) -> Path:
        store = SnapshotStore(root)
        device = Device(name="backbone4", host="192.0.2.4")
        result = self._command_result(device, command_id=command_id, output=output, category=category)
        return store.write_snapshot(label, [device], {device.name: [result]}, stage_slug=stage_slug)

    def _command_result(
        self,
        device: Device,
        command_id: str = "interface_brief",
        output: str = "GE1/0/1 UP",
        category: str = "interface",
    ) -> CommandResult:
        return CommandResult(
            device_name=device.name,
            host=device.host,
            command_id=command_id,
            command="display interface brief",
            description="Interface summary",
            category=category,
            phase="check",
            success=True,
            output=output,
            started_at="2026-06-11T10:00:00",
            ended_at="2026-06-11T10:00:01",
        )

    def _diff_item(self, summary, command_id: str):
        return next(item for item in summary.items if item.command_id == command_id)

    def test_ignores_clock_like_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "Current time is 10:00:00\nGE1/0/1 UP")
            target = self._snapshot(root, "target", "Current time is 10:30:00\nGE1/0/1 UP")

            summary = DiffEngine().compare(base, target)

        self.assertEqual(summary.counts["Unchanged"], 2)
        self.assertEqual(summary.counts["Critical"], 0)

    def test_interface_down_is_critical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "GE1/0/1 UP\nGE1/0/2 UP")
            target = self._snapshot(root, "target", "GE1/0/1 DOWN\nGE1/0/2 UP")

            summary = DiffEngine().compare(base, target)

        changed = [item for item in summary.items if item.status == "changed"]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0].severity, "Critical")
        self.assertEqual(changed[0].finding_title, "인터페이스 Down 감지")
        self.assertEqual(changed[0].expectation, "unexpected")
        self.assertIn("이중화 경로", changed[0].impact_reason)

    def test_lacp_selected_count_decrease_is_critical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "Aggregation1 selected ports: 4", command_id="link_aggregation_summary")
            target = self._snapshot(root, "target", "Aggregation1 selected ports: 2", command_id="link_aggregation_summary")

            summary = DiffEngine().compare(base, target)

        changed = [item for item in summary.items if item.status == "changed"]
        self.assertEqual(changed[0].severity, "Critical")

    def test_hardware_major_alarm_is_critical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "No alarm", command_id="alarm_status", category="hardware")
            target = self._snapshot(root, "target", "Major alarm: power failure", command_id="alarm_status", category="hardware")

            summary = DiffEngine().compare(base, target)

        changed = [item for item in summary.items if item.status == "changed"]
        self.assertEqual(changed[0].severity, "Critical")

    def test_minor_alarm_in_log_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            device = Device(name="backbone4", host="192.0.2.4")
            store = SnapshotStore(root)
            base = store.write_snapshot(
                "base",
                [device],
                {device.name: [self._command_result(device, command_id="recent_log", output="No alarm", category="log")]},
            )
            target = store.write_snapshot(
                "target",
                [device],
                {device.name: [self._command_result(device, command_id="recent_log", output="Minor alarm: fan speed changed", category="log")]},
            )

            summary = DiffEngine().compare(base, target)

        changed = [item for item in summary.items if item.status == "changed"]
        self.assertEqual(changed[0].severity, "Warning")

    def test_vrrp_status_unchanged_output_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = "VRID 1 State Master Priority 110 VIP 10.0.0.1"
            base = self._snapshot(root, "base", output, command_id="vrrp_status", category="routing")
            target = self._snapshot(root, "target", output, command_id="vrrp_status", category="routing")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "vrrp_status")
        self.assertEqual(item.status, "unchanged")
        self.assertEqual(item.severity, "Unchanged")

    def test_vrrp_status_role_or_priority_change_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(
                root,
                "base",
                "VRID 1 State Master Priority 110 VIP 10.0.0.1",
                command_id="vrrp_status",
                category="routing",
            )
            target = self._snapshot(
                root,
                "target",
                "VRID 1 State Backup Priority 100 VIP 10.0.0.1",
                command_id="vrrp_status",
                category="routing",
            )

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "vrrp_status")
        self.assertEqual(item.status, "changed")
        self.assertEqual(item.severity, "Warning")
        self.assertEqual(item.summary, "Operational state changed.")

    def test_vrrp_status_down_state_is_critical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(
                root,
                "base",
                "VRID 1 State Master Priority 110 VIP 10.0.0.1",
                command_id="vrrp_status",
                category="routing",
            )
            target = self._snapshot(
                root,
                "target",
                "VRID 1 State down Priority 0 VIP 10.0.0.1",
                command_id="vrrp_status",
                category="routing",
            )

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "vrrp_status")
        self.assertEqual(item.status, "changed")
        self.assertEqual(item.severity, "Critical")
        self.assertEqual(item.summary, "Critical state keyword detected in changed output.")

    def test_cpu_usage_critical_even_when_output_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = "5 seconds: 70%\n1 minute: 20%\n5 minutes: 10%"
            base = self._snapshot(root, "base", output, command_id="cpu_usage", category="resource")
            target = self._snapshot(root, "target", output, command_id="cpu_usage", category="resource")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "cpu_usage")
        self.assertEqual(item.status, "changed")
        self.assertEqual(item.severity, "Critical")
        self.assertEqual(item.summary, "CPU usage is 70% or higher.")
        self.assertIn("current 5 seconds CPU usage 70%", item.change_preview)

    def test_cpu_usage_warning_threshold_boundaries(self) -> None:
        samples = [
            ("1 minute: 50%", "1 minute"),
            ("5 minutes: 69%", "5 minutes"),
        ]
        for output, label in samples:
            with self.subTest(output=output), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                base = self._snapshot(root, "base", "5 seconds: 10%\n1 minute: 10%\n5 minutes: 10%", command_id="cpu_usage", category="resource")
                target = self._snapshot(root, "target", output, command_id="cpu_usage", category="resource")

                summary = DiffEngine().compare(base, target)

            item = self._diff_item(summary, "cpu_usage")
            self.assertEqual(item.severity, "Warning")
            self.assertEqual(item.summary, "CPU usage is between 50% and 69%.")
            self.assertIn(f"current {label} CPU usage", item.change_preview)

    def test_cpu_usage_below_warning_is_info_even_when_output_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = "5 seconds: 49%\n1 minute: 49%\n5 minutes: 49%"
            base = self._snapshot(root, "base", output, command_id="cpu_usage", category="resource")
            target = self._snapshot(root, "target", output, command_id="cpu_usage", category="resource")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "cpu_usage")
        self.assertEqual(item.status, "changed")
        self.assertEqual(item.severity, "Info")
        self.assertEqual(item.summary, "CPU usage is below 50%.")
        self.assertIn("current 5 seconds CPU usage 49%", item.change_preview)

    def test_cpu_usage_normal_numeric_change_is_info_not_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "5 seconds: 10%\n1 minute: 10%\n5 minutes: 10%", command_id="cpu_usage", category="resource")
            target = self._snapshot(root, "target", "5 seconds: 49%\n1 minute: 20%\n5 minutes: 10%", command_id="cpu_usage", category="resource")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "cpu_usage")
        self.assertEqual(item.status, "changed")
        self.assertEqual(item.severity, "Info")
        self.assertEqual(item.summary, "CPU usage is below 50%.")

    def test_cpu_usage_critical_takes_priority_over_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "5 seconds: 10%\n1 minute: 10%\n5 minutes: 10%", command_id="cpu_usage", category="resource")
            target = self._snapshot(root, "target", "5 seconds: 49%\n1 minute: 69%\n5 minutes: 70%", command_id="cpu_usage", category="resource")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "cpu_usage")
        self.assertEqual(item.severity, "Critical")
        self.assertIn("current 5 minutes CPU usage 70%", item.change_preview)

    def test_cpu_usage_label_variants_are_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "5 sec: 10%\n1 min: 10%\n5minutes 10%", command_id="cpu_usage", category="resource")
            target = self._snapshot(root, "target", "5 sec = 51%\n1 min: 49%\n5minutes 49%", command_id="cpu_usage", category="resource")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "cpu_usage")
        self.assertEqual(item.severity, "Warning")
        self.assertIn("current 5 seconds CPU usage 51%", item.change_preview)

    def test_cpu_usage_value_before_label_is_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "10% in last 5 seconds", command_id="cpu_usage", category="resource")
            target = self._snapshot(root, "target", "72% in last 5 seconds", command_id="cpu_usage", category="resource")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "cpu_usage")
        self.assertEqual(item.severity, "Critical")
        self.assertEqual(item.summary, "CPU usage is 70% or higher.")

    def test_cpu_thresholds_are_loaded_from_analysis_rules(self) -> None:
        rules = analysis_rules_from_mapping({"thresholds": {"cpu_usage": {"warning_percent": 20, "critical_percent": 80}}})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "5 seconds: 10%", command_id="cpu_usage", category="resource")
            target = self._snapshot(root, "target", "5 seconds: 25%", command_id="cpu_usage", category="resource")

            summary = DiffEngine(rules=rules).compare(base, target)

        item = self._diff_item(summary, "cpu_usage")
        self.assertEqual(item.severity, "Warning")
        self.assertEqual(item.finding_title, "확인 필요")

    def test_memory_free_ratio_critical_even_when_output_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = "Memory statistics\nFreeRatio: 30%"
            base = self._snapshot(root, "base", output, command_id="memory_usage", category="resource")
            target = self._snapshot(root, "target", output, command_id="memory_usage", category="resource")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "memory_usage")
        self.assertEqual(item.status, "changed")
        self.assertEqual(item.severity, "Critical")
        self.assertEqual(item.summary, "Memory FreeRatio is 30% or lower.")
        self.assertIn("current FreeRatio 30%", item.change_preview)

    def test_memory_free_ratio_warning_threshold_boundaries(self) -> None:
        for value in (31, 40):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                base = self._snapshot(root, "base", "FreeRatio: 70%", command_id="memory_usage", category="resource")
                target = self._snapshot(root, "target", f"FreeRatio = {value}", command_id="memory_usage", category="resource")

                summary = DiffEngine().compare(base, target)

            item = self._diff_item(summary, "memory_usage")
            self.assertEqual(item.severity, "Warning")
            self.assertEqual(item.summary, "Memory FreeRatio is between 31% and 40%.")

    def test_memory_free_ratio_above_warning_is_info_even_when_output_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = "FreeRatio: 41%"
            base = self._snapshot(root, "base", output, command_id="memory_usage", category="resource")
            target = self._snapshot(root, "target", output, command_id="memory_usage", category="resource")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "memory_usage")
        self.assertEqual(item.status, "changed")
        self.assertEqual(item.severity, "Info")
        self.assertEqual(item.summary, "Memory FreeRatio is above 40%.")
        self.assertIn("current FreeRatio 41%", item.change_preview)

    def test_memory_free_ratio_normal_numeric_change_is_info_not_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "FreeRatio: 80%", command_id="memory_usage", category="resource")
            target = self._snapshot(root, "target", "FreeRatio: 41%", command_id="memory_usage", category="resource")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "memory_usage")
        self.assertEqual(item.status, "changed")
        self.assertEqual(item.severity, "Info")
        self.assertEqual(item.summary, "Memory FreeRatio is above 40%.")

    def test_unparsed_cpu_and_memory_changes_are_info_not_resource_warning(self) -> None:
        samples = [
            ("cpu_usage", "CPU output unavailable", "CPU output format changed"),
            ("memory_usage", "Memory output unavailable", "Memory output format changed"),
        ]
        for command_id, base_output, target_output in samples:
            with self.subTest(command_id=command_id), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                base = self._snapshot(root, "base", base_output, command_id=command_id, category="resource")
                target = self._snapshot(root, "target", target_output, command_id=command_id, category="resource")

                summary = DiffEngine().compare(base, target)

            item = self._diff_item(summary, command_id)
            self.assertEqual(item.status, "changed")
            self.assertEqual(item.severity, "Info")
            self.assertEqual(item.summary, "Output changed.")

    def test_memory_free_ratio_table_format_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(
                root,
                "base",
                "Slot Total Used Free FreeRatio\n1 1000 200 800 80%",
                command_id="memory_usage",
                category="resource",
            )
            target = self._snapshot(
                root,
                "target",
                "Slot Total Used Free FreeRatio\n1 1000 650 350 35%",
                command_id="memory_usage",
                category="resource",
            )

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "memory_usage")
        self.assertEqual(item.severity, "Warning")

    def test_memory_free_ratio_hpe_mem_prefixed_table_is_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(
                root,
                "base",
                (
                    "Memory statistics are measured in KB:\n"
                    "Slot 0:\n"
                    "            Total Used Free Shared Buffers Cached FreeRatio\n"
                    "Mem:        4035360 1291280 2744080 0 0 0 68%"
                ),
                command_id="memory_usage",
                category="resource",
            )
            target = self._snapshot(
                root,
                "target",
                (
                    "Memory statistics are measured in KB:\n"
                    "Slot 0:\n"
                    "            Total Used Free Shared Buffers Cached FreeRatio\n"
                    "Mem:        4035360 2622984 1412376 0 0 0 35%"
                ),
                command_id="memory_usage",
                category="resource",
            )

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "memory_usage")
        self.assertEqual(item.severity, "Warning")
        self.assertIn("current FreeRatio 35%", item.change_preview)

    def test_power_status_non_normal_state_is_critical(self) -> None:
        samples = [
            "State: Abnormal",
            "PowerID State Mode\n1 Absent AC",
            "Power 1 Fault",
        ]
        for output in samples:
            with self.subTest(output=output), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                base = self._snapshot(root, "base", "Power 1 Normal", command_id="power_status", category="hardware")
                target = self._snapshot(root, "target", output, command_id="power_status", category="hardware")

                summary = DiffEngine().compare(base, target)

            item = self._diff_item(summary, "power_status")
            self.assertEqual(item.status, "changed")
            self.assertEqual(item.severity, "Critical")
            self.assertEqual(item.summary, "Power State is not Normal.")

    def test_power_status_non_normal_state_is_critical_even_when_output_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = "Power 1 Absent"
            base = self._snapshot(root, "base", output, command_id="power_status", category="hardware")
            target = self._snapshot(root, "target", output, command_id="power_status", category="hardware")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "power_status")
        self.assertEqual(item.status, "changed")
        self.assertEqual(item.severity, "Critical")

    def test_power_status_all_normal_keeps_unchanged_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = "Power 1 Normal\nPower 2 Normal"
            base = self._snapshot(root, "base", output, command_id="power_status", category="hardware")
            target = self._snapshot(root, "target", output, command_id="power_status", category="hardware")

            summary = DiffEngine().compare(base, target)

        item = self._diff_item(summary, "power_status")
        self.assertEqual(item.status, "unchanged")
        self.assertEqual(item.severity, "Unchanged")

    def test_changed_lines_include_before_after_values_and_line_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "Header\nGE1/0/1 UP\nGE1/0/2 UP")
            target = self._snapshot(root, "target", "Header\nGE1/0/1 DOWN\nGE1/0/2 UP")

            summary = DiffEngine().compare(base, target)

        item = next(item for item in summary.items if item.status == "changed")
        change_lines = [line for line in item.changed_lines if line.kind != "context"]
        self.assertEqual(item.change_count, 1)
        self.assertEqual(change_lines[0].kind, "changed")
        self.assertEqual(change_lines[0].base_line_no, 2)
        self.assertEqual(change_lines[0].target_line_no, 2)
        self.assertEqual(change_lines[0].base_text, "GE1/0/1 UP")
        self.assertEqual(change_lines[0].target_text, "GE1/0/1 DOWN")
        self.assertIn("GE1/0/1 UP -> GE1/0/1 DOWN", item.change_preview)

    def test_added_and_removed_lines_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._snapshot(root, "base", "A\nC")
            target = self._snapshot(root, "target", "A\nB\nC")
            added = DiffEngine().compare(base, target)

            base_removed = self._snapshot(root, "base_removed", "A\nB\nC", command_id="interface_brief_removed")
            target_removed = self._snapshot(root, "target_removed", "A\nC", command_id="interface_brief_removed")
            removed = DiffEngine().compare(base_removed, target_removed)

        added_item = next(item for item in added.items if item.status == "changed")
        added_lines = [line for line in added_item.changed_lines if line.kind != "context"]
        self.assertEqual(added_lines[0].kind, "added")
        self.assertEqual(added_lines[0].target_line_no, 2)
        self.assertEqual(added_lines[0].target_text, "B")

        removed_item = next(item for item in removed.items if item.status == "changed")
        removed_lines = [line for line in removed_item.changed_lines if line.kind != "context"]
        self.assertEqual(removed_lines[0].kind, "removed")
        self.assertEqual(removed_lines[0].base_line_no, 2)
        self.assertEqual(removed_lines[0].base_text, "B")

    def test_unreachable_target_device_is_single_critical_connectivity_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = SnapshotStore(root)
            device = Device(name="backbone3", host="192.0.2.3")
            base = store.write_snapshot(
                "base",
                [device],
                {device.name: [self._command_result(device, output="GE1/0/1 UP")]},
            )
            target = store.write_snapshot(
                "target",
                [device],
                {
                    device.name: [
                        make_connectivity_result_for_device(
                            device_name=device.name,
                            host=device.host,
                            success=False,
                            reason="timeout",
                            started_at="2026-06-11T10:05:00",
                            ended_at="2026-06-11T10:05:00",
                        )
                    ]
                },
            )

            summary = DiffEngine().compare(base, target)

        connectivity = next(item for item in summary.items if item.command_id == DEVICE_CONNECTIVITY_COMMAND_ID)
        self.assertEqual(connectivity.severity, "Critical")
        self.assertEqual(connectivity.summary, "Target device connection failed.")
        self.assertEqual(connectivity.change_count, 1)
        self.assertEqual(connectivity.changed_lines[0].base_text, "reachable")
        self.assertEqual(connectivity.changed_lines[0].target_text, "unreachable: timeout (BST-CON-301)")
        self.assertEqual(connectivity.expectation, "unexpected")
        self.assertEqual(connectivity.finding_title, "장비 접속 실패")
        self.assertFalse(any(item.command_id == "interface_brief" and item.status == "removed" for item in summary.items))

    def test_expected_stage_change_marks_backbone3_off_connectivity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = SnapshotStore(root)
            device = Device(name="backbone3", host="192.0.2.3")
            base = store.write_snapshot(
                "base",
                [device],
                {device.name: [self._command_result(device, output="GE1/0/1 UP")]},
                stage_slug="pre_work",
            )
            target = store.write_snapshot(
                "target",
                [device],
                {
                    device.name: [
                        make_connectivity_result_for_device(
                            device_name=device.name,
                            host=device.host,
                            success=False,
                            reason="timeout",
                            started_at="2026-06-11T10:05:00",
                            ended_at="2026-06-11T10:05:00",
                        )
                    ]
                },
                stage_slug="bb3_off",
            )

            summary = DiffEngine().compare(base, target)

        connectivity = next(item for item in summary.items if item.command_id == DEVICE_CONNECTIVITY_COMMAND_ID)
        self.assertEqual(connectivity.severity, "Critical")
        self.assertEqual(connectivity.expectation, "expected")
        self.assertEqual(connectivity.finding_title, "백본3 OFF 단계의 접속 실패")
        self.assertIn("계획된 OFF 단계", connectivity.action_hint)

    def test_restored_target_device_is_info_without_added_command_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = SnapshotStore(root)
            device = Device(name="backbone3", host="192.0.2.3")
            base = store.write_snapshot(
                "base",
                [device],
                {
                    device.name: [
                        make_connectivity_result_for_device(
                            device_name=device.name,
                            host=device.host,
                            success=False,
                            reason="timeout",
                            started_at="2026-06-11T10:00:00",
                            ended_at="2026-06-11T10:00:00",
                        )
                    ]
                },
            )
            target = store.write_snapshot(
                "target",
                [device],
                {device.name: [self._command_result(device, output="GE1/0/1 UP")]},
            )

            summary = DiffEngine().compare(base, target)

        connectivity = next(item for item in summary.items if item.command_id == DEVICE_CONNECTIVITY_COMMAND_ID)
        self.assertEqual(connectivity.severity, "Info")
        self.assertEqual(connectivity.summary, "Target device connection restored.")
        self.assertEqual(connectivity.changed_lines[0].base_text, "unreachable: timeout (BST-CON-301)")
        self.assertEqual(connectivity.changed_lines[0].target_text, "reachable")
        self.assertFalse(any(item.command_id == "interface_brief" and item.status == "added" for item in summary.items))

    def test_still_unreachable_target_device_remains_critical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = SnapshotStore(root)
            device = Device(name="backbone3", host="192.0.2.3")
            failure = lambda: make_connectivity_result_for_device(
                device_name=device.name,
                host=device.host,
                success=False,
                reason="timeout",
                started_at="2026-06-11T10:00:00",
                ended_at="2026-06-11T10:00:00",
            )
            base = store.write_snapshot("base", [device], {device.name: [failure()]})
            target = store.write_snapshot("target", [device], {device.name: [failure()]})

            summary = DiffEngine().compare(base, target)

        connectivity = next(item for item in summary.items if item.command_id == DEVICE_CONNECTIVITY_COMMAND_ID)
        self.assertEqual(connectivity.severity, "Critical")
        self.assertEqual(connectivity.summary, "Target device connection failed.")
        self.assertEqual(connectivity.change_count, 1)


if __name__ == "__main__":
    unittest.main()
