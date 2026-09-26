"""Use production SnapshotStore, DiffEngine, expected-change rules and HTML writer."""

from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.analysis_rules import ExpectedChangeRule, load_analysis_rules
from core.diff_engine import DiffEngine
from core.models import CommandResult, Device
from core.snapshot import SnapshotStore
from core.reporter import ReportWriter

SCENARIOS = {
    "expected": "정상 변경 · VLAN / Description",
    "unexpected": "예상하지 못한 변경 · STP / VRRP",
    "critical": "Critical · Interface / LACP / OSPF / Resource",
    "no_change": "No Change",
    "collection_failed": "확인 불가 · OSPF 수집 실패",
}


def run_demo(scenario: str):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown demo scenario")
    data = json.loads(
        (ROOT / "portfolio_demo/demo_data/snapshots.json").read_text(encoding="utf-8")
    )
    device = Device(name="DEMO-SW", host="192.0.2.1")
    raw = {"Before": {}, "After": {}}
    batches = {}
    failed = []
    for stage in raw:
        results = []
        for command_id, (command, category, before) in data["commands"].items():
            output = (
                data["scenarios"][scenario].get(command_id, before)
                if stage == "After"
                else before
            )
            success = output is not None
            if not success:
                failed.append(command_id)
            raw[stage][command_id] = (
                output if success else "[CLI collection timeout · 확인 불가]"
            )
            results.append(
                CommandResult(
                    device_name=device.name,
                    host=device.host,
                    command_id=command_id,
                    command=command,
                    category=category,
                    success=success,
                    output=output or "",
                    error_message="Demo timeout" if not success else "",
                    started_at="2026-01-01T00:00:00",
                    ended_at="2026-01-01T00:00:01",
                )
            )
        batches[stage] = results
    rules = replace(
        load_analysis_rules(ROOT / "config/analysis_rules.yaml"),
        expected_changes=(
            ExpectedChangeRule(
                stage_slugs=("demo_post",),
                device_names=("DEMO-SW",),
                command_ids=("vlan", "interface_description"),
                title="계획된 VLAN / Description 변경",
            ),
        ),
    )
    with TemporaryDirectory(prefix="comware-demo-") as tmp:
        store = SnapshotStore(Path(tmp))
        before = store.write_snapshot(
            "[샘플] Pre-change",
            [device],
            {device.name: batches["Before"]},
            stage_slug="demo_pre",
        )
        after = store.write_snapshot(
            "[샘플] Post-change",
            [device],
            {device.name: batches["After"]},
            stage_slug="demo_post",
        )
        summary = DiffEngine(rules).compare(before, after)
        report_path = Path(tmp) / "report.html"
        ReportWriter._write_html(report_path, summary)
        html = report_path.read_text(encoding="utf-8")
        # The public export retains fixture results, never temporary server paths.
        html = (
            html.replace(str(before), "Pre-change")
            .replace(str(after), "Post-change")
            .replace(tmp, "Demo")
        )
    rows = []
    for item in summary.items:
        if item.command_id not in data["commands"]:
            continue
        rows.append(
            {
                "Item": item.command_id,
                "Before": raw["Before"][item.command_id],
                "After": raw["After"][item.command_id],
                "Difference": item.diff,
                "Classification": "Unknown"
                if item.command_id in failed
                else (
                    "Unchanged"
                    if raw["Before"][item.command_id] == raw["After"][item.command_id]
                    and item.severity not in {"Critical", "Warning"}
                    else (
                        "Expected" if item.expectation == "expected" else "Unexpected"
                    )
                ),
                "Severity": "Unknown" if item.command_id in failed else item.severity,
                "Reason": item.summary,
            }
        )
    counts = {
        label: sum(r["Classification"] == label for r in rows)
        for label in ["Expected", "Unexpected", "Unknown"]
    }
    counts["Critical"] = sum(r["Severity"] == "Critical" for r in rows)
    status = (
        "Unknown / Collection Error"
        if failed
        else (
            "Validation Failed"
            if counts["Unexpected"] or counts["Critical"]
            else "Validation Passed"
        )
    )
    return {
        "rows": rows,
        "raw": raw,
        "counts": counts,
        "status": status,
        "html": html,
        "expected_changes": [asdict(r) for r in rules.expected_changes],
    }
