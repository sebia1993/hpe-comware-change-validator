import sys
from pathlib import Path
from dataclasses import asdict
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_demo.runtime import DemoRuntime
from portfolio_demo.fixture_collector import DEVICES, COMMANDS
from core.workflow import WORK_STAGE_NAMES, CUSTOM_STAGE

st.set_page_config(
    page_title="Comware Change Console · Public Demo v2", page_icon="🔎", layout="wide"
)
if "runtime" not in st.session_state:
    st.session_state.runtime = DemoRuntime()
r = st.session_state.runtime
st.title("Comware Change Console")
st.caption("Public Demo v2 · 합성 CLI → 실제 SnapshotStore → DiffEngine → ReportWriter")
with st.sidebar:
    st.success("Read-only · 실제 SSH 비활성")
    st.caption("브라우저 세션별 임시 저장소 · 최대 Snapshot 20개 · 계정 입력 없음")
    if st.button("Demo Reset"):
        r.close()
        st.session_state.runtime = DemoRuntime()
        st.rerun()
setup, workspace, results, reports, logs = st.tabs(
    ["장비 / Preflight", "작업 / Snapshot", "비교 결과", "보고서", "작업 로그"]
)
with setup:
    st.subheader("장비 설정")
    st.dataframe([asdict(d) for d in DEVICES], hide_index=True)
    st.caption(
        f"읽기 전용 명령 {len(COMMANDS)}개 · 문서용 IP에 대한 Preflight 주의는 의도된 설정입니다."
    )
    with st.expander("Command Set"):
        st.dataframe([asdict(c) for c in COMMANDS], hide_index=True)
    if st.button("설정 점검"):
        r.check()
    if r.preflight:
        st.write(f"오류 {r.preflight.error_count} · 주의 {r.preflight.warning_count}")
        st.dataframe([asdict(i) for i in r.preflight.issues], hide_index=True)
with workspace:
    st.subheader("작업 단계별 상태 수집")
    stage = st.selectbox("작업 단계", WORK_STAGE_NAMES)
    label = st.text_input(
        "사용자 지정 단계명", disabled=stage != CUSTOM_STAGE, max_chars=60
    )
    vlan = resource = timeout = False
    if stage == CUSTOM_STAGE:
        st.caption(
            "합성 장비에 적용할 관측값입니다. 계획 변경 등록은 아래에서 별도로 지정합니다."
        )
        vlan = st.checkbox("VLAN 20 / Description 변경 적용")
        resource = st.checkbox("CPU 사용률 85% 적용")
        timeout = st.checkbox("BB3 OSPF CLI 수집 실패")
    st.caption(
        "백본3 OFF 중: BB3 응답 없음(Unknown), BB4에서 링크·LACP·OSPF·VRRP 변화 관측. 복구 후: 초기 CLI로 복귀."
    )
    planned_off = st.checkbox("BB3 OFF 영향을 계획된 변경으로 등록")
    planned_vlan = st.checkbox("VLAN / Description을 계획된 변경으로 등록")
    if st.button("상태 수집 시작", type="primary", disabled=len(r.catalog) >= 20):
        r.capture(
            stage,
            label if stage == CUSTOM_STAGE else "",
            planned_off=planned_off,
            planned_vlan=planned_vlan,
            vlan=vlan,
            resource=resource,
            timeout=timeout,
        )
    if r.catalog:
        catalog = r.snapshot_rows()
        st.dataframe(catalog, hide_index=True, width="stretch")
        st.caption(
            "자동 기준: "
            + (
                f"#{r.baseline + 1}"
                if r.baseline is not None
                else "없음 · 작업 전을 먼저 수집하세요."
            )
        )
        fmt = lambda i: f"#{i + 1} {catalog[i]['Label']}"
        base = st.selectbox(
            "기준 Snapshot", range(len(catalog)), index=r.baseline or 0, format_func=fmt
        )
        target = st.selectbox(
            "비교 Snapshot",
            range(len(catalog)),
            index=len(catalog) - 1,
            format_func=fmt,
        )
        if st.button("선택 항목 비교"):
            r.compare(base, target, planned_off, planned_vlan)
with results:
    st.subheader("변경 검증 결과")
    if not r.summary:
        st.info(
            "작업 전 수집 후 후속 단계를 수집하거나 Snapshot 두 개를 선택해 비교하세요."
        )
    else:
        st.caption(
            f"분석 Snapshot #{r.pair[0] + 1} → #{r.pair[1] + 1} · 계획 등록: BB3 OFF={r.options[0]}, VLAN={r.options[1]}"
        )
        if r.options != (planned_off, planned_vlan):
            st.warning(
                "계획 변경 설정이 바뀌었습니다. 선택 항목 비교를 눌러 재분석하세요."
            )
        labels = [
            "Critical",
            "Warning",
            "Expected",
            "Unexpected",
            "Unknown",
            "Unchanged",
        ]
        counts = {
            k: sum(
                row["Severity" if k in ("Critical", "Warning") else "Classification"]
                == k
                for row in r.rows
            )
            for k in labels
        }
        st.write(
            "Validation Status: "
            + ("확인 불가 포함" if counts["Unknown"] else "관측 완료")
        )
        for col, name in zip(st.columns(6), labels):
            col.metric(name, counts[name])
        st.caption(
            "Expected는 계획 일치 여부입니다. Critical / Warning 등급은 그대로 유지됩니다."
        )
        selected = st.selectbox("결과 Filter", ["전체", "문제"] + labels)
        search = st.text_input("Device / Command / Finding 검색")
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
            st.write(item.finding_title or item.summary)
            st.write("영향: " + item.impact_reason)
            st.write("Evidence: " + item.evidence)
            st.write("권장 조치: " + item.action_hint)
            st.dataframe([asdict(line) for line in item.changed_lines], hide_index=True)
            before, after = st.columns(2)
            before.code(row["Before"], language="text")
            after.code(row["After"], language="text")
with reports:
    st.subheader("HTML / Share ZIP")
    if r.html:
        st.download_button("HTML Download", r.html, "comware-demo-v2.html", "text/html")
        st.download_button(
            "Share ZIP Download", r.zip_bytes, "comware-demo-v2.zip", "application/zip"
        )
        if st.checkbox("HTML Preview"):
            components.html(r.html, height=650, scrolling=True)
    else:
        st.info("비교 실행 후 보고서를 생성합니다.")
with logs:
    st.dataframe(r.logs, hide_index=True, width="stretch")
st.link_button(
    "원본 프로젝트", "https://github.com/sebia1993/hpe-comware-change-validator"
)
