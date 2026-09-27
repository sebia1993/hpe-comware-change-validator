# Public Demo v2 구현 계획 — HPE Comware Change Validator

## 목적

현재 `portfolio_demo`는 미리 준비된 `snapshots.json` 시나리오 하나를 선택하면 production `SnapshotStore → DiffEngine → ReportWriter`를 실행한다. 엔진 재사용은 적절하지만 원본 프로그램의 실제 작업 흐름인 **장비 설정/Preflight → 작업 단계별 상태 수집 → 기준 Snapshot → 자동 비교 → 변경 상세 → 보고서/로그** 경험이 충분하지 않다.

Public Demo v2는 실제 변경 작업 검증 콘솔처럼 느껴져야 한다.

## 원본 프로그램 실제 흐름

1. 장비 설정에서 대상 장비/접속정보 확인
2. 설정 점검(Preflight)
3. `작업 전` 상태 수집
4. 기준 Snapshot 자동 지정
5. 네트워크 작업 수행
6. 후속 단계 상태 수집
   - 백본3 OFF 중
   - 복구 후
   - 사용자 지정 단계
7. 후속 Snapshot을 작업 전 기준과 자동 비교
8. 필요하면 기준/비교 Snapshot을 직접 선택해 재비교
9. 변경점을 Critical/Warning/Info/Unchanged와 Expected/Unexpected로 확인
10. 선택 변경의 Before/After/원본 근거 확인
11. HTML report / Share ZIP 확인
12. 작업 로그에서 전체 실행 이력 확인

Public Demo도 이 순서를 중심으로 구성한다.

## 핵심 원칙

- 실제 SSH는 하지 않는다.
- Public Demo에서 계정 입력을 요구하지 않는다.
- 단순 Scenario selectbox → 결과표 방식이 메인이 되면 안 된다.
- production `SnapshotStore`, `DiffEngine`, `ReportWriter`, `workflow.py`, analysis rules를 재사용한다.
- fixture는 Collector 경계만 대체한다.
- Snapshot이 실제로 생성되고 목록에 쌓이며 기준/대상 선택이 가능해야 한다.
- Expected Change가 Critical/Warning을 무조건 숨기도록 만들지 않는다.
- Collection failure는 Unknown/Connectivity 제한으로 분리한다.

## 1. Demo 장비 설정 / Preflight

비식별 Demo inventory:
- DEMO-BB3
- DEMO-BB4

표시:
- Device Name
- Host
- Enabled
- Device Type
- Command Set

버튼:
- 설정 점검

production preflight validation을 가능한 범위에서 재사용한다.

실제 계정/known_hosts는 public demo에서는 합성 transport로 대체한다.

## 2. 작업 단계별 상태 수집

원본 프로그램과 동일한 중심 UX:
- 작업 단계 선택
  - 작업 전
  - 백본3 OFF 중
  - 복구 후
  - 사용자 지정
- 사용자 지정 단계명
- 상태 수집 시작

`작업 전` 수집:
- production SnapshotStore에 session-local temp workspace로 실제 Snapshot 작성
- 자동 baseline 지정

후속 수집:
- 실제 새로운 Snapshot 작성
- 가장 최근 작업 전 Snapshot과 자동 비교

Public Demo fixture transport는 현재 stage에 따라 CommandResult를 반환한다.
가능하면 `core/mock_validation.py`의 결과 생성기를 그대로 결과로 쓰지 말고, stage별 fixture collector를 두어 **실제 collect→snapshot→compare 흐름**을 재현한다.

## 3. Snapshot Workspace

브라우저 session 안에서 생성된 Snapshot 목록 표시:
- Label
- Stage
- Created
- Device Count
- Collection Status

사용자가:
- 기준 Snapshot 선택
- 비교 Snapshot 선택
- 선택 항목 비교

를 직접 할 수 있어야 한다.

이 부분이 현재 selectbox scenario 데모와 가장 큰 차이다.

## 4. 비교 결과

상단:
- Validation Status
- Critical
- Warning
- Expected
- Unexpected
- Unknown
- Unchanged

Filter:
- 문제
- Critical
- Warning
- Expected
- Unexpected
- Unknown
- Unchanged
- 검색

변경 표:
- Device
- Command/Category
- Classification
- Severity
- Finding
- Before
- After
- Change Count

선택 행 상세:
- 판단 요약
- 영향 이유
- Evidence
- 권장 조치
- line-level diff
- Before raw
- After raw

원본 `DiffItem`, `DiffLine` 의미를 유지한다.

## 5. expected_changes 체험

고정 규칙만 보여주지 말고 사용자가 Demo 범위에서 계획 변경을 선택/토글할 수 있게 한다.

예:
- DEMO-BB3 OFF를 계획된 변경으로 취급
- VLAN/Description 변경을 계획된 변경으로 등록

단, production `ExpectedChangeRule` 구조와 `DiffEngine`을 사용한다.

사용자 선택이 바뀌면 같은 Snapshot pair도 재분석 결과가 달라져야 한다.

## 6. 작업 로그

원본 앱처럼 다음 이벤트를 시간순으로 표시:
- Preflight
- Collect Started
- Snapshot Saved
- Baseline Selected
- Auto Compare
- Manual Compare
- Report Generated
- Collection Error

실제 민감 정보는 없음.

## 7. 보고서

- production `ReportWriter` HTML 생성
- HTML Preview
- HTML Download
- 가능하면 Share ZIP 생성도 production API 재사용

임시 경로는 public HTML에 노출하지 않는다.

## 코드 구조 권장

현재:
- `portfolio_demo/app.py`
- `portfolio_demo/logic.py`
- `portfolio_demo/demo_data/snapshots.json`

개선:
- `portfolio_demo/app.py`: UI
- `portfolio_demo/runtime.py`: session-local workspace/Snapshot catalog/log
- `portfolio_demo/fixture_collector.py`: stage 기반 합성 CommandResult
- `portfolio_demo/logic.py`: production workflow adapter

가능하면 `snapshots.json` 하나에서 완성된 Before/After를 꺼내 비교하는 방식은 제거하거나 fixture source 용도로만 축소한다.

## 테스트

1. Preflight 성공
2. 작업 전 수집 후 baseline 자동 지정
3. 후속 stage 수집 시 새 Snapshot 생성
4. 후속 Snapshot이 작업 전과 자동 비교
5. 수동 baseline/target 재선택 비교
6. No Change
7. Expected Change
8. Unexpected Warning
9. Unexpected Critical
10. Collection failure = Unknown
11. expected_changes 변경 후 동일 Snapshot pair의 classification 변경
12. HTML report 생성
13. session reset 시 temp workspace 정리

## 완료 기준

- 시나리오 하나 고르고 즉시 결과표를 보는 구조에서 벗어남
- 사용자가 실제 변경 작업 순서를 따라 Snapshot을 생성하고 비교
- baseline/target 선택 가능
- production SnapshotStore/DiffEngine/ReportWriter 사용
- expected_changes를 체험 가능
- 상세 line diff/Raw/작업 로그/HTML report 제공
- Streamlit Cloud에서 외부 장비 없이 동작
- 실제 운영정보/계정/known_hosts 미포함
