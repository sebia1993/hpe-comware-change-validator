"""Evaluator stories orchestrate the existing runtime; no manufactured findings."""

from dataclasses import dataclass, field

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


@dataclass
class ScenarioRun:
    key: str
    name: str
    steps: list = field(default_factory=list)
    completed: bool = False
    error: str = ""


class ScenarioRunner:
    def __init__(self):
        self.runtime = DemoRuntime()
        self.run = None
        self.post_started = False

    def play(self, key, on_change=None):
        if key not in SCENARIOS:
            raise ValueError("지원하지 않는 시나리오입니다.")
        self.run = ScenarioRun(
            key,
            SCENARIOS[key],
            [
                ScenarioStep(
                    "before",
                    "작업 전 상태 저장",
                    "장비 상태를 읽고 비교의 기준으로 저장합니다.",
                ),
                ScenarioStep(
                    "plan",
                    "예정된 작업 상태 재현",
                    "공개 데모의 합성 입력을 선택합니다. 실제 장비를 변경하지 않습니다.",
                ),
                ScenarioStep(
                    "after",
                    "작업 후 상태 재수집",
                    "같은 장비와 읽기 전용 명령으로 다시 상태를 저장합니다.",
                ),
                ScenarioStep(
                    "diff",
                    "작업 전·후 자동 비교",
                    "저장된 두 상태에서 달라진 항목을 찾습니다.",
                ),
                ScenarioStep(
                    "classify",
                    "변화 의미 분석",
                    "등록된 계획과 실제 변화, 정보 부족을 구분합니다.",
                ),
                ScenarioStep(
                    "report",
                    "최종 결과와 보고서",
                    "판단 근거와 공유할 보고서를 준비합니다.",
                ),
            ],
        )
        r = self.runtime

        def update():
            self._observe()
            if on_change:
                on_change(self)

        r.execution.on_change = update
        try:
            with r.execution.operation(self.run.name):
                self.run.steps[0].status = "running"
                update()
                if r.check().has_errors:
                    raise ValueError("설정 점검에 실패해 검증을 중단했습니다.")
                r.capture("작업 전")
                inputs = {
                    "vlan": key in ("representative", "normal"),
                    "resource": key in ("representative", "unexpected"),
                    "timeout": key == "failure",
                }
                plan = self.run.steps[1]
                plan.status = "success"
                plan.result = (
                    "네트워크 구역·연결 설명 변경을 작업 계획으로 등록했습니다."
                    if inputs["vlan"]
                    else "추가 변경을 계획으로 등록하지 않았습니다."
                )
                plan.result += (
                    " 처리 자원 이상 입력을 포함합니다." if inputs["resource"] else ""
                )
                plan.result += (
                    " 일부 정보 수집 실패 입력을 포함합니다."
                    if inputs["timeout"]
                    else ""
                )
                self.post_started = True
                self.run.steps[2].status = "running"
                update()
                # capture performs the existing automatic compare and ReportWriter path.
                r.capture(
                    "사용자 지정", SCENARIOS[key], planned_vlan=inputs["vlan"], **inputs
                )
                if not (r.summary and r.html and r.zip_bytes):
                    raise ValueError("비교 결과 또는 보고서가 준비되지 않았습니다.")
                self.run.completed = True
                update()
        except Exception as exc:
            self.run.error = str(exc)
            for step in self.run.steps:
                if step.status == "running":
                    step.status, step.result = "failure", "실행 중단: " + str(exc)
            raise
        finally:
            r.execution.on_change = None
            if on_change:
                on_change(self)
        return self.run

    def _observe(self):
        r = self.runtime
        if not self.run:
            return
        for index, path in enumerate(r.catalog[:2]):
            snap = r.store.load_snapshot(path)
            step = self.run.steps[0 if index == 0 else 2]
            failed = sum(not result.success for result in snap.results)
            step.status = "warning" if failed else "success"
            step.result = (
                f"장비 {len(snap.devices)}대 · 수집 결과 {len(snap.results)}개 저장 "
                f"(성공 {len(snap.results) - failed}, 정보 부족 {failed}) · 저장본 #{index + 1}"
            )
        if not self.post_started:
            return
        for evidence in r.execution.steps:
            if evidence.id not in ("diff", "classification", "report"):
                continue
            step = self.run.steps[
                {"diff": 3, "classification": 4, "report": 5}[evidence.id]
            ]
            if evidence.status == "running":
                step.status, step.result = "running", "실제 처리 중"
            elif evidence.id == "diff":
                step.status = evidence.status
                step.result = f"저장본 #{evidence.evidence.get('base')} → #{evidence.evidence.get('target')} · {evidence.evidence.get('items')}개 분석 항목 비교"
            elif evidence.id == "classification":
                values = evidence.evidence["classification"]
                step.status = (
                    "warning"
                    if values["Unexpected"] or values["Unknown"]
                    else "success"
                )
                step.result = " · ".join(
                    f"{LABELS[k]} {v}개" for k, v in values.items()
                )
            else:
                step.status = evidence.status
                step.result = f"보고서 {evidence.evidence.get('html_bytes')} bytes · 공유 파일 {evidence.evidence.get('zip_bytes')} bytes 준비"
