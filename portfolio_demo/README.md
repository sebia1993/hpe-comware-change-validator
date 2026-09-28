# Network Change Validator — Public Demo

**[Live Demo](https://sebia1993-comware-validator-demo.streamlit.app/)** · [GitHub Source](https://github.com/sebia1993/hpe-comware-change-validator)

## 무엇을 보여주는 데모인가

네트워크 작업 전 상태를 저장하고 작업 후 상태와 자동 비교해 **계획된 변화, 비계획 변화, 위험 신호와 수집 실패를 구분하는 변경 검증 도구**입니다.

대표적인 사용 상황은 다음과 같습니다.

> 백본 작업이 끝났는데 Interface, LACP, OSPF, VRRP, CPU/Memory 상태가 작업 전과 동일하게 복구됐는지 빠르게 확인해야 합니다.

이 도구는 여러 장비의 수십 개 조회 명령을 Snapshot으로 묶어 저장한 뒤 동일 장비·명령 기준으로 자동 비교합니다.

## 가장 빠르게 보는 방법

1. Live Demo를 엽니다.
2. **샘플 변경 검증 1-click**을 누릅니다.
3. 상단의 자연어 **결론**에서 긴급/주의/계획/비계획/확인 불가 건수를 먼저 봅니다.
4. `3. Validation`에서 어떤 장비의 어떤 상태가 왜 바뀌었는지 확인합니다.
5. 상세 항목에서 Before / After, 영향, Evidence와 권장 조치를 확인합니다.
6. 필요하면 `4. Report`에서 HTML 또는 Share ZIP을 내려받습니다.

## 용어

- **Snapshot**: 특정 시점의 장비 상태 명령 결과를 묶어 저장한 기준 자료
- **Expected**: 변화가 작업 계획과 일치한다는 의미. Critical/Warning 등급 자체를 숨기지 않음
- **Unexpected**: 작업 계획에 없던 변화로 추가 확인이 필요한 항목
- **Unknown**: CLI 수집 실패 등으로 정상/이상을 판단할 근거가 부족한 항목

Public Demo의 fixture_collector는 합성 CommandResult만 제공합니다. Snapshot 저장, 구조화 비교, Expected/Unexpected 분류와 보고서 생성은 production `SnapshotStore`, `DiffEngine`, `ExpectedChangeRule`, `ReportWriter`를 사용합니다.

## 직접 실행

```sh
python -m pip install -r portfolio_demo/requirements.txt
python -m streamlit run portfolio_demo/app.py
python -m unittest portfolio_demo.test_demo
```

자동 Mock/CI 결과와 실제 장비·현장 검증은 같은 증거 수준으로 표현하지 않습니다.
