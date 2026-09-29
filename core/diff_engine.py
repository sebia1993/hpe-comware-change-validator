from __future__ import annotations

import difflib
import re
from datetime import datetime
from pathlib import Path

from .analysis_rules import AnalysisRules, load_analysis_rules
from .connectivity import (
    DEVICE_CONNECTIVITY_COMMAND_ID,
    is_connectivity_result,
    is_legacy_connection_failure,
    legacy_failure_reason,
    make_connectivity_result_for_device,
)
from .models import CommandResult, DiffItem, DiffLine, DiffSummary, Snapshot
from .snapshot import SnapshotStore, read_text_lossless


VOLATILE_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"^\s*<[^>]+>\s*$"),
    re.compile(r"^\s*\[[^\]]+\]\s*$"),
    re.compile(r"\b(current\s+)?time\b", re.IGNORECASE),
    re.compile(r"\bclock\b", re.IGNORECASE),
    re.compile(r"\buptime\b", re.IGNORECASE),
    re.compile(r"\bup\s+time\b", re.IGNORECASE),
    re.compile(r"\bboot\b.*\btime\b", re.IGNORECASE),
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
    re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b"),
]

CRITICAL_PATTERNS = [
    re.compile(r"\bdown\b", re.IGNORECASE),
    re.compile(r"\bfail(?:ed|ure)?\b", re.IGNORECASE),
    re.compile(r"\bfault\b", re.IGNORECASE),
    re.compile(r"\babnormal\b", re.IGNORECASE),
    re.compile(r"\boffline\b", re.IGNORECASE),
    re.compile(r"\bmissing\b", re.IGNORECASE),
    re.compile(r"\babsent\b", re.IGNORECASE),
    re.compile(r"\bunselected\b", re.IGNORECASE),
    re.compile(r"\bnot\s+selected\b", re.IGNORECASE),
    re.compile(r"\binit\b|\bexstart\b|\bexchange\b|\bloading\b", re.IGNORECASE),
    re.compile(r"\bcritical\b", re.IGNORECASE),
    re.compile(r"\bmajor\b.*\balarm\b|\balarm\b.*\bmajor\b", re.IGNORECASE),
    re.compile(r"\bover\s+threshold\b", re.IGNORECASE),
]

WARNING_PATTERNS = [
    re.compile(r"\bwarn(?:ing)?\b", re.IGNORECASE),
    re.compile(r"\berror\b", re.IGNORECASE),
    re.compile(r"\bminor\b.*\balarm\b|\balarm\b.*\bminor\b|\balarm\b", re.IGNORECASE),
    re.compile(r"\bchange(?:d)?\b", re.IGNORECASE),
]
HEALTHY_ALERT_PATTERNS = [
    re.compile(r"\bno\s+alarm\b|\bno\s+fault\b|\bnone\b|\bnormal\b", re.IGNORECASE),
]

MAX_CHANGED_LINES = 500
CPU_CRITICAL_USAGE = 70.0
CPU_WARNING_USAGE = 50.0
MEMORY_CRITICAL_FREE_RATIO = 30.0
MEMORY_WARNING_FREE_RATIO = 40.0


class DiffEngine:
    def __init__(self, rules: AnalysisRules | None = None) -> None:
        self.rules = rules or load_analysis_rules()

    def compare(self, base_dir: Path, target_dir: Path) -> DiffSummary:
        base = SnapshotStore.load_snapshot(base_dir)
        target = SnapshotStore.load_snapshot(target_dir)
        base_results = self._index_results(self._results_with_connectivity(base))
        target_results = self._index_results(self._results_with_connectivity(target))
        base_unreachable_devices = self._unreachable_devices(base_results)
        target_unreachable_devices = self._unreachable_devices(target_results)
        keys = sorted(set(base_results) | set(target_results))
        items: list[DiffItem] = []

        for key in keys:
            device_name, command_id = key
            base_result = base_results.get(key)
            target_result = target_results.get(key)

            if self._should_suppress_missing_due_to_unreachable(
                device_name,
                command_id,
                base_result,
                target_result,
                base_unreachable_devices,
                target_unreachable_devices,
            ):
                continue

            if base_result and base_result.phase == "setup":
                continue
            if target_result and target_result.phase == "setup":
                continue

            if base_result is None or target_result is None:
                self._append_item(items, self._missing_item(base_dir, target_dir, key, base_result, target_result), target.stage_slug)
                continue

            if command_id == DEVICE_CONNECTIVITY_COMMAND_ID:
                self._append_item(items, self._connectivity_item(base_dir, target_dir, base_result, target_result), target.stage_slug)
                continue

            base_text = self._read_result_output(base_dir, base_result)
            target_text = self._read_result_output(target_dir, target_result)
            base_lines = normalize_output_lines(base_text, command_id=base_result.command_id)
            target_lines = normalize_output_lines(target_text, command_id=target_result.command_id)
            base_normalized = "\n".join(line for _, line in base_lines).strip()
            target_normalized = "\n".join(line for _, line in target_lines).strip()
            health = assess_target_health(target_result, target_lines, self.rules)

            if base_normalized == target_normalized and base_result.success == target_result.success:
                if health is not None:
                    severity, summary, health_line = health
                    change_count, changed_lines, change_preview = summarize_changed_lines([health_line])
                    self._append_item(
                        items,
                        DiffItem(
                            device_name=target_result.device_name,
                            command_id=target_result.command_id,
                            command=target_result.command,
                            category=target_result.category,
                            severity=severity,
                            status="changed",
                            summary=summary,
                            base_raw_file=base_result.raw_file,
                            target_raw_file=target_result.raw_file,
                            changed_lines=changed_lines,
                            change_count=change_count,
                            change_preview=change_preview,
                        ),
                        target.stage_slug,
                    )
                    continue
                self._append_item(
                    items,
                    DiffItem(
                        device_name=target_result.device_name,
                        command_id=target_result.command_id,
                        command=target_result.command,
                        category=target_result.category,
                        severity="Unchanged",
                        status="unchanged",
                        summary="No meaningful change detected.",
                        base_raw_file=base_result.raw_file,
                        target_raw_file=target_result.raw_file,
                    ),
                    target.stage_slug,
                )
                continue

            diff_text = "\n".join(
                difflib.unified_diff(
                    base_normalized.splitlines(),
                    target_normalized.splitlines(),
                    fromfile=f"base/{base_result.device_name}/{base_result.command_id}",
                    tofile=f"target/{target_result.device_name}/{target_result.command_id}",
                    lineterm="",
                )
            )
            added_lines = [line[1:] for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")]
            health_line = None
            if health is not None:
                severity, summary, health_line = health
            else:
                severity, summary = classify_change(target_result, added_lines, diff_text)
            changed_lines = build_changed_lines(base_lines, target_lines)
            if health_line is not None:
                changed_lines = [health_line] + changed_lines
            change_count, changed_lines, change_preview = summarize_changed_lines(changed_lines)
            self._append_item(
                items,
                DiffItem(
                    device_name=target_result.device_name,
                    command_id=target_result.command_id,
                    command=target_result.command,
                    category=target_result.category,
                    severity=severity,
                    status="changed",
                    summary=summary,
                    diff=diff_text,
                    base_raw_file=base_result.raw_file,
                    target_raw_file=target_result.raw_file,
                    changed_lines=changed_lines,
                    change_count=change_count,
                    change_preview=change_preview,
                ),
                target.stage_slug,
            )

        return DiffSummary(
            base_snapshot=str(base_dir),
            target_snapshot=str(target_dir),
            generated_at=datetime.now().isoformat(timespec="seconds"),
            items=items,
        )

    def _append_item(self, items: list[DiffItem], item: DiffItem, target_stage_slug: str) -> None:
        items.append(self._enrich_item(item, target_stage_slug))

    def _enrich_item(self, item: DiffItem, target_stage_slug: str) -> DiffItem:
        finding_key = infer_finding_key(item)
        finding = self.rules.finding(finding_key)
        expected_change = self.rules.expected_change(
            stage_slug=target_stage_slug,
            device_name=item.device_name,
            command_id=item.command_id,
            summary=item.summary,
        )
        item.finding_title = expected_change.title if expected_change and expected_change.title else finding.title
        item.impact_reason = finding.impact_reason
        item.evidence = item.change_preview or item.summary
        item.action_hint = expected_change.action_hint if expected_change and expected_change.action_hint else finding.action_hint
        item.expectation = classify_expectation(item, expected_change is not None)
        item.priority = finding.priority
        return item

    @staticmethod
    def _index_results(results: list[CommandResult]) -> dict[tuple[str, str], CommandResult]:
        return {(result.device_name, result.command_id): result for result in results}

    @staticmethod
    def _read_result_output(snapshot_dir: Path, result: CommandResult) -> str:
        if not result.raw_file:
            return result.output
        raw_path = snapshot_dir / result.raw_file
        if not raw_path.exists():
            return result.output
        return read_text_lossless(raw_path)

    def _results_with_connectivity(self, snapshot: Snapshot) -> list[CommandResult]:
        results = [result for result in snapshot.results if not is_legacy_connection_failure(result)]
        devices = self._enabled_device_map(snapshot)
        existing_connectivity = {result.device_name for result in results if is_connectivity_result(result)}

        for device_name, host in devices.items():
            if device_name in existing_connectivity:
                continue

            legacy_failure = next(
                (
                    result
                    for result in snapshot.results
                    if result.device_name == device_name and is_legacy_connection_failure(result)
                ),
                None,
            )
            if legacy_failure is not None:
                results.append(
                    make_connectivity_result_for_device(
                        device_name=device_name,
                        host=legacy_failure.host or host,
                        success=False,
                        reason=legacy_failure_reason(legacy_failure),
                        error_message=legacy_failure.error_message,
                        started_at=legacy_failure.started_at,
                        ended_at=legacy_failure.ended_at,
                    )
                )
                continue

            reachable_result = next(
                (
                    result
                    for result in snapshot.results
                    if result.device_name == device_name and self._is_reachable_command_result(result)
                ),
                None,
            )
            if reachable_result is not None:
                results.append(
                    make_connectivity_result_for_device(
                        device_name=device_name,
                        host=reachable_result.host or host,
                        success=True,
                        started_at=reachable_result.started_at,
                        ended_at=reachable_result.ended_at,
                    )
                )

        return results

    @staticmethod
    def _enabled_device_map(snapshot: Snapshot) -> dict[str, str]:
        devices: dict[str, str] = {}
        for payload in snapshot.devices:
            if not bool(payload.get("enabled", True)):
                continue
            name = str(payload.get("name") or payload.get("host") or "").strip()
            if name:
                devices[name] = str(payload.get("host") or "").strip()

        for result in snapshot.results:
            if result.device_name and result.device_name not in devices:
                devices[result.device_name] = result.host
        return devices

    @staticmethod
    def _is_reachable_command_result(result: CommandResult) -> bool:
        return (
            result.phase != "setup"
            and not is_connectivity_result(result)
            and not is_legacy_connection_failure(result)
        )

    @staticmethod
    def _unreachable_devices(results: dict[tuple[str, str], CommandResult]) -> set[str]:
        return {
            device_name
            for (device_name, command_id), result in results.items()
            if command_id == DEVICE_CONNECTIVITY_COMMAND_ID and not result.success
        }

    @staticmethod
    def _should_suppress_missing_due_to_unreachable(
        device_name: str,
        command_id: str,
        base_result: CommandResult | None,
        target_result: CommandResult | None,
        base_unreachable_devices: set[str],
        target_unreachable_devices: set[str],
    ) -> bool:
        if command_id == DEVICE_CONNECTIVITY_COMMAND_ID:
            return False
        if target_result is None and device_name in target_unreachable_devices:
            return True
        if base_result is None and device_name in base_unreachable_devices:
            return True
        return False

    def _connectivity_item(
        self,
        base_dir: Path,
        target_dir: Path,
        base_result: CommandResult,
        target_result: CommandResult,
    ) -> DiffItem:
        base_text = self._read_result_output(base_dir, base_result)
        target_text = self._read_result_output(target_dir, target_result)
        base_lines = normalize_output_lines(base_text, command_id=base_result.command_id)
        target_lines = normalize_output_lines(target_text, command_id=target_result.command_id)
        base_normalized = "\n".join(line for _, line in base_lines).strip()
        target_normalized = "\n".join(line for _, line in target_lines).strip()

        if base_result.success and target_result.success and base_normalized == target_normalized:
            return DiffItem(
                device_name=target_result.device_name,
                command_id=target_result.command_id,
                command=target_result.command,
                category=target_result.category,
                severity="Unchanged",
                status="unchanged",
                summary="No meaningful change detected.",
                base_raw_file=base_result.raw_file,
                target_raw_file=target_result.raw_file,
            )

        diff_text = "\n".join(
            difflib.unified_diff(
                base_normalized.splitlines(),
                target_normalized.splitlines(),
                fromfile=f"base/{base_result.device_name}/{base_result.command_id}",
                tofile=f"target/{target_result.device_name}/{target_result.command_id}",
                lineterm="",
            )
        )
        changed_lines = build_changed_lines(base_lines, target_lines)
        if not changed_lines:
            changed_lines = [
                DiffLine(
                    kind="changed",
                    base_line_no=1,
                    target_line_no=1,
                    base_text=base_normalized or "-",
                    target_text=target_normalized or "-",
                )
            ]
        change_count, changed_lines, change_preview = summarize_changed_lines(changed_lines)
        severity, summary = classify_connectivity_change(base_result, target_result)
        return DiffItem(
            device_name=target_result.device_name,
            command_id=target_result.command_id,
            command=target_result.command,
            category=target_result.category,
            severity=severity,
            status="changed",
            summary=summary,
            diff=diff_text,
            base_raw_file=base_result.raw_file,
            target_raw_file=target_result.raw_file,
            changed_lines=changed_lines,
            change_count=change_count,
            change_preview=change_preview,
        )

    def _missing_item(
        self,
        base_dir: Path,
        target_dir: Path,
        key: tuple[str, str],
        base_result: CommandResult | None,
        target_result: CommandResult | None,
    ) -> DiffItem:
        result = target_result or base_result
        device_name, command_id = key
        status = "added" if base_result is None else "removed"
        raw_file = result.raw_file if result else ""
        changed_lines: list[DiffLine] = []
        if target_result is not None:
            output = self._read_result_output(target_dir, target_result)
            changed_lines = [
                DiffLine(kind="added", target_line_no=line_no, target_text=line)
                for line_no, line in normalize_output_lines(output, command_id=target_result.command_id)
            ]
        elif base_result is not None:
            output = self._read_result_output(base_dir, base_result)
            changed_lines = [
                DiffLine(kind="removed", base_line_no=line_no, base_text=line)
                for line_no, line in normalize_output_lines(output, command_id=base_result.command_id)
            ]
        change_count, changed_lines, change_preview = summarize_changed_lines(changed_lines)
        return DiffItem(
            device_name=device_name,
            command_id=command_id,
            command=result.command if result else "",
            category=result.category if result else "unknown",
            severity="Warning",
            status=status,
            summary=f"Command result was {status} between snapshots.",
            base_raw_file=raw_file if base_result else "",
            target_raw_file=raw_file if target_result else "",
            changed_lines=changed_lines,
            change_count=change_count,
            change_preview=change_preview,
        )


def classify_expectation(item: DiffItem, expected_match: bool) -> str:
    if expected_match:
        return "expected"
    if item.severity in {"Critical", "Warning"}:
        return "unexpected"
    return "unknown"


def infer_finding_key(item: DiffItem) -> str:
    summary = item.summary
    command_id = item.command_id
    category = item.category

    if command_id == DEVICE_CONNECTIVITY_COMMAND_ID:
        if summary == "Target device connection failed.":
            return "connection_failed"
        if summary == "Target device connection restored.":
            return "connection_restored"
    if summary == "Target snapshot command failed.":
        return "command_failed"

    if command_id == "cpu_usage":
        if item.severity == "Critical":
            return "cpu_critical"
        if item.severity == "Warning":
            return "cpu_warning"
        return "cpu_info"
    if command_id == "memory_usage":
        if item.severity == "Critical":
            return "memory_critical"
        if item.severity == "Warning":
            return "memory_warning"
        return "memory_info"
    if command_id == "power_status" or summary == "Power State is not Normal.":
        return "power_non_normal" if item.severity != "Unchanged" else "unchanged"

    if item.status in {"added", "removed"}:
        return "command_added_removed"
    if item.severity == "Unchanged":
        return "unchanged"

    if command_id == "interface_brief" and item.severity == "Critical":
        return "interface_down"
    if command_id.startswith("link_aggregation") and item.severity == "Critical":
        return "lacp_selected_decrease"
    if command_id == "ospf_peer" and item.severity == "Critical":
        return "ospf_peer_not_full"
    if command_id == "vrrp_status":
        return "vrrp_down" if item.severity == "Critical" else "vrrp_role_change"
    if command_id == "recent_log":
        return "log_critical" if item.severity == "Critical" else "log_warning"
    if category == "hardware" and item.severity in {"Critical", "Warning"}:
        return "hardware_critical" if item.severity == "Critical" else "hardware_warning"
    if summary == "Operational state changed.":
        return "operational_change"
    if summary == "Output changed.":
        return "output_changed"
    if summary == "New critical-looking log line detected.":
        return "log_critical"
    if summary == "Warning keyword detected in changed output.":
        return "log_warning" if category == "log" else "operational_change"
    if summary == "Hardware warning or alarm keyword detected in changed output.":
        return "hardware_warning"
    if summary == "Critical state keyword detected in changed output.":
        return "hardware_critical" if category == "hardware" else "operational_change"
    return "output_changed"


def normalize_output(text: str, command_id: str = "") -> str:
    return "\n".join(line for _, line in normalize_output_lines(text, command_id=command_id)).strip()


def normalize_output_lines(text: str, command_id: str = "") -> list[tuple[int, str]]:
    if command_id == "system_clock":
        return []
    normalized_lines: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        stripped = line.rstrip()
        if should_ignore_line(stripped):
            continue
        normalized_lines.append((line_no, stripped))
    return normalized_lines


def should_ignore_line(line: str) -> bool:
    return any(pattern.search(line) for pattern in VOLATILE_PATTERNS)


def build_changed_lines(
    base_lines: list[tuple[int, str]],
    target_lines: list[tuple[int, str]],
    context: int = 1,
) -> list[DiffLine]:
    base_values = [line for _, line in base_lines]
    target_values = [line for _, line in target_lines]
    matcher = difflib.SequenceMatcher(None, base_values, target_values, autojunk=False)
    details: list[DiffLine] = []
    seen: set[tuple[str, int | None, int | None, str, str]] = set()

    def add_line(line: DiffLine) -> None:
        key = (line.kind, line.base_line_no, line.target_line_no, line.base_text, line.target_text)
        if key in seen:
            return
        seen.add(key)
        details.append(line)

    def add_context(base_index: int, target_index: int) -> None:
        if base_index < 0 or target_index < 0:
            return
        if base_index >= len(base_lines) or target_index >= len(target_lines):
            return
        base_line_no, base_text = base_lines[base_index]
        target_line_no, target_text = target_lines[target_index]
        add_line(
            DiffLine(
                kind="context",
                base_line_no=base_line_no,
                target_line_no=target_line_no,
                base_text=base_text,
                target_text=target_text,
            )
        )

    for tag, base_start, base_end, target_start, target_end in matcher.get_opcodes():
        if tag == "equal":
            continue

        for offset in range(context, 0, -1):
            add_context(base_start - offset, target_start - offset)

        if tag == "replace":
            base_count = base_end - base_start
            target_count = target_end - target_start
            for offset in range(max(base_count, target_count)):
                base_line = base_lines[base_start + offset] if offset < base_count else None
                target_line = target_lines[target_start + offset] if offset < target_count else None
                if base_line is not None and target_line is not None:
                    add_line(
                        DiffLine(
                            kind="changed",
                            base_line_no=base_line[0],
                            target_line_no=target_line[0],
                            base_text=base_line[1],
                            target_text=target_line[1],
                        )
                    )
                elif base_line is not None:
                    add_line(DiffLine(kind="removed", base_line_no=base_line[0], base_text=base_line[1]))
                elif target_line is not None:
                    add_line(DiffLine(kind="added", target_line_no=target_line[0], target_text=target_line[1]))
        elif tag == "delete":
            for base_index in range(base_start, base_end):
                line_no, line = base_lines[base_index]
                add_line(DiffLine(kind="removed", base_line_no=line_no, base_text=line))
        elif tag == "insert":
            for target_index in range(target_start, target_end):
                line_no, line = target_lines[target_index]
                add_line(DiffLine(kind="added", target_line_no=line_no, target_text=line))

        for offset in range(context):
            add_context(base_end + offset, target_end + offset)

    return details


def summarize_changed_lines(lines: list[DiffLine]) -> tuple[int, list[DiffLine], str]:
    change_lines = [line for line in lines if line.kind != "context"]
    preview = ""
    if change_lines:
        preview = format_diff_line_preview(change_lines[0])
    return len(change_lines), lines[:MAX_CHANGED_LINES], preview


def format_diff_line_preview(line: DiffLine) -> str:
    if line.kind == "changed":
        return f"{line.base_text} -> {line.target_text}"
    if line.kind == "added":
        return f"추가: {line.target_text}"
    if line.kind == "removed":
        return f"삭제: {line.base_text}"
    return line.target_text or line.base_text


def classify_connectivity_change(base_result: CommandResult, target_result: CommandResult) -> tuple[str, str]:
    if not target_result.success:
        return "Critical", "Target device connection failed."
    if not base_result.success and target_result.success:
        return "Info", "Target device connection restored."
    return "Info", "Output changed."


def assess_target_health(
    result: CommandResult,
    target_lines: list[tuple[int, str]],
    rules: AnalysisRules | None = None,
) -> tuple[str, str, DiffLine] | None:
    if not result.success:
        message = result.error_message or "command failed"
        return (
            "Critical",
            "Target snapshot command failed.",
            DiffLine(
                kind="changed",
                target_line_no=1,
                base_text="expected command success",
                target_text=f"command failed: {message}",
            ),
        )

    if result.command_id == "cpu_usage":
        return assess_cpu_usage(target_lines, rules)
    if result.command_id == "memory_usage":
        return assess_memory_free_ratio(target_lines, rules)
    if result.command_id == "power_status":
        return assess_power_state(target_lines)
    return None


def assess_cpu_usage(target_lines: list[tuple[int, str]], rules: AnalysisRules | None = None) -> tuple[str, str, DiffLine] | None:
    values = find_cpu_usage_values(target_lines)
    if not values:
        return None
    thresholds = rules or AnalysisRules()
    critical_usage = thresholds.threshold("cpu_usage", "critical_percent", CPU_CRITICAL_USAGE)
    warning_usage = thresholds.threshold("cpu_usage", "warning_percent", CPU_WARNING_USAGE)

    critical = max((value for value in values if value[2] >= critical_usage), key=lambda value: value[2], default=None)
    if critical is not None:
        line_no, label, usage, source = critical
        display_value = format_threshold_number(usage)
        return (
            "Critical",
            "CPU usage is 70% or higher.",
            DiffLine(
                kind="changed",
                target_line_no=line_no,
                base_text="expected CPU usage < 50%",
                target_text=f"current {label} CPU usage {display_value}% ({source})",
            ),
        )

    warning = max((value for value in values if value[2] >= warning_usage), key=lambda value: value[2], default=None)
    if warning is not None:
        line_no, label, usage, source = warning
        display_value = format_threshold_number(usage)
        return (
            "Warning",
            "CPU usage is between 50% and 69%.",
            DiffLine(
                kind="changed",
                target_line_no=line_no,
                base_text="expected CPU usage < 50%",
                target_text=f"current {label} CPU usage {display_value}% ({source})",
            ),
        )
    line_no, label, usage, source = max(values, key=lambda value: value[2])
    display_value = format_threshold_number(usage)
    return (
        "Info",
        "CPU usage is below 50%.",
        DiffLine(
            kind="changed",
            target_line_no=line_no,
            base_text="expected CPU usage < 50%",
            target_text=f"current {label} CPU usage {display_value}% ({source})",
        ),
    )


def assess_memory_free_ratio(target_lines: list[tuple[int, str]], rules: AnalysisRules | None = None) -> tuple[str, str, DiffLine] | None:
    parsed = find_memory_free_ratio(target_lines)
    if parsed is None:
        return None

    line_no, value, source = parsed
    display_value = format_threshold_number(value)
    thresholds = rules or AnalysisRules()
    critical_free_ratio = thresholds.threshold("memory_free_ratio", "critical_percent", MEMORY_CRITICAL_FREE_RATIO)
    warning_free_ratio = thresholds.threshold("memory_free_ratio", "warning_percent", MEMORY_WARNING_FREE_RATIO)
    if value <= critical_free_ratio:
        return (
            "Critical",
            "Memory FreeRatio is 30% or lower.",
            DiffLine(
                kind="changed",
                target_line_no=line_no,
                base_text="expected FreeRatio > 40%",
                target_text=f"current FreeRatio {display_value}% ({source})",
            ),
        )
    if value <= warning_free_ratio:
        return (
            "Warning",
            "Memory FreeRatio is between 31% and 40%.",
            DiffLine(
                kind="changed",
                target_line_no=line_no,
                base_text="expected FreeRatio > 40%",
                target_text=f"current FreeRatio {display_value}% ({source})",
            ),
        )
    return (
        "Info",
        "Memory FreeRatio is above 40%.",
        DiffLine(
            kind="changed",
            target_line_no=line_no,
            base_text="expected FreeRatio > 40%",
            target_text=f"current FreeRatio {display_value}% ({source})",
        ),
    )


def assess_power_state(target_lines: list[tuple[int, str]]) -> tuple[str, str, DiffLine] | None:
    states = find_power_states(target_lines)
    for line_no, state, source in states:
        if state.lower() != "normal":
            return (
                "Critical",
                "Power State is not Normal.",
                DiffLine(
                    kind="changed",
                    target_line_no=line_no,
                    base_text="expected State: Normal",
                    target_text=f"current State: {state} ({source})",
                ),
            )
    return None


def classify_change(result: CommandResult, added_lines: list[str], diff_text: str) -> tuple[str, str]:
    if not result.success:
        return "Critical", "Target snapshot command failed."
    if result.command_id in {"cpu_usage", "memory_usage"}:
        return "Info", "Output changed."

    target_lines = added_lines or target_lines_from_diff(diff_text)
    base_lines = base_lines_from_diff(diff_text)
    haystack = alert_haystack(target_lines) or alert_haystack(diff_text.splitlines())
    critical_categories = {"interface", "routing", "hardware", "connection"}
    if result.category in critical_categories and any(pattern.search(haystack) for pattern in CRITICAL_PATTERNS):
        return "Critical", "Critical state keyword detected in changed output."

    if result.category == "hardware" and any(pattern.search(haystack) for pattern in WARNING_PATTERNS):
        return "Warning", "Hardware warning or alarm keyword detected in changed output."

    if result.category == "log" and any(pattern.search(haystack) for pattern in CRITICAL_PATTERNS):
        return "Critical", "New critical-looking log line detected."

    if result.category == "interface" and selected_count_decreased(base_lines, target_lines):
        return "Critical", "Critical state keyword detected in changed output."

    if result.category in {"log", "routing", "resource", "switching"}:
        if any(pattern.search(haystack) for pattern in WARNING_PATTERNS):
            return "Warning", "Warning keyword detected in changed output."
        return "Warning", "Operational state changed."

    return "Info", "Output changed."


def alert_haystack(lines: list[str]) -> str:
    relevant = [line for line in lines if not any(pattern.search(line) for pattern in HEALTHY_ALERT_PATTERNS)]
    return "\n".join(relevant)


def target_lines_from_diff(diff_text: str) -> list[str]:
    return [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def base_lines_from_diff(diff_text: str) -> list[str]:
    return [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]


def selected_count_decreased(base_lines: list[str], target_lines: list[str]) -> bool:
    base_count = max(selected_counts(base_lines), default=None)
    target_count = max(selected_counts(target_lines), default=None)
    return base_count is not None and target_count is not None and target_count < base_count


def selected_counts(lines: list[str]) -> list[int]:
    counts: list[int] = []
    for line in lines:
        if not re.search(r"\bselected\b", line, re.IGNORECASE):
            continue
        for pattern in (
            re.compile(r"\bselected\b\D{0,20}(\d+)", re.IGNORECASE),
            re.compile(r"(\d+)\D{0,20}\bselected\b", re.IGNORECASE),
        ):
            counts.extend(int(match.group(1)) for match in pattern.finditer(line))
    return counts


def find_cpu_usage_values(lines: list[tuple[int, str]]) -> list[tuple[int, str, float, str]]:
    values: list[tuple[int, str, float, str]] = []
    seen: set[tuple[int, str]] = set()
    patterns = [
        ("5 seconds", re.compile(r"\b5\s*(?:seconds?|secs?)\b", re.IGNORECASE)),
        ("1 minute", re.compile(r"\b1\s*(?:minutes?|mins?)\b", re.IGNORECASE)),
        ("5 minutes", re.compile(r"\b5\s*(?:minutes?|mins?)\b|\b5minutes\b", re.IGNORECASE)),
    ]
    for line_no, line in lines:
        for label, pattern in patterns:
            for match in pattern.finditer(line):
                usage = cpu_usage_near_label(line, match.start(), match.end())
                if usage is None:
                    continue
                key = (line_no, label)
                if key in seen:
                    continue
                seen.add(key)
                values.append((line_no, label, usage, line))
    return values


def cpu_usage_near_label(line: str, start: int, end: int) -> float | None:
    after = line[end : min(len(line), end + 80)]
    after_match = re.search(r"\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*%", after)
    if after_match:
        return float(after_match.group(1))

    before = line[max(0, start - 80) : start]
    before_matches = list(re.finditer(r"([0-9]+(?:\.[0-9]+)?)\s*%", before))
    if before_matches:
        return float(before_matches[-1].group(1))
    return None


def find_memory_free_ratio(lines: list[tuple[int, str]]) -> tuple[int, float, str] | None:
    for line_no, line in lines:
        direct = re.search(r"\bfree\s*ratio\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", line, re.IGNORECASE)
        if direct:
            return line_no, float(direct.group(1)), line

        same_line = re.search(r"\bfree\s*ratio\b.*?([0-9]+(?:\.[0-9]+)?)\s*%?", line, re.IGNORECASE)
        if same_line:
            return line_no, float(same_line.group(1)), line

    header_index: int | None = None
    header_width: int | None = None
    for line_no, line in lines:
        tokens = split_status_tokens(line)
        if not tokens:
            continue
        if header_index is None:
            header_index = next(
                (
                    index
                    for index, token in enumerate(tokens)
                    if normalized_header_token(token) == "freeratio"
                ),
                None,
            )
            if header_index is not None:
                header_width = len(tokens)
            continue
        if is_separator_line(line):
            continue
        if header_width is None:
            continue
        # Some Comware platforms prefix the data row with "Mem:" while the
        # header starts directly at Total/Used/Free/.../FreeRatio. Shift the
        # target column by the row/header width difference instead of treating
        # Cached as FreeRatio.
        data_index = header_index + max(0, len(tokens) - header_width)
        if len(tokens) > data_index:
            value = parse_numeric_token(tokens[data_index])
            if value is not None:
                return line_no, value, line
    return None


def find_power_states(lines: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    states: list[tuple[int, str, str]] = []
    state_column: int | None = None

    for line_no, line in lines:
        direct = re.search(r"\bstate\b\s*[:=]\s*(.+?)\s*$", line, re.IGNORECASE)
        if direct:
            state = clean_state_value(direct.group(1))
            if state:
                states.append((line_no, state, line))
            continue

        tokens = split_status_tokens(line)
        if not tokens:
            continue
        if state_column is None:
            state_column = next((index for index, token in enumerate(tokens) if normalized_header_token(token) == "state"), None)
            if state_column is not None:
                continue
        if (
            state_column is not None
            and not is_separator_line(line)
            and len(tokens) > state_column
            and is_likely_power_data_row(tokens)
        ):
            state = clean_state_value(tokens[state_column])
            if state:
                states.append((line_no, state, line))
            continue

        simple = re.search(r"^\s*(?:Power|PSU|PWR)\s+\d+\b.*?([A-Za-z][A-Za-z0-9_/-]*)\s*$", line, re.IGNORECASE)
        if simple:
            state = clean_state_value(simple.group(1))
            if state:
                states.append((line_no, state, line))
            continue

        colon = re.search(r"^\s*(?:Power|PSU|PWR)\b.*:\s*(.+?)\s*$", line, re.IGNORECASE)
        if colon:
            state = clean_state_value(colon.group(1))
            if state:
                states.append((line_no, state, line))

    return states


def split_status_tokens(line: str) -> list[str]:
    return [token for token in re.split(r"\s+", line.strip()) if token]


def normalized_header_token(token: str) -> str:
    return re.sub(r"[^A-Za-z]", "", token).lower()


def parse_numeric_token(token: str) -> float | None:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%?", token)
    return float(match.group(1)) if match else None


def clean_state_value(value: str) -> str:
    return value.strip().strip(".,;|")


def is_separator_line(line: str) -> bool:
    return bool(re.fullmatch(r"[\s\-+=|:]+", line))


def is_likely_power_data_row(tokens: list[str]) -> bool:
    if not tokens:
        return False
    first = tokens[0].lower()
    return first.startswith(("power", "psu", "pwr")) or any(char.isdigit() for char in first)


def format_threshold_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"
