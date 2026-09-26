from pathlib import Path
import sys
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_demo.logic import SCENARIOS, run_demo

st.set_page_config(
    page_title="Comware Validator · Public Demo", page_icon="📡", layout="wide"
)
st.title("HPE Comware Change Validator")
st.caption("Pre-change → Post-change · 예상된 변경과 예상하지 못한 변경 비교")
st.info(
    "공개 Demo Mode · 비식별 Snapshot을 기존 SnapshotStore / DiffEngine / expected_changes 규칙으로 분석합니다. 실제 장비 접속·설정 변경·내부 파일 업로드는 없습니다."
)
with st.sidebar:
    st.subheader("Demo Mode")
    st.success("실제 장비 연결: 비활성")
    st.write("분석 / HTML 보고서: 원 프로젝트 코드")
    st.caption(
        "수집 실패는 Unknown입니다. Critical은 합성 관측값에 대한 규칙의 판단입니다."
    )
scenario = st.selectbox("체험 시나리오", list(SCENARIOS), format_func=SCENARIOS.get)
if st.button("분석 실행", type="primary", width="stretch"):
    st.session_state.result = (scenario, run_demo(scenario))
if "result" in st.session_state:
    selected, result = st.session_state.result
    st.subheader(f"결과 · {SCENARIOS[selected]}")
    if selected != scenario:
        st.info("입력이 변경되었습니다. 분석 실행을 눌러 새 결과를 확인하세요.")
    (st.success if result["status"] == "Validation Passed" else st.warning)(
        result["status"]
    )
    for col, (key, value) in zip(st.columns(4), result["counts"].items()):
        col.metric(f"{key} Changes", value)
    filter_value = st.selectbox(
        "결과 필터", ["All", "Expected", "Unexpected", "Warning", "Critical", "Unknown"]
    )
    rows = [
        r
        for r in result["rows"]
        if filter_value == "All" or filter_value in (r["Classification"], r["Severity"])
    ]
    st.dataframe(
        [{k: v for k, v in r.items() if k != "Difference"} for r in rows],
        hide_index=True,
        width="stretch",
    )
    with st.expander("Difference / 근거"):
        for row in rows:
            st.markdown(
                f"**{row['Item']} · {row['Classification']} / {row['Severity']}**"
            )
            st.code(
                row["Difference"] or "변경 없음 / 수집 상태는 결과 표 참조",
                language="diff",
            )
    with st.expander("Raw Data / expected_changes"):
        st.json(result["raw"])
        st.json(result["expected_changes"])
    st.download_button(
        "HTML Report 다운로드", result["html"], "comware-demo.html", "text/html"
    )
    with st.expander("HTML Report Preview"):
        st.caption(
            "수집 실패는 HTML에서도 Unknown으로 분리합니다. 확인 불가 필터에서 수집 오류 근거를 확인할 수 있습니다."
        )
        st.iframe(result["html"], height=650)
with st.expander("Architecture / How It Works"):
    st.write(
        "Fixture CLI → SnapshotStore (임시 디렉터리) → DiffEngine + expected_changes → 원 HTML ReportWriter"
    )
    st.caption(
        "Snapshot 임시 파일은 실행 직후 정리합니다. 결과는 각 브라우저 세션에서만 유지됩니다."
    )
st.link_button(
    "GitHub Source", "https://github.com/sebia1993/hpe-comware-change-validator"
)
