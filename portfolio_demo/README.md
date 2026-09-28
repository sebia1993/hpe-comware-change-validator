# 백본 상태 추적 콘솔 — Public Web Edition

**[고정 Live URL](https://sebia1993-comware-validator-demo.streamlit.app/)** · [GitHub Source](https://github.com/sebia1993/hpe-comware-change-validator)

이 앱은 별도의 샘플 Lab이 아니라 **Desktop `백본 상태 추적 콘솔`의 Web Edition**입니다.

## Desktop → Web 매핑

| Desktop UI | Public Web Edition |
|---|---|
| 좌측 Navigation | `장비 설정 / 비교 결과 / 작업 로그` Sidebar |
| Topbar 현재 상태 / 기준 / 비교 대상 | 동일 3개 상태 Chip |
| 접속 계정 | Public Demo에서는 비활성 상태로 동일 위치 표시 |
| 대상 장비 표 | 동일 장비명 / IP / Port / Type 표 |
| 작업 단계 / 설정 점검 / 상태 수집 | 동일 작업 흐름 |
| 기준/비교 Snapshot 선택 | 동일 비교 컨트롤 |
| 샘플 검증 생성 | 동일 버튼으로 Public Demo 데이터 생성 |
| 긴급/주의/정보/변경없음 Metric | 동일 결과 Metrics |
| 변경 Tree / 선택 상세 | 변경 표 + 선택 맥락 + Before/After |
| 최근 리포트 / 공유 ZIP | Browser Download로 동일 산출물 제공 |
| 작업 로그 | 동일 실행 이력 페이지 |

Public Web Edition에서는 `fixture_collector.py`가 합성 CommandResult만 제공합니다. Preflight, Snapshot 저장, 구조화 비교, Expected/Unexpected 분류와 ReportWriter는 production 코드를 사용합니다.

Streamlit Community Cloud는 기존 repository `sebia1993/hpe-comware-change-validator`, branch `main`, entrypoint `portfolio_demo/app.py`를 계속 사용합니다. **Live URL은 변경하지 않습니다.**

자동 Mock/CI 결과와 실제 장비·현장 검증은 같은 증거 수준으로 표현하지 않습니다.
