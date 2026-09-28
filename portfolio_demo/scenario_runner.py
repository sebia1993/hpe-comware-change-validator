"""Evaluator stories orchestrate the existing runtime; no manufactured findings."""

from dataclasses import dataclass, field
from time import perf_counter

from portfolio_demo.fixture_collector import COMMANDS, DEVICES
from portfolio_demo.runtime import DemoRuntime

SCENARIOS = {
    "representative": "대표 네트워크 작업 검증",
    "normal": "정상 작업 완료",
    "unexpected": "예상하지 못한 변화",
    "failure": "일부 정보 수집 실패",
}
LABELS = {
    "Unchanged": "정상 유지",
    "Expected": "작업 계획과 일치",
    "Unexpected": "추가 확인 필요",
    "Unknown": "정보 부족으로 판단 불가",
}


def counts(runtime):
    return {
        key: sum(row["Classification"] == key for row in runtime.rows) for key in LABELS
    }


def conclusion(runtime):
    values = counts(runtime)
    if values["Unknown"]:
        return (
            f"일부 상태를 수집하지 못해 {values['Unknown']}개 항목의 정상 여부를 판단할 수 없습니다. "
            f"추가 확인이 필요합니다. 별도로 확인할 변화는 {values['Unexpected']}개입니다."
        )
    if values["Unexpected"]:
        return (
            f"작업 계획에 없던 상태 변화가 {values['Unexpected']}개 발견되었습니다. "
            "추가 확인이 필요합니다."
        )
    return "작업 전과 비교한 결과 계획된 변화 외에 추가 확인이 필요한 이상은 발견되지 않았습니다."


TOPICS = {
    "ospf_peer": "핵심 네트워크 연결 상태",
    "link_aggregation_summary": "여러 회선을 묶어 사용하는 연결 상태",
    "vrrp_status": "이중화 장비의 역할",
    "interface_brief": "장비의 회선 연결 상태",
    "interface_description": "연결에 붙인 설명",
    "vlan": "네트워크 구역 구성",
    "cpu_usage": "장비의 처리 자원 사용 상태",
    "memory_usage": "장비의 메모리 사용 상태",
    "device_connectivity": "장비 정보 수집의 완전성",
}


def business_finding(runtime, row):
    """Carry the same item index into the technical evidence, without reclassification."""
    item = runtime.summary.items[row["Index"]]
    topic = TOPICS.get(item.command_id, "장비 상태")
    classification = row["Classification"]
    if classification == "Unknown":
        message = f"{topic}를 수집하지 못해 작업 전후 차이를 판단할 수 없습니다."
    elif classification == "Expected":
        message = f"{topic}의 변화가 등록된 작업 계획과 일치합니다."
    elif classification == "Unexpected":
        message = f"{topic}에서 계획에 없던 변화 또는 확인할 신호가 발견되었습니다."
    else:
        message = f"{topic}에 추가 확인이 필요한 변화가 없습니다."
    if classification != "Unknown" and item.severity in ("Critical", "Warning"):
        message += (
            " "
            + ("긴급 확인" if item.severity == "Critical" else "주의 확인")
            + " 대상입니다."
        )
    return {
        "index": row["Index"],
        "device": item.device_name,
        "message": message,
        "classification": classification,
        "severity": item.severity,
    }


@dataclass
class ScenarioStep:
    id: str
    title: str
    description: str
    result: str = "대기"
    status: str = "pending"
    elapsed_ms: float | None = None


@dataclass
class ScenarioRun:
    key: str
    name: str
    steps: list = field(default_factory=list)
    completed: bool = False
    error: str = ""
    current_index: int = 0
    started_at: float | None = None
    elapsed_ms: float | None = None


class ScenarioRunner:
    def __init__(self):
        self.runtime = DemoRuntime()
        self.run = None
        self.inputs = {}
        self.planned_vlan = False

    def start(self, key):
        if key not in SCENARIOS:
            raise ValueError("지원하지 않는 시나리오입니다.")
        self.inputs = {
            "vlan": key in ("representative", "normal"),
            "resource": key in ("representative", "unexpected"),
            "timeout": key == "failure",
        }
        self.planned_vlan = self.inputs["vlan"]
        self.run = ScenarioRun(
            key,
            SCENARIOS[key],
            [
                ScenarioStep(
                    "preflight",
                    "대상과 읽기 전용 명령 확인",
                    "검증할 장비와 조회 명령이 안전한 읽기 전용 구성인지 확인합니다.",
                ),
                ScenarioStep(
                    "before",
                    "작업 전 상태 수집·저장",
                    "네트워크 작업 전 상태를 비교 기준 Snapshot으로 저장합니다.",
                ),
                ScenarioStep(
                    "after",
                    "작업 후 상태 재수집·저장",
                    "같은 대상과 명령으로 작업 후 상태를 다시 저장합니다.",
                ),
                ScenarioStep(
                    "diff",
                    "작업 전·후 상태 자동 비교",
                    "두 Snapshot에서 실제로 달라진 분석 항목을 찾습니다.",
                ),
                ScenarioStep(
                    "classify",
                    "변화 의미와 우선순위 판정",
                    "계획과 일치하는 변화, 추가 확인 필요, 정보 부족을 구분합니다.",
                ),
                ScenarioStep(
                    "report",
                    "결과 보고서 생성",
                    "판단 근거를 HTML 보고서와 공유 ZIP으로 생성합니다.",
                ),
            ],
            started_at=perf_counter(),
        )
        self.run.steps[0].status = "running"
        return self.run

    def advance(self, on_change=None):
        if self.run is None:
            raise ValueError("시나리오를 먼저 시작하세요.")
        if self.run.completed or self.run.error:
            return self.run

        index = self.run.current_index
        step = self.run.steps[index]
        step.status = "running"
        if on_change:
            on_change(self)
        started = perf_counter()

        try:
            if step.id == "preflight":
                self._run_preflight(step)
            elif step.id == "before":
                self._run_before(step)
            elif step.id == "after":
                self._run_after(step)
            elif step.id == "diff":
                self._run_diff(step)
            elif step.id == "classify":
                self._run_classification(step)
            elif step.id == "report":
                self._run_report(step)
            else:
                raise ValueError("Unknown scenario step")

            step.elapsed_ms = (perf_counter() - started) * 1000
            if step.status == "running":
                step.status = "success"
            self.run.current_index += 1

            if self.run.current_index >= len(self.run.steps):
                self.run.completed = True
                self.run.elapsed_ms = (perf_counter() - self.run.started_at) * 1000
            else:
                self.run.steps[self.run.current_index].status = "running"
        except Exception as exc:
            step.elapsed_ms = (perf_counter() - started) * 1000
            step.status = "failure"
            step.result = "실행 중단: " + str(exc)
            self.run.error = str(exc)
            self.run.elapsed_ms = (perf_counter() - self.run.started_at) * 1000
            raise
        finally:
            if on_change:
                on_change(self)

        return self.run

    def play(self, key, on_change=None):
        self.start(key)
        if on_change:
            on_change(self)
        with self.runtime.execution.operation(self.run.name):
            while not self.run.completed and not self.run.error:
                self.advance(on_change)
        return self.run

    def _run_preflight(self, step):
        result = self.runtime.check()
        if result.has_errors:
            raise ValueError("설정 점검에 실패해 검증을 중단했습니다.")
        step.status = "warning" if result.warning_count else "success"
        step.result = (
            f"대상 {len(DEVICES)}대 · 읽기 전용 명령 {len(COMMANDS)}종 · "
            f"Error {result.error_count} · Warning {result.warning_count}"
        )

    def _snapshot_result(self, index):
        snap = self.runtime.store.load_snapshot(self.runtime.catalog[index])
        failed = sum(not result.success for result in snap.results)
        return (
            f"장비 {len(snap.devices)}대 · 수집 결과 {len(snap.results)}개 저장 "
            f"(성공 {len(snap.results) - failed}, 정보 부족 {failed}) · "
            f"Snapshot #{index + 1}",
            failed,
        )

    def _run_before(self, step):
        index = self.runtime.capture(
            "작업 전",
            check_preflight=False,
            auto_compare=False,
        )
        step.result, failed = self._snapshot_result(index)
        step.status = "warning" if failed else "success"

    def _run_after(self, step):
        index = self.runtime.capture(
            "사용자 지정",
            SCENARIOS[self.run.key],
            planned_vlan=self.planned_vlan,
            check_preflight=False,
            auto_compare=False,
            **self.inputs,
        )
        step.result, failed = self._snapshot_result(index)
        if self.inputs["vlan"]:
            step.result += " · 네트워크 구역/연결 설명 변화 포함"
        if self.inputs["resource"]:
            step.result += " · 처리 자원 변화 포함"
        if self.inputs["timeout"]:
            step.result += " · 일부 정보 수집 실패 포함"
        step.status = "warning" if failed else "success"

    def _run_diff(self, step):
        summary = self.runtime.prepare_comparison(
            0,
            1,
            False,
            self.planned_vlan,
            automatic=True,
        )
        step.result = f"Snapshot #1 → #2 · {len(summary.items)}개 분석 항목 비교"
        step.status = "success"

    def _run_classification(self, step):
        self.runtime.classify_pending_comparison()
        values = counts(self.runtime)
        severities = {
            key: sum(item.severity == key for item in self.runtime.summary.items)
            for key in ("Critical", "Warning", "Info", "Unknown")
        }
        step.result = " · ".join(f"{LABELS[key]} {value}개" for key, value in values.items())
        step.status = (
            "warning"
            if values["Unexpected"]
            or values["Unknown"]
            or severities["Critical"]
            or severities["Warning"]
            else "success"
        )

    def _run_report(self, step):
        self.runtime.report_pending_comparison()
        if not (self.runtime.html and self.runtime.zip_bytes):
            raise ValueError("보고서 생성 결과가 준비되지 않았습니다.")
        step.result = (
            f"HTML {len(self.runtime.html.encode('utf-8'))} bytes · "
            f"공유 ZIP {len(self.runtime.zip_bytes)} bytes"
        )
        step.status = "success"
