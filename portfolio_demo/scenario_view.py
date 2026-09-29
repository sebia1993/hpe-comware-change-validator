"""Business-language presentation of the same runtime evidence."""

from html import escape
from portfolio_demo.scenario_runner import (
    LABELS,
    TOPICS,
    business_finding,
    conclusion,
    counts,
)


def render_timeline(runner, slot):
    if not runner or not runner.run:
        slot.empty()
        return
    run = runner.run
    labels = {
        "pending": "대기",
        "running": "실행 중",
        "success": "완료",
        "warning": "확인 필요",
        "failure": "실패",
    }
    cards = "".join(
        '<article style="border:1px solid #8885;border-radius:10px;padding:1rem;margin:.6rem 0;overflow-wrap:anywhere">'
        f"<h4>STEP {index} · {escape(step.title)}</h4><p>{escape(step.description)}</p>"
        f"<b>{labels[step.status]}</b> · {escape(step.result)}"
        + (
            f" · {step.elapsed_ms:.1f} ms"
            if step.elapsed_ms is not None
            else ""
        )
        + "</article>"
        for index, step in enumerate(run.steps, 1)
    )
    state = (
        "검증 완료" if run.completed else "실행 중단" if run.error else "검증 실행 중"
    )
    slot.markdown(
        '<section aria-label="Scenario Timeline"><h3>작업 검증 흐름</h3>'
        f"<p>{escape(run.name)} · {state}</p>{cards}</section>",
        unsafe_allow_html=True,
    )



def render_run_status(runner, st):
    if not runner or not runner.run:
        st.info("READY · 대표 검증을 실행하면 실제 6단계 처리 과정을 자동으로 진행합니다.")
        st.progress(0, text="대기 중 · 0/6")
        return

    run = runner.run
    total = len(run.steps)
    completed = sum(
        step.status in ("success", "warning", "failure") for step in run.steps
    )
    if run.error:
        st.error(
            f"FAILED · {min(run.current_index + 1, total)}/{total} · {run.error}"
        )
    elif run.completed:
        duration = f" · {run.elapsed_ms:.1f} ms" if run.elapsed_ms is not None else ""
        st.success(f"COMPLETED · {total}/{total} · 검증 완료{duration}")
    else:
        current = run.steps[run.current_index]
        st.info(
            f"RUNNING · {run.current_index + 1}/{total} · {current.title}"
        )
    st.progress(
        min(completed / total, 1.0),
        text=f"실제 처리 단계 · {completed}/{total}",
    )


def render_result(runtime, st):
    if runtime.summary is None:
        return
    st.markdown("### 이번 작업 검증 결과")
    values = counts(runtime)
    message = conclusion(runtime)
    if values["Unknown"] or values["Unexpected"]:
        st.warning(message)
    else:
        st.success(message)
    for col, (key, label) in zip(st.columns(4), LABELS.items()):
        col.metric(label, values[key])
    planned_risks = sum(
        row["Classification"] == "Expected"
        and row["Severity"] in ("Critical", "Warning")
        for row in runtime.rows
    )
    if planned_risks:
        st.warning(
            f"계획과 일치하는 변화 중에도 긴급·주의 {planned_risks}개가 있습니다. 계획 일치가 안전 보장을 뜻하지는 않습니다."
        )
    st.caption(
        "수치는 분석 항목 수입니다. 각 항목은 한 분류에만 포함되며, 장비 대수나 전체 네트워크 안전 보장을 뜻하지 않습니다."
    )



CATEGORY_LABELS = {
    "basic": "기본 정보",
    "hardware": "하드웨어",
    "interface": "인터페이스 / LACP",
    "switching": "스위칭",
    "routing": "라우팅 / 이중화",
    "resource": "CPU / Memory",
    "log": "최근 로그",
    "connection": "장비 접속 상태",
}
CATEGORY_ORDER = {
    key: index for index, key in enumerate(CATEGORY_LABELS)
}


def comparison_scope(runtime):
    grouped = {}
    for row in runtime.rows:
        category = row["Category"]
        bucket = grouped.setdefault(
            category,
            {
                "분야": CATEGORY_LABELS.get(category, category),
                "비교 항목": 0,
                "정상 유지": 0,
                "작업 계획과 일치": 0,
                "추가 확인 필요": 0,
                "정보 부족": 0,
            },
        )
        bucket["비교 항목"] += 1
        bucket[LABELS[row["Classification"]]] += 1
    return [
        grouped[key]
        for key in sorted(
            grouped,
            key=lambda value: (CATEGORY_ORDER.get(value, 99), value),
        )
    ]


def render_comparison_scope(runtime, st):
    if not runtime.summary:
        return

    st.markdown("### 무엇을 비교했나요?")
    values = counts(runtime)
    devices = {row["Device"] for row in runtime.rows}
    categories = {row["Category"] for row in runtime.rows}
    changed = values["Expected"] + values["Unexpected"] + values["Unknown"]

    metrics = st.columns(4)
    metrics[0].metric("전체 비교 항목", len(runtime.rows))
    metrics[1].metric("대상 장비", len(devices))
    metrics[2].metric("점검 분야", len(categories))
    metrics[3].metric("변화 / 확인 필요", changed)

    st.caption(
        "먼저 '추가 확인 필요'와 '정보 부족'을 확인하고, "
        "'정상 유지'는 작업 후에도 바뀌지 않은 상태를 뜻합니다."
    )
    st.dataframe(
        comparison_scope(runtime),
        hide_index=True,
        width="stretch",
    )

    with st.expander(f"전체 {len(runtime.rows)}개 비교 항목 보기", expanded=False):
        table = []
        for row in runtime.rows:
            table.append(
                {
                    "분야": CATEGORY_LABELS.get(row["Category"], row["Category"]),
                    "장비": row["Device"],
                    "점검 항목": TOPICS.get(row["Command"], row["Command"]),
                    "분류": LABELS[row["Classification"]],
                    "위험도": row["Severity"],
                    "비교 결과": row["Finding"],
                }
            )
        st.dataframe(table, hide_index=True, width="stretch")



def render_business_trace(runtime, slot):
    if not runtime.execution.steps:
        slot.empty()
        return
    names = {
        "preflight": "대상과 읽기 전용 수집 설정 확인",
        "collect": "장비 상태 읽기",
        "snapshot": "수집한 상태 저장",
        "diff": "저장된 작업 전후 상태 비교",
        "classification": "계획 일치와 확인할 변화 분류",
        "report": "결과 보고서와 공유 파일 생성",
        "execution_error": "검증 중단",
    }
    icons = {"running": "◌", "success": "✓", "warning": "⚠", "failure": "✕"}
    rows = []
    for step in runtime.execution.steps:
        timing = f" · {step.elapsed_ms:.1f} ms" if step.elapsed_ms is not None else ""
        evidence = step.evidence
        detail = ""
        if step.id == "preflight" and evidence:
            detail = f"대상 {evidence['devices']}대 · 읽기 전용 명령 {evidence['commands']}종 · 오류 {evidence['errors']}건 · 설정 안내 {evidence['warnings']}건"
        elif step.id == "collect" and evidence:
            detail = f"수집 결과 {evidence['total']}개 중 성공 {evidence['total'] - evidence['failed']}개 · 정보 부족 {evidence['failed']}개"
        elif step.id == "snapshot" and evidence:
            detail = f"저장본 #{evidence['snapshot_id']} · 현재 {evidence['snapshot_count']}개 보관"
        elif step.id == "diff" and evidence:
            detail = f"{evidence['items']}개 분석 항목 · 등록된 계획 규칙 {evidence['rules']}개"
        elif step.id == "classification" and evidence:
            detail = " · ".join(
                f"{LABELS[k]} {v}개" for k, v in evidence["classification"].items()
            )
        elif step.id == "report" and evidence:
            detail = f"보고서 {evidence['html_bytes']} bytes · 공유 파일 {evidence['zip_bytes']} bytes"
        rows.append(
            f"<p>{icons[step.status]} {escape(names.get(step.id, '처리 기록'))}{timing}<br>{escape(detail)}</p>"
        )
    duration = runtime.execution.elapsed_ms
    state = "실제 처리 중" if duration is None else f"실제 처리시간 · {duration:.1f} ms"
    slot.markdown(
        '<section aria-label="Execution Trace"><h3>실제 처리 기록</h3>'
        f"<p>{state}</p>{''.join(rows)}<p>합성 입력의 실제 호출 시간입니다. 수집 실패는 정상 판정이 아닙니다. 상세 수치와 명령은 기술 상세에서 확인할 수 있습니다.</p></section>",
        unsafe_allow_html=True,
    )


def render_findings(runtime, st):
    if not runtime.summary:
        return
    st.markdown("### 주요 확인 항목")
    selected = [row for row in runtime.rows if row["Classification"] != "Unchanged"]
    if not selected:
        st.info("추가 확인이 필요한 변화가 없습니다.")
    for row in selected:
        view = business_finding(runtime, row)
        with st.container(border=True):
            st.write(
                f"**항목 #{view['index'] + 1} · {view['device']} · {LABELS[view['classification']]}**"
            )
            st.write(view["message"])
            with st.expander(f"기술 근거 보기 · 항목 #{view['index'] + 1}"):
                item = runtime.summary.items[view["index"]]
                st.write(
                    f"Command: {item.command_id} · Severity: {item.severity} · Classification: {view['classification']}"
                )
                st.write(item.summary)
                st.write(item.evidence)
                st.markdown("**작업 전**")
                st.code(row["Before"], language="text")
                st.markdown("**작업 후**")
                st.code(row["After"], language="text")
