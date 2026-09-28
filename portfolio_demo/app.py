import sys
from dataclasses import asdict
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.workflow import CUSTOM_STAGE, WORK_STAGE_NAMES
from portfolio_demo.fixture_collector import COMMANDS, DEVICES
from portfolio_demo.runtime import DemoRuntime

st.set_page_config(
    page_title="Comware Change Validation · Public Demo",
    page_icon="🔎",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top:1.5rem; padding-bottom:3rem; max-width:1500px;}
    .product-kicker {font-size:.78rem; letter-spacing:.08em; font-weight:800; color:#7da7ff; margin-bottom:.25rem;}
    .product-title {font-size:2.15rem; line-height:1.1; font-weight:800; margin:0;}
    .product-sub {color:#8a98aa; margin-top:.45rem; margin-bottom:1rem;}
    .demo-badge {display:inline-block; border:1px solid #31445f; border-radius:999px; padding:.22rem .62rem;
                 font-size:.72rem; font-weight:750; color:#afc8ee; background:#101927; margin-right:.35rem;}
    .step-card {border:1px solid rgba(120,145,175,.25); border-radius:12px; padding:.7rem .85rem;
                background:rgba(18,27,41,.55); min-height:78px;}
    .step-no {font-size:.72rem; color:#7da7ff; font-weight:800;}
    .step-title {font-size:.95rem; font-weight:760; margin-top:.15rem;}
    .step-state {font-size:.76rem; color:#8494a8; margin-top:.25rem;}
    .explain-card {
        border:1px solid rgba(120,145,175,.24); border-radius:12px;
        padding:.85rem 1rem; background:rgba(18,27,41,.5); min-height:118px;
    }
    .explain-label {font-size:.72rem; color:#7da7ff; font-weight:800; letter-spacing:.04em;}
    .explain-title {font-size:1rem; font-weight:780; margin:.2rem 0 .35rem;}
    .explain-copy {font-size:.86rem; color:#91a0b3; line-height:1.45;}
    </style>
    """,
    unsafe_allow_html=True,
)

if "runtime" not in st.session_state:
    st.session_state.runtime = DemoRuntime()
r = st.session_state.runtime


def render_header() -> None:
    st.markdown(
        '<div class="product-kicker">NETWORK CHANGE VALIDATION</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="product-title">네트워크 변경 전·후 검증 도구</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="product-sub">네트워크 작업 전 상태를 기준으로 저장하고 작업 후와 자동 비교해 '
        '계획된 변화, 위험 신호와 수집 실패를 구분합니다.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span class="demo-badge">PUBLIC DEMO</span>'
        '<span class="demo-badge">SYNTHETIC CLI</span>'
        '<span class="demo-badge">READ ONLY</span>',
        unsafe_allow_html=True,
    )



def render_explainer() -> None:
    st.markdown("### 이 도구는 무엇을 해결하나요?")
    cols = st.columns(3)
    cards = (
        (
            "현업 문제",
            "작업 후 수십 개 상태를 재확인",
            "백본 작업 뒤 Interface, LACP, OSPF, VRRP, CPU 같은 상태를 사람이 다시 비교하면 "
            "누락과 판단 편차가 생길 수 있습니다.",
        ),
        (
            "자동화 방식",
            "Pre / Post Snapshot 자동 비교",
            "작업 전 상태를 기준 Snapshot으로 저장하고, 작업 후 동일 장비·명령 결과를 구조화해 "
            "무엇이 바뀌었는지 자동으로 찾습니다.",
        ),
        (
            "운영 결과",
            "위험 / 계획 / 확인 불가 분류",
            "변화를 단순 diff로 끝내지 않고 Critical, Warning, Expected, Unexpected, Unknown으로 "
            "나눠 우선 확인 대상을 보여줍니다.",
        ),
    )
    for col, (label, title, copy) in zip(cols, cards):
        col.markdown(
            '<div class="explain-card">'
            f'<div class="explain-label">{label}</div>'
            f'<div class="explain-title">{title}</div>'
            f'<div class="explain-copy">{copy}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    st.info(
        "예시: 백본 장비 OFF 작업 후 링크·LACP·OSPF·VRRP 변화가 계획과 일치하는지, "
        "수집 실패 때문에 확인할 수 없는 항목은 없는지를 작업 전 상태와 자동 비교합니다."
    )
    c = st.columns([1.45, 3.55])
    if c[0].button(
        "▶ 샘플 변경 검증 1-click",
        type="primary",
        use_container_width=True,
    ):
        demo = DemoRuntime()
        demo.check()
        demo.capture("작업 전")
        demo.capture("백본3 OFF 중")
        st.session_state.runtime = demo
        st.rerun()
    c[1].caption(
        "한 번 클릭하면 Pre-Change Snapshot → 작업 중 Snapshot → 자동 비교까지 실행해 "
        "대표 결과를 바로 보여줍니다."
    )

    with st.expander("용어를 쉽게 보기", expanded=False):
        st.write("**Snapshot**: 특정 시점의 장비 상태 명령 결과를 묶어 저장한 기준 자료")
        st.write("**Expected**: 변화가 계획과 일치한다는 뜻이며, Critical/Warning 등급 자체를 숨기지 않음")
        st.write("**Unexpected**: 작업 계획에 없던 변화로 추가 확인이 필요한 항목")
        st.write("**Unknown**: CLI 수집 실패 등으로 정상/이상을 판단할 근거가 부족한 항목")


def result_counts() -> dict[str, int]:
    if not r.summary:
        return {}
    labels = ["Critical", "Warning", "Expected", "Unexpected", "Unknown", "Unchanged"]
    return {
        key: sum(
            row["Severity" if key in ("Critical", "Warning") else "Classification"] == key
            for row in r.rows
        )
        for key in labels
    }


def render_plain_summary() -> None:
    counts = result_counts()
    if not counts:
        return
    risky = counts["Critical"] + counts["Warning"]
    st.markdown("### 이번 비교에서 무엇을 알 수 있나요?")
    if risky:
        st.warning(
            f"결론: 작업 전 대비 긴급/주의 항목 {risky}건이 확인됐습니다. "
            f"계획된 변화 {counts['Expected']}건, 비계획 변화 {counts['Unexpected']}건, "
            f"수집 부족으로 확인 불가 {counts['Unknown']}건입니다."
        )
    else:
        st.success(
            f"결론: 작업 전 대비 긴급/주의 변화가 확인되지 않았습니다. "
            f"계획된 변화 {counts['Expected']}건, 확인 불가 {counts['Unknown']}건입니다."
        )
    st.caption(
        "상세 근거는 아래 3. Validation 탭에서 Before / After와 함께 확인할 수 있습니다."
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.subheader("Change Workspace")
        st.caption("브라우저 세션마다 임시 작업공간을 사용합니다.")
        st.write(f"**Devices**  {len(DEVICES)}")
        st.write(f"**Read-only commands**  {len(COMMANDS)}")
        st.write("**Snapshot limit**  20")
        st.divider()
        st.caption("실제 SSH/계정/known_hosts는 사용하지 않습니다.")
        if st.button("Demo Reset", use_container_width=True):
            r.close()
            st.session_state.runtime = DemoRuntime()
            st.rerun()


def render_workflow_strip() -> None:
    has_preflight = r.preflight is not None
    has_baseline = r.baseline is not None
    has_post = len(r.catalog) >= 2
    has_compare = r.summary is not None
    states = [
        ("1", "Preflight", "완료" if has_preflight else "대기"),
        ("2", "Pre-Change Snapshot", "완료" if has_baseline else "대기"),
        ("3", "Post-Change Snapshot", "완료" if has_post else "대기"),
        ("4", "Diff / Validation", "완료" if has_compare else "대기"),
    ]
    cols = st.columns(4)
    for col, (no, title, state) in zip(cols, states):
        col.markdown(
            f'<div class="step-card"><div class="step-no">STEP {no}</div>'
            f'<div class="step-title">{title}</div>'
            f'<div class="step-state">{state}</div></div>',
            unsafe_allow_html=True,
        )


def render_preflight() -> None:
    st.subheader("장비 / Preflight")
    c = st.columns([1, 4])
    if c[0].button("설정 점검", type="primary", use_container_width=True):
        r.check()
    c[1].caption(
        "실제 운영에서는 작업 전 장비 목록과 조회 명령을 확인합니다. "
        "Public Demo의 문서용 IP 주의는 의도된 설정입니다."
    )

    if r.preflight:
        x = st.columns(3)
        x[0].metric("Error", r.preflight.error_count)
        x[1].metric("Warning", r.preflight.warning_count)
        x[2].metric("Devices", len(DEVICES))
        st.dataframe([asdict(i) for i in r.preflight.issues], hide_index=True, width="stretch")

    with st.expander("장비 / Command Set", expanded=False):
        st.dataframe([asdict(d) for d in DEVICES], hide_index=True, width="stretch")
        st.dataframe([asdict(c) for c in COMMANDS], hide_index=True, width="stretch")


def render_snapshot_workspace():
    st.subheader("Change Snapshot")
    st.caption(
        "작업 전 기준을 먼저 저장한 뒤 후속 상태를 수집하면 production DiffEngine이 자동 비교합니다."
    )

    stage = st.selectbox("작업 단계", WORK_STAGE_NAMES)
    label = ""
    vlan = resource = timeout = False

    with st.expander("Demo controls · 합성 변화/수집 실패 재현", expanded=False):
        st.caption(
            "실제 프로그램의 입력 경로와 분리된 공개 데모용 변화 주입입니다. "
            "기본 흐름은 Pre-Change → Post-Change → 자동 비교입니다."
        )
        label = st.text_input(
            "사용자 지정 단계명",
            disabled=stage != CUSTOM_STAGE,
            max_chars=60,
        )
        if stage == CUSTOM_STAGE:
            vlan = st.checkbox("VLAN 20 / Description 변경 적용")
            resource = st.checkbox("CPU 사용률 85% 적용")
            timeout = st.checkbox("BB3 OSPF CLI 수집 실패")
        st.caption(
            "‘백본3 OFF 중’은 BB3 응답 없음(Unknown), BB4 링크/LACP/OSPF/VRRP 변화가 관측되는 합성 작업입니다."
        )

    st.subheader("계획 변경")
    p = st.columns(2)
    planned_off = p[0].checkbox(
        "BB3 OFF 영향을 계획된 변경으로 등록",
        help="계획 일치 여부만 Expected로 분류하며 Critical/Warning 등급 자체는 유지합니다.",
    )
    planned_vlan = p[1].checkbox(
        "VLAN / Description을 계획된 변경으로 등록",
        help="사용자 지정 단계에서 VLAN/Description 변경을 계획된 변경으로 분류합니다.",
    )

    c = st.columns([1.2, 4])
    capture = c[0].button(
        "상태 수집 시작",
        type="primary",
        disabled=len(r.catalog) >= 20,
        use_container_width=True,
    )
    c[1].caption(
        "조회 전용 합성 CLI를 수집해 실제 SnapshotStore에 저장합니다. "
        "작업 전 Snapshot이 있으면 후속 Snapshot은 자동으로 비교됩니다."
    )
    if capture:
        try:
            r.capture(
                stage,
                label if stage == CUSTOM_STAGE else "",
                planned_off=planned_off,
                planned_vlan=planned_vlan,
                vlan=vlan,
                resource=resource,
                timeout=timeout,
            )
        except ValueError as exc:
            st.error(str(exc))

    if not r.catalog:
        st.info("Snapshot이 없습니다. ‘작업 전’을 선택해 Pre-Change 기준부터 수집하세요.")
        return planned_off, planned_vlan

    catalog = r.snapshot_rows()
    st.dataframe(catalog, hide_index=True, width="stretch")
    st.caption(
        "자동 기준: "
        + (f"#{r.baseline + 1}" if r.baseline is not None else "없음 · 작업 전을 먼저 수집하세요.")
    )

    fmt = lambda i: f"#{i + 1} {catalog[i]['Label']}"
    base = st.selectbox(
        "기준 Snapshot",
        range(len(catalog)),
        index=r.baseline or 0,
        format_func=fmt,
    )
    target = st.selectbox(
        "비교 Snapshot",
        range(len(catalog)),
        index=len(catalog) - 1,
        format_func=fmt,
    )
    if st.button("선택 항목 비교"):
        r.compare(base, target, planned_off, planned_vlan)

    return planned_off, planned_vlan


def render_results(planned_off: bool, planned_vlan: bool) -> None:
    st.subheader("변경 검증 결과")
    if not r.summary:
        st.info("Pre-Change와 Post-Change Snapshot이 준비되면 비교 결과가 이곳에 표시됩니다.")
        return

    st.caption(
        f"분석 Snapshot #{r.pair[0] + 1} → #{r.pair[1] + 1} · "
        f"계획 등록: BB3 OFF={r.options[0]}, VLAN={r.options[1]}"
    )
    if r.options != (planned_off, planned_vlan):
        st.warning("계획 변경 설정이 바뀌었습니다. ‘선택 항목 비교’를 눌러 재분석하세요.")

    labels = ["Critical", "Warning", "Expected", "Unexpected", "Unknown", "Unchanged"]
    counts = result_counts()
    st.write(
        "**Validation Status:** "
        + ("확인 불가 포함" if counts["Unknown"] else "관측 완료")
    )
    for col, name in zip(st.columns(6), labels):
        col.metric(name, counts[name])
    st.caption("Expected는 계획 일치 여부입니다. Critical / Warning 등급은 그대로 유지됩니다.")

    c = st.columns([1, 2])
    selected = c[0].selectbox("결과 Filter", ["전체", "문제"] + labels)
    search = c[1].text_input("Device / Command / Finding 검색")
    rows = [
        row
        for row in r.rows
        if (
            selected == "전체"
            or (
                selected == "문제"
                and (
                    row["Severity"] in ("Critical", "Warning", "Unknown")
                    or row["Classification"] == "Unexpected"
                )
            )
            or selected in (row["Severity"], row["Classification"])
        )
        and search.lower() in str(row).lower()
    ]
    st.dataframe(
        [{k: v for k, v in row.items() if k != "Index"} for row in rows],
        hide_index=True,
        width="stretch",
    )

    if rows:
        detail = st.selectbox(
            "변경 상세",
            range(len(rows)),
            format_func=lambda i: rows[i]["Device"] + " / " + rows[i]["Command"],
        )
        row = rows[detail]
        item = r.summary.items[row["Index"]]
        st.markdown(f"### {item.finding_title or item.summary}")
        a, b, c = st.columns(3)
        a.info("**영향**\n\n" + item.impact_reason)
        b.info("**Evidence**\n\n" + item.evidence)
        c.info("**권장 조치**\n\n" + item.action_hint)
        if item.changed_lines:
            st.dataframe([asdict(line) for line in item.changed_lines], hide_index=True)
        before, after = st.columns(2)
        with before:
            st.markdown("**Before**")
            st.code(row["Before"], language="text")
        with after:
            st.markdown("**After**")
            st.code(row["After"], language="text")


def render_reports() -> None:
    st.subheader("보고서 / 공유")
    if not r.html:
        st.info("비교 실행 후 HTML Report와 Share ZIP을 생성합니다.")
        return
    c = st.columns(2)
    c[0].download_button(
        "HTML Download",
        r.html,
        "comware-demo-v2.html",
        "text/html",
        use_container_width=True,
    )
    c[1].download_button(
        "Share ZIP Download",
        r.zip_bytes,
        "comware-demo-v2.zip",
        "application/zip",
        use_container_width=True,
    )
    if st.checkbox("HTML Preview"):
        components.html(r.html, height=650, scrolling=True)


def render_logs() -> None:
    st.subheader("작업 로그")
    if not r.logs:
        st.info("아직 작업 이력이 없습니다.")
        return
    st.dataframe(r.logs, hide_index=True, width="stretch")


render_header()
render_explainer()
render_sidebar()
render_workflow_strip()
render_plain_summary()

preflight, snapshots, results, reports, logs = st.tabs(
    ["1. Preflight", "2. Snapshot", "3. Validation", "4. Report", "작업 로그"]
)
with preflight:
    render_preflight()
with snapshots:
    planned_off, planned_vlan = render_snapshot_workspace()
with results:
    render_results(planned_off, planned_vlan)
with reports:
    render_reports()
with logs:
    render_logs()

with st.expander("Architecture", expanded=False):
    st.write(
        "Synthetic CommandResult → production SnapshotStore → DiffEngine → "
        "ExpectedChangeRule → ReportWriter → Share ZIP"
    )
    st.caption(
        "완성된 비교 결과 fixture를 표시하지 않습니다. Public Demo adapter는 합성 CLI 결과만 공급하며 "
        "Snapshot, Diff, Expected/Unexpected 분류와 보고서는 production 코드를 재사용합니다."
    )
st.link_button(
    "GitHub Source",
    "https://github.com/sebia1993/hpe-comware-change-validator",
)
