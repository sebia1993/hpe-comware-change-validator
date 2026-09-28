"""Bounded per-browser SnapshotStore workspace with production comparisons."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
from datetime import datetime
from html import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.analysis_rules import ExpectedChangeRule, load_analysis_rules
from core.diff_engine import DiffEngine
from core.preflight import validate_preflight
from core.snapshot import SnapshotStore
from core.reporter import ReportWriter
from core.report_bundle import create_share_report_bundle
from core.workflow import (
    PRE_WORK_STAGE,
    WORK_STAGE_NAMES,
    resolve_stage,
    find_latest_pre_work_snapshot,
)
from portfolio_demo.fixture_collector import DEVICES, COMMANDS, collect


from portfolio_demo.execution_trace import ExecutionTrace, traced


class DemoRuntime:
    def __init__(self):
        self.execution = ExecutionTrace()
        self.temp = TemporaryDirectory(prefix="comware-demo-v2-")
        self.root = Path(self.temp.name)
        self.store = SnapshotStore(self.root / "snapshots")
        self.catalog = []
        self.logs = []
        self.baseline = None
        self.pair = None
        self.summary = None
        self.rows = []
        self.html = ""
        self.zip_bytes = b""
        self.options = (False, False)
        self.preflight = None

    def close(self):
        self.temp.cleanup()

    def log(self, event, detail):
        self.logs.append(
            {
                "Time": datetime.now().isoformat(timespec="seconds"),
                "Event": event,
                "Detail": detail,
            }
        )
        self.logs = self.logs[-200:]

    @traced("설정 점검")
    def check(self):
        with self.execution.step(
            "preflight", "Preflight · 읽기 전용 명령 검증"
        ) as step:
            self.preflight = validate_preflight(DEVICES, COMMANDS)
            step.status = (
                "failure"
                if self.preflight.has_errors
                else ("warning" if self.preflight.warning_count else "success")
            )
            step.detail = f"대상 {len(DEVICES)}대 · 명령 {len(COMMANDS)}종 · Error {self.preflight.error_count} / Warning {self.preflight.warning_count}"
            step.evidence = {
                "devices": len(DEVICES),
                "commands": len(COMMANDS),
                "errors": self.preflight.error_count,
                "warnings": self.preflight.warning_count,
            }
        self.log(
            "Preflight",
            f"Errors={self.preflight.error_count}, Warnings={self.preflight.warning_count}",
        )
        return self.preflight

    @traced("상태 수집 및 비교")
    def capture(
        self, stage, label="", *, planned_off=False, planned_vlan=False, **inputs
    ):
        if stage not in WORK_STAGE_NAMES:
            raise ValueError("Unknown stage")
        if len(self.catalog) >= 20:
            raise ValueError("Snapshot 한도 20개입니다. Reset 후 다시 시작하세요.")
        if self.check().has_errors:
            raise ValueError("Preflight failed")
        if stage == "사용자 지정" and label.strip() in WORK_STAGE_NAMES:
            raise ValueError("사용자 지정 단계명은 기본 단계명과 달라야 합니다.")
        resolved = resolve_stage(stage, label.strip()[:60] or stage)
        if stage == "사용자 지정":
            resolved = replace(resolved, slug="custom_" + resolved.slug)
        self.log("Collect Started", resolved.name)
        with self.execution.step("collect", "작업 상태 수집", resolved.name) as step:
            batches = collect(stage, **inputs)
            failed = sum(not r.success for batch in batches.values() for r in batch)
            total = sum(len(batch) for batch in batches.values())
            step.status = "warning" if failed else "success"
            step.detail = f"{resolved.name} · 대상 {len(batches)}대 · CLI 성공 {total - failed}/{total} · 확인 불가 {failed}"
            step.evidence = {"devices": len(batches), "total": total, "failed": failed}
        with self.execution.step(
            "snapshot",
            "작업 전 상태 저장" if stage == PRE_WORK_STAGE else "작업 후 상태 저장",
        ) as step:
            path = self.store.write_snapshot(
                resolved.name,
                DEVICES,
                batches,
                stage_name=resolved.name,
                stage_slug=resolved.slug,
            )
            self.catalog.append(path)
            idx = len(self.catalog) - 1
            step.status = "warning" if failed else "success"
            step.detail = (
                f"Snapshot #{idx + 1} · {resolved.name} · 저장 {len(self.catalog)}개"
                + (" · 수집 실패 포함, 정상 판정 보류" if failed else "")
            )
            step.evidence = {
                "snapshot_id": idx + 1,
                "snapshot_count": len(self.catalog),
                "failed": failed,
            }
        self.log("Snapshot Saved", f"#{idx + 1} {resolved.name}")
        if failed:
            self.log("Collection Error", f"{failed} CLI results unavailable; Unknown")
        base = find_latest_pre_work_snapshot(self.store.list_snapshots())
        if base is not None:
            self.baseline = self.catalog.index(base)
            self.log("Baseline Selected", f"#{self.baseline + 1}")
        # A fresh baseline must not leave a stale comparison on screen.
        self.summary = None
        self.rows, self.html, self.zip_bytes, self.pair = [], "", b"", None
        if stage != PRE_WORK_STAGE and self.baseline is not None:
            self.compare(self.baseline, idx, planned_off, planned_vlan, automatic=True)
        return idx

    def snapshot_rows(self):
        rows = []
        for i, path in enumerate(self.catalog):
            snap = self.store.load_snapshot(path)
            rows.append(
                {
                    "ID": i + 1,
                    "Label": snap.label,
                    "Stage": snap.stage_slug,
                    "Created": snap.created_at,
                    "Devices": len(snap.devices),
                    "Collection": "Unknown"
                    if any(not r.success for r in snap.results)
                    else "Complete",
                }
            )
        return rows

    @traced("Snapshot 비교")
    def compare(
        self, base, target, planned_off=False, planned_vlan=False, *, automatic=False
    ):
        if not (0 <= base < len(self.catalog) and 0 <= target < len(self.catalog)):
            raise ValueError("Choose session-owned snapshots")
        bp, tp = self.catalog[base], self.catalog[target]
        bs, ts = self.store.load_snapshot(bp), self.store.load_snapshot(tp)
        rules = []
        if planned_off:
            rules.append(
                ExpectedChangeRule(
                    stage_slugs=("bb3_off",),
                    device_names=("DEMO-BB4",),
                    command_ids=(
                        "interface_brief",
                        "link_aggregation_summary",
                        "ospf_peer",
                        "vrrp_status",
                    ),
                    title="계획된 BB3 OFF의 BB4 관측 영향",
                )
            )
        if planned_vlan:
            rules.append(
                ExpectedChangeRule(
                    command_ids=("vlan", "interface_description"),
                    title="계획된 VLAN / Description 변경",
                )
            )
        config = replace(
            load_analysis_rules(ROOT / "config/analysis_rules.yaml"),
            expected_changes=tuple(rules),
        )
        with self.execution.step("diff", "DiffEngine / ExpectedChangeRule") as step:
            summary = DiffEngine(config).compare(bp, tp)
            step.detail = f"Snapshot #{base + 1} → #{target + 1} · {len(summary.items)}개 분석 항목 · 계획 규칙 {len(rules)}개"
            step.evidence = {
                "base": base + 1,
                "target": target + 1,
                "items": len(summary.items),
                "rules": len(rules),
            }
        failed = {
            (r.device_name, r.command_id)
            for snap in (bs, ts)
            for r in snap.results
            if not r.success
        }
        unavailable_devices = {
            d.name
            for d in DEVICES
            if any(
                all(not r.success for r in snap.results if r.device_name == d.name)
                for snap in (bs, ts)
            )
        }
        items = []
        for item in summary.items:
            if (item.device_name, item.command_id) in failed or (
                item.device_name in unavailable_devices
                and item.command_id not in DATA_COMMAND_IDS
            ):
                item = replace(
                    item,
                    severity="Unknown",
                    status="Unknown",
                    expectation="unknown",
                    finding_title="Unknown / Collection Error",
                    summary="수집 실패 · 변경 여부 확인 불가",
                    impact_reason="기준 또는 비교 CLI가 없어 정상/장애를 판단할 수 없습니다.",
                    evidence="Synthetic collection timeout",
                    action_hint="수집 경로 확인 후 유효한 Snapshot 두 개로 재비교하세요.",
                    diff="",
                    changed_lines=[],
                    change_count=0,
                    change_preview="비교 불가",
                )
            items.append(item)
        self.summary = replace(summary, items=items)
        self.pair, self.options = (base, target), (planned_off, planned_vlan)
        self.rows = []
        lookup = [
            {(r.device_name, r.command_id): r for r in snap.results}
            for snap in (bs, ts)
        ]
        for i, item in enumerate(items):
            raw = []
            for path, records in zip((bp, tp), lookup):
                if item.command_id not in DATA_COMMAND_IDS:
                    device_results = [
                        r for r in records.values() if r.device_name == item.device_name
                    ]
                    raw.append(
                        f"Snapshot metadata: {sum(r.success for r in device_results)}/{len(device_results)} CLI 수집 성공"
                    )
                    continue
                record = records.get((item.device_name, item.command_id))
                raw.append(
                    (path / record.raw_file).read_text(encoding="utf-8")
                    if record and record.success
                    else "[Collection Error / Unknown]"
                )
            classification = (
                "Unknown"
                if item.severity == "Unknown"
                else (
                    "Unchanged"
                    if raw[0] == raw[1] and item.severity not in ("Critical", "Warning")
                    else (
                        "Expected" if item.expectation == "expected" else "Unexpected"
                    )
                )
            )
            self.rows.append(
                {
                    "Index": i,
                    "Device": item.device_name,
                    "Command": item.command_id,
                    "Category": item.category,
                    "Classification": classification,
                    "Severity": item.severity,
                    "Finding": item.summary,
                    "Before": raw[0],
                    "After": raw[1],
                    "Changes": item.change_count,
                }
            )
        counts = {
            key: sum(row["Classification"] == key for row in self.rows)
            for key in ("Unchanged", "Expected", "Unexpected", "Unknown")
        }
        severities = {
            key: sum(item.severity == key for item in self.summary.items)
            for key in ("Critical", "Warning", "Info", "Unknown")
        }
        self.execution.record(
            "classification",
            "변경 및 위험도 판정",
            "warning"
            if counts["Unknown"] or severities["Critical"] or severities["Warning"]
            else "success",
            f"비교 {len(self.rows)}항목 · "
            + " · ".join(f"{key} {value}" for key, value in counts.items())
            + " · "
            + " · ".join(f"{key} {value}" for key, value in severities.items()),
            {"items": len(self.rows), "classification": counts, "severity": severities},
        )
        self.log(
            "Auto Compare" if automatic else "Manual Compare",
            f"#{base + 1} → #{target + 1}",
        )
        self.make_report(bp, tp)
        return self.rows

    def make_report(self, bp, tp):
        with self.execution.step("report", "ReportWriter · HTML / Share ZIP") as step:
            report_dir = self.root / "comparison"
            report_dir.mkdir(exist_ok=True)
            report = report_dir / "diff_report.html"
            ReportWriter._write_html(report, self.summary)
            html = report.read_text(encoding="utf-8")
            unknown = sum(i.severity == "Unknown" for i in self.summary.items)
            if unknown:
                html = html.replace(
                    '<div class="wrap">',
                    '<div class="wrap"><section class="problem-summary"><h2>Unknown / Collection Error</h2><p>수집 실패 항목은 정상이나 장애로 판단하지 않습니다.</p></section>',
                    1,
                )
                html = html.replace(
                    '<section class="counts" aria-label="등급 필터">',
                    '<section class="counts" aria-label="등급 필터"><button class="count" type="button" data-filter="Unknown"><span class="count-label">확인 불가</span><strong>'
                    + str(unknown)
                    + "</strong></button>",
                    1,
                )
                html = html.replace(
                    "const filterLabels = {",
                    'const filterLabels = {"Unknown":"확인 불가",',
                    1,
                )
                html = html.replace(
                    "예상되지 않은 긴급/주의 문제가 없습니다.",
                    "수집 성공 항목에서 예상되지 않은 긴급/주의가 확인되지 않았습니다. 계획된 변경의 등급은 아래에서 확인하세요. 실패 항목은 확인 불가입니다.",
                )
            for value, replacement in (
                (str(bp), f"Snapshot {self.pair[0] + 1}"),
                (str(tp), f"Snapshot {self.pair[1] + 1}"),
                (str(self.root), "Demo workspace"),
            ):
                html = html.replace(escape(value), replacement).replace(
                    value, replacement
                )
            self.html = html
            report.write_text(html, encoding="utf-8")
            docs = self.root / "empty-docs"
            docs.mkdir(exist_ok=True)
            # Bound report storage across repeated reclassifications.
            for old in report_dir.glob("*.zip"):
                old.unlink()
            bundle = create_share_report_bundle(report_dir, docs_dir=docs)
            self.zip_bytes = bundle.read_bytes()
            self.log("Report Generated", "HTML / Share ZIP")
            step.detail = f"HTML {len(self.html.encode('utf-8'))} bytes · Share ZIP {len(self.zip_bytes)} bytes 생성"
            step.evidence = {
                "html_bytes": len(self.html.encode("utf-8")),
                "zip_bytes": len(self.zip_bytes),
            }


DATA_COMMAND_IDS = {c.id for c in COMMANDS}
