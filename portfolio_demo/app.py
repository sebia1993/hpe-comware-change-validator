from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.workflow import CUSTOM_STAGE, WORK_STAGE_NAMES
from portfolio_demo.fixture_collector import COMMANDS, DEVICES
from portfolio_demo.runtime import DemoRuntime

from portfolio_demo.execution_trace import render_trace
from portfolio_demo.guided_flow import GuidedSlot, begin
from portfolio_demo.scenario_runner import SCENARIOS, ScenarioRunner
from portfolio_demo.scenario_view import (
    render_timeline,
    render_result,
    render_business_trace,
    render_findings,
)

st.set_page_config(
    page_title="Network Change Validator · Public Web Edition",
    page_icon="🔎",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1540px;
        padding-top: 1.15rem;
        padding-bottom: 3rem;
    }
    .brand-box {
        border: 1px solid rgba(120, 145, 175, .24);
        border-radius: 13px;
        padding: 12px 15px;
        background: rgba(15, 23, 35, .58);
        margin-bottom: .55rem;
    }
    .brand-title {
        font-size: 1.45rem;
        font-weight: 850;
    }
    .brand-sub {
        color: #8797aa;
        font-size: .8rem;
        margin-top: .15rem;
    }
    .top-stat {
        border: 1px solid rgba(120, 145, 175, .24);
        border-radius: 9px;
        padding: 8px 10px;
        min-height: 58px;
        background: rgba(17, 26, 39, .55);
    }
    .top-stat-label {
        color: #8293a7;
        font-size: .68rem;
        font-weight: 750;
    }
    .top-stat-value {
        font-size: .88rem;
        font-weight: 820;
        margin-top: .18rem;
    }
    .section-note {
        border-left: 4px solid #4b8bff;
        padding: 8px 11px;
        background: rgba(43, 89, 160, .12);
        border-radius: 6px;
        font-size: .84rem;
        color: #9bacbf;
        margin-bottom: .65rem;
    }
    .demo-pill {
        display: inline-block;
        border: 1px solid #38506d;
        border-radius: 999px;
        padding: .16rem .5rem;
        margin-right: .3rem;
        color: #afc8ee;
        font-size: .66rem;
        font-weight: 800;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "runtime" not in st.session_state:
    st.session_state.runtime = DemoRuntime()
if "comware_page" not in st.session_state:
    st.session_state.comware_page = "장비 설정"
if "comware_demo_vlan" not in st.session_state:
    st.session_state.comware_demo_vlan = False
if "comware_demo_resource" not in st.session_state:
    st.session_state.comware_demo_resource = False
if "comware_demo_timeout" not in st.session_state:
    st.session_state.comware_demo_timeout = False

r = st.session_state.runtime


def current_state() -> str:
    if r.summary is not None:
        return "비교 완료"
    if r.catalog:
        return "Snapshot 준비"
    if r.preflight is not None:
        return "설정 점검 완료"
    return "대기"


def baseline_text() -> str:
    if r.baseline is None:
        return "-"
    return f"#{r.baseline + 1}"


def target_text() -> str:
    if r.pair is None:
        return "-"
    return f"#{r.pair[1] + 1}"


def render_topbar() -> None:
    left, right = st.columns([3.7, 2.3])
    with left:
        page_descriptions = {
            "장비 설정": "접속 계정, 대상 장비, 상태 수집을 한 화면에서 실행합니다.",
            "비교 결과": "선택한 두 Snapshot의 명령 출력 차이를 구조화해 확인합니다.",
            "작업 로그": "수집, 비교, 오류와 보고서 생성 이력을 시간 순서대로 확인합니다.",
        }
        st.markdown(
            '<div class="brand-box">'
            f'<div class="brand-title">{st.session_state.comware_page}</div>'
            f'<div class="brand-sub">{page_descriptions[st.session_state.comware_page]}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
    with right:
        cols = st.columns(3)
        values = (
            ("현재 상태", current_state()),
            ("기준", baseline_text()),
            ("비교 대상", target_text()),
        )
        for col, (label, value) in zip(cols, values, strict=True):
            col.markdown(
                '<div class="top-stat">'
                f'<div class="top-stat-label">{label}</div>'
                f'<div class="top-stat-value">{value}</div>'
                "</div>",
                unsafe_allow_html=True,
            )


def render_reviewer_summary() -> None:
    st.markdown("### 이 프로젝트는 무엇을 해결하나요?")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("**프로젝트 목적**")
            st.write(
                "네트워크 작업을 하기 전과 후의 상태를 자동으로 비교해, "
                "의도한 변경과 예상하지 못한 이상, 그리고 확인할 수 없는 항목을 구분하는 검증 도구입니다."
            )
            st.caption(
                "쉽게 말해: 작업 전 사진과 작업 후 사진을 비교하듯 네트워크 상태의 차이를 자동으로 검사합니다."
            )
    with right:
        with st.container(border=True):
            st.markdown("**이 데모에서 보여주는 것**")
            st.write(
                "작업 전 상태 저장 → 작업 후 상태 저장 → 자동 비교 → 위험 항목 분류 → "
                "변경 전·후 근거와 보고서 생성까지의 전체 검증 과정을 보여줍니다."
            )
            st.caption(
                "해커톤 관점: Before/After 데이터를 구조화하고, 변화의 의미와 우선순위를 자동으로 분류합니다."
            )


def render_sidebar() -> None:
    with st.container():
        st.markdown(
            '<div style="display:flex;gap:.6rem;align-items:center;margin-bottom:1rem">'
            '<div style="background:#3076d8;color:white;font-weight:850;'
            'padding:.7rem .65rem;border-radius:7px">백본</div>'
            '<div style="font-weight:850;line-height:1.2">백본 상태<br>추적 콘솔</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        page = st.radio(
            "Navigation",
            ["장비 설정", "비교 결과", "작업 로그"],
            index=["장비 설정", "비교 결과", "작업 로그"].index(
                st.session_state.comware_page
            ),
            format_func=lambda value: {
                "장비 설정": "장비 설정 · 접속 계정/대상 장비/상태 수집",
                "비교 결과": "비교 결과 · 기준/대상 변경점",
                "작업 로그": "작업 로그 · 실행 이력과 오류",
            }[value],
            label_visibility="collapsed",
        )
        if page != st.session_state.comware_page:
            st.session_state.comware_page = page
            st.rerun()

        st.divider()
        st.markdown(
            '<span class="demo-pill">PUBLIC WEB EDITION</span>'
            '<span class="demo-pill">READ ONLY</span>',
            unsafe_allow_html=True,
        )
        st.caption("v0.9.0 · 실제 SSH 대신 합성 CLI만 사용")
        if st.button("Demo Reset", use_container_width=True):
            st.session_state.pop("scenario_runner", None)
            r.close()
            st.session_state.runtime = DemoRuntime()
            st.session_state.comware_page = "장비 설정"
            st.rerun()


def render_access_section() -> None:
    st.markdown("### 접속 계정")
    with st.container(border=True):
        fields = st.columns([2, 2, 1])
        fields[0].text_input(
            "계정",
            value="Public Demo에서는 입력하지 않습니다",
            disabled=True,
        )
        fields[1].text_input(
            "암호",
            value="synthetic-only",
            type="password",
            disabled=True,
        )
        fields[2].text_input(
            "제한시간(초)",
            value="30",
            disabled=True,
        )
        st.markdown(
            '<div class="section-note"><b>운영 입력 순서</b><br>'
            "접속 계정과 대상 장비를 먼저 확인한 뒤 설정 점검을 실행하고, "
            "이상이 없으면 상태 수집을 시작합니다.</div>",
            unsafe_allow_html=True,
        )


def render_devices_section() -> None:
    st.markdown("### 대상 장비")
    st.dataframe(
        [
            {
                "사용": device.enabled,
                "장비명": device.name,
                "IP/호스트": device.host,
                "포트": device.port,
                "장비 타입": device.device_type,
            }
            for device in DEVICES
        ],
        hide_index=True,
        width="stretch",
    )
    actions = st.columns([1, 1, 1, 2])
    actions[0].button("장비 추가", disabled=True, use_container_width=True)
    actions[1].button("장비 목록 불러오기", disabled=True, use_container_width=True)
    actions[2].button("장비 목록 저장", disabled=True, use_container_width=True)
    enabled = sum(device.enabled for device in DEVICES)
    actions[3].caption(
        f"대상 요약 · 사용 {enabled}대 / 입력 {len(DEVICES)}대 / 행 {len(DEVICES)}개"
    )


def capture_snapshot(
    stage: str,
    label: str,
    planned_off: bool,
    planned_vlan: bool,
) -> None:
    st.session_state.pop("scenario_runner", None)
    try:
        r.capture(
            stage,
            label if stage == CUSTOM_STAGE else "",
            planned_off=planned_off,
            planned_vlan=planned_vlan,
            vlan=st.session_state.comware_demo_vlan,
            resource=st.session_state.comware_demo_resource,
            timeout=st.session_state.comware_demo_timeout,
        )
    except ValueError as exc:
        st.error(str(exc))


def render_collection_section() -> None:
    st.markdown("### 상태 수집")
    with st.container(border=True):
        cols = st.columns([1.4, 2, 1, 1])
        stage = cols[0].selectbox("작업 단계", WORK_STAGE_NAMES)
        label = cols[1].text_input(
            "수집 단계명(선택)",
            disabled=stage != CUSTOM_STAGE,
            max_chars=60,
        )
        if cols[2].button("설정 점검", use_container_width=True):
            st.session_state.pop("scenario_runner", None)
            r.check()
            st.rerun()

        planned_off = False
        planned_vlan = False

        if cols[3].button(
            "상태 수집 시작",
            type="primary",
            use_container_width=True,
            disabled=len(r.catalog) >= 20,
        ):
            capture_snapshot(stage, label, planned_off, planned_vlan)
            st.rerun()

        if r.preflight:
            if r.preflight.has_errors:
                st.error(
                    f"설정 점검 실패 · Error {r.preflight.error_count} / "
                    f"Warning {r.preflight.warning_count}"
                )
            elif r.preflight.warning_count:
                st.warning(
                    f"설정 점검 주의 · Error {r.preflight.error_count} / "
                    f"Warning {r.preflight.warning_count}"
                )
            else:
                st.success("설정 점검 통과")

        st.caption(
            "작업 전 Snapshot이 있으면 후속 Snapshot 수집 시 자동으로 기준과 비교합니다."
        )

        with st.expander("Public Demo 합성 변화 입력", expanded=False):
            st.caption(
                "실제 Desktop App에서는 장비에서 읽은 상태를 사용합니다. "
                "공개 Web Edition에서만 비교 동작을 보여주기 위해 합성 변화 값을 주입합니다."
            )
            st.session_state.comware_demo_vlan = st.checkbox(
                "VLAN 20 / Description 변경",
                value=st.session_state.comware_demo_vlan,
            )
            st.session_state.comware_demo_resource = st.checkbox(
                "CPU 사용률 85%",
                value=st.session_state.comware_demo_resource,
            )
            st.session_state.comware_demo_timeout = st.checkbox(
                "BB3 OSPF CLI 수집 실패",
                value=st.session_state.comware_demo_timeout,
            )


def render_command_section() -> None:
    with st.expander("점검 명령 세트", expanded=False):
        st.caption("읽기 전용 명령만 허용되며 실제 전송 직전에 다시 안전 검증합니다.")
        st.dataframe(
            [asdict(command) for command in COMMANDS],
            hide_index=True,
            width="stretch",
        )


def render_settings_page() -> None:
    global trace_slot
    controls_area = st.container()
    trace_slot = st.empty()
    r.execution.on_change = lambda: render_trace(r.execution, trace_slot)
    render_trace(r.execution, trace_slot)
    with controls_area:
        render_access_section()
        render_devices_section()
        render_collection_section()
    render_command_section()


def severity_metrics() -> dict[str, int]:
    keys = ("Critical", "Warning", "Info", "Unchanged")
    if not r.summary:
        return {key: 0 for key in keys}
    return {
        key: sum(
            item.severity == key or (key == "Unchanged" and item.status == "unchanged")
            for item in r.summary.items
        )
        for key in keys
    }


def classification_metrics() -> dict[str, int]:
    keys = ("Expected", "Unexpected", "Unknown")
    if not r.summary:
        return {key: 0 for key in keys}
    return {key: sum(row["Classification"] == key for row in r.rows) for key in keys}


def run_sample_validation() -> None:
    st.session_state.pop("scenario_runner", None)
    demo = DemoRuntime()
    demo.execution.on_change = lambda: render_trace(demo.execution, trace_slot)
    with demo.execution.operation("작업 전 저장 → 작업 후 저장 → 자동 비교"):
        demo.capture("작업 전")
        demo.capture("백본3 OFF 중")
    r.close()
    st.session_state.runtime = demo
    st.session_state.comware_page = "비교 결과"
    st.rerun()


def render_compare_controls() -> tuple[bool, bool]:
    st.markdown("### Snapshot 비교")
    planned_off = False
    planned_vlan = False

    with st.container(border=True):
        if not r.catalog:
            st.info(
                "Snapshot이 없습니다. 장비 설정에서 ‘작업 전’ 상태를 수집하거나 "
                "아래 샘플 검증을 실행하세요."
            )
            if st.button(
                "샘플 검증 생성",
                type="primary",
                use_container_width=True,
            ):
                run_sample_validation()
            return planned_off, planned_vlan

        catalog = r.snapshot_rows()
        fmt = lambda index: f"#{index + 1} {catalog[index]['Label']}"
        cols = st.columns([2, 2, 1])
        base = cols[0].selectbox(
            "기준 스냅샷",
            range(len(catalog)),
            index=r.baseline or 0,
            format_func=fmt,
        )
        target = cols[1].selectbox(
            "비교 스냅샷",
            range(len(catalog)),
            index=len(catalog) - 1,
            format_func=fmt,
        )
        cols[2].button("목록 새로고침", disabled=True, use_container_width=True)

        with st.expander("계획 변경 규칙", expanded=False):
            planned_off = st.checkbox(
                "BB3 OFF 영향을 계획된 변경으로 등록",
                value=r.options[0] if r.summary else False,
            )
            planned_vlan = st.checkbox(
                "VLAN / Description을 계획된 변경으로 등록",
                value=r.options[1] if r.summary else False,
            )
            st.caption(
                "계획과 일치하더라도 Critical / Warning 등급 자체는 숨기지 않습니다."
            )

        actions = st.columns(5)
        if actions[0].button(
            "선택 항목 비교",
            type="primary",
            use_container_width=True,
        ):
            try:
                st.session_state.pop("scenario_runner", None)
                r.compare(base, target, planned_off, planned_vlan)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

        if actions[1].button("샘플 검증 생성", use_container_width=True):
            run_sample_validation()

        if r.html:
            actions[2].download_button(
                "최근 리포트",
                r.html,
                "diff_report.html",
                "text/html",
                use_container_width=True,
            )
            actions[3].download_button(
                "공유 ZIP",
                r.zip_bytes,
                "change-validation-share.zip",
                "application/zip",
                use_container_width=True,
            )
        else:
            actions[2].button("최근 리포트", disabled=True, use_container_width=True)
            actions[3].button("공유 ZIP", disabled=True, use_container_width=True)

        actions[4].button("결과 폴더", disabled=True, use_container_width=True)

        st.dataframe(catalog, hide_index=True, width="stretch")

    return planned_off, planned_vlan


def render_diff_details(planned_off: bool, planned_vlan: bool) -> None:
    st.markdown("### 변경 상세")
    if not r.summary:
        st.info("비교 완료 후 변경된 항목과 Before / After를 표시합니다.")
        return

    sev = severity_metrics()
    cards = st.columns(4)
    for col, key, label in zip(
        cards,
        ("Critical", "Warning", "Info", "Unchanged"),
        ("긴급", "주의", "정보", "변경없음"),
        strict=True,
    ):
        col.metric(label, sev[key])

    cls = classification_metrics()
    st.caption(
        f"계획 일치 {cls['Expected']} · 비계획 변화 {cls['Unexpected']} · "
        f"확인 불가 {cls['Unknown']}"
    )

    if r.options != (planned_off, planned_vlan):
        st.warning(
            "현재 계획 변경 선택과 마지막 비교 조건이 다릅니다. "
            "선택 항목 비교를 다시 실행하면 분류가 갱신됩니다."
        )

    filters = st.columns([1.2, 2.8, 1])
    view = filters[0].selectbox(
        "보기",
        ["문제", "전체", "Critical", "Warning", "Info", "Unchanged", "Unknown"],
    )
    search = filters[1].text_input("검색")
    filters[2].button("초기화", disabled=True, use_container_width=True)

    def include(row: dict[str, object]) -> bool:
        if search and search.casefold() not in str(row).casefold():
            return False
        if view == "전체":
            return True
        if view == "문제":
            return (
                row["Severity"] in {"Critical", "Warning", "Unknown"}
                or row["Classification"] == "Unexpected"
            )
        return view in {row["Severity"], row["Classification"]}

    rows = [row for row in r.rows if include(row)]
    table = [
        {
            "등급": row["Severity"],
            "장비": row["Device"],
            "명령": row["Command"],
            "판단": row["Finding"],
            "유형": row["Classification"],
            "라인": row["Changes"],
            "변경 내용": row["Finding"],
        }
        for row in rows
    ]
    st.dataframe(table, hide_index=True, width="stretch")

    if not rows:
        st.caption("필터 조건에 맞는 변경 항목이 없습니다.")
        return

    selected = st.selectbox(
        "선택 변경 행",
        range(len(rows)),
        format_func=lambda index: (
            f"{rows[index]['Severity']} · {rows[index]['Device']} · "
            f"{rows[index]['Command']}"
        ),
    )
    row = rows[selected]
    item = r.summary.items[row["Index"]]

    st.markdown(
        '<div class="section-note"><b>선택 변경 맥락</b><br>'
        f"{item.finding_title or item.summary}<br>"
        f"영향: {item.impact_reason}<br>"
        f"권장 조치: {item.action_hint}</div>",
        unsafe_allow_html=True,
    )

    if item.changed_lines:
        st.dataframe(
            [asdict(line) for line in item.changed_lines],
            hide_index=True,
            width="stretch",
        )

    before, after = st.columns(2)
    with before:
        st.markdown("**기준 원본**")
        st.code(row["Before"], language="text")
    with after:
        st.markdown("**비교 원본**")
        st.code(row["After"], language="text")

    with st.expander("선택 상세 텍스트", expanded=False):
        st.write(f"Evidence: {item.evidence}")
        st.write(f"분류: {row['Classification']}")
        st.write(f"등급: {row['Severity']}")

    if r.html and st.checkbox("최근 HTML 리포트 미리보기"):
        components.html(r.html, height=650, scrolling=True)


def render_compare_page() -> None:
    global trace_slot
    controls_area = st.container()
    trace_slot = st.empty()
    r.execution.on_change = lambda: render_trace(r.execution, trace_slot)
    render_trace(r.execution, trace_slot)
    with controls_area:
        planned_off, planned_vlan = render_compare_controls()
    render_diff_details(planned_off, planned_vlan)


def render_logs_page() -> None:
    global trace_slot
    trace_slot = st.empty()
    r.execution.on_change = lambda: render_trace(r.execution, trace_slot)
    render_trace(r.execution, trace_slot)
    st.markdown("### 작업 로그")
    st.markdown(
        '<div class="section-note"><b>실행 이력</b><br>'
        "수집 시작, 설정 오류, 비교 완료, 리포트 생성 위치를 시간 순서로 남깁니다. "
        "실제 제품은 민감 정보를 로그 저장 전에 마스킹합니다.</div>",
        unsafe_allow_html=True,
    )
    if r.logs:
        st.dataframe(r.logs, hide_index=True, width="stretch")
    else:
        st.info(
            "준비 완료. 장비 정보와 접속 계정을 확인한 뒤 작업 단계별 상태를 수집하세요."
        )


def start_scenario(key):
    global r
    begin()
    old = r
    runner = ScenarioRunner()
    st.session_state.scenario_runner = runner

    def update(current):
        render_timeline(current, timeline_slot)
        render_business_trace(current.runtime, public_trace_slot)

    try:
        runner.play(key, update)
    except Exception as exc:
        st.error(f"검증을 완료하지 못했습니다: {exc}")
    r = runner.runtime
    st.session_state.runtime = r
    old.close()


st.title("Network Change Validator")
st.write(
    "네트워크 작업 전·후 상태를 자동 비교해 작업이 정상적으로 끝났는지 확인합니다."
)
st.caption(
    "HPE Comware Change Validator · Public Web Edition · 비식별 합성 데이터 · 실제 장비 변경 없음"
)
controls = st.container()
timeline_slot = GuidedSlot(
    st.empty(), lambda: getattr(st.session_state.get("scenario_runner"), "run", None)
)
result_slot = st.container()
with st.expander("실제 처리 기록 / Execution Trace", expanded=False):
    public_trace_slot = st.empty()
with st.expander("판단 근거 / 주요 확인 항목", expanded=False):
    findings_slot = st.container()
with controls:
    chosen = None
    if st.button(
        "▶ 대표 네트워크 작업 검증 보기", type="primary", use_container_width=True
    ):
        chosen = "representative"
    st.caption("다른 시나리오")
    for col, (key, label) in zip(st.columns(3), list(SCENARIOS.items())[1:]):
        if col.button(label, use_container_width=True):
            chosen = key
    st.write(
        "실제 운영에서는 네트워크 작업 전후에 여러 장비의 상태를 사람이 다시 확인해야 합니다. 이 프로그램은 작업 전 상태를 기준으로 저장하고 작업 후 상태와 자동 비교해 확인이 필요한 항목을 보여줍니다."
    )
    if chosen:
        start_scenario(chosen)

runner = st.session_state.get("scenario_runner")
render_timeline(runner, timeline_slot)
with result_slot:
    render_result(r, st)
    if r.html:
        actions = st.columns(2)
        actions[0].download_button(
            "HTML 보고서 다운로드",
            r.html,
            "diff_report.html",
            "text/html",
            use_container_width=True,
        )
        actions[1].download_button(
            "ZIP 다운로드",
            r.zip_bytes,
            "change-validation-share.zip",
            "application/zip",
            use_container_width=True,
        )
        with st.expander("HTML 보고서 보기"):
            components.html(r.html, height=650, scrolling=True)
render_business_trace(r, public_trace_slot)
with findings_slot:
    render_findings(r, st)
with st.expander("기술 상세 / 직접 조작", expanded=False):
    st.caption(
        "기존 전문가용 화면 · 직접 수집/비교를 실행하면 시나리오 기록을 닫고 현재 작업을 이어갑니다."
    )
    render_sidebar()
    render_topbar()
    if st.session_state.comware_page == "장비 설정":
        render_settings_page()
    elif st.session_state.comware_page == "비교 결과":
        render_compare_page()
    else:
        render_logs_page()

st.caption("Public Web Edition · 실제 장비 접속 없이 공개 합성 입력으로 검증합니다.")
st.link_button(
    "GitHub Source", "https://github.com/sebia1993/hpe-comware-change-validator"
)
r.execution.on_change = None
