# Comware Change Console — Public Demo v2

검토 브랜치: `codex/public-demo-v2`. 기존 main / 공개 앱은 변경하지 않습니다.

```sh
python -m pip install -r portfolio_demo/requirements.txt
python -m streamlit run portfolio_demo/app.py
python -m unittest portfolio_demo.test_demo
```

1. 장비 / Preflight에서 설정 점검: 문서용 IP 주의 2건은 의도된 결과입니다.
2. 작업 / Snapshot에서 `작업 전` 수집 → 세션별 실제 Snapshot / 기준 자동 지정.
3. `백본3 OFF 중` 수집 → BB3 CLI 실패는 Unknown, BB4의 링크 / OSPF / VRRP 변화는 production DiffEngine으로 분석.
4. BB3 OFF 계획 등록 후 동일 Snapshot pair 재비교: Expected가 되어도 Critical / Warning은 유지됩니다.
5. `복구 후` 수집 → 최근 작업 전과 자동 비교. 이전 OFF Snapshot을 직접 기준으로 선택할 수도 있습니다.
6. 사용자 지정 단계에서 VLAN / Description, CPU, OSPF 수집 실패 관측값을 적용하고 별도로 계획 변경을 등록합니다.
7. 결과 필터 → 상세 DiffLine / Evidence / Before / After → HTML Preview / Download / production Share ZIP.
8. 작업 로그에서 수집과 비교 이력을 확인합니다. Demo Reset은 해당 세션 임시 저장소를 정리합니다.

`fixture_collector.py`가 CommandResult만 생성합니다. 완성된 비교 결과 fixture는 사용하지 않습니다. 실제 SSH / 계정 / known_hosts는 사용하지 않습니다. production `workflow`, `preflight`, `SnapshotStore`, `DiffEngine`, `ExpectedChangeRule`, `ReportWriter`, `create_share_report_bundle`을 재사용합니다.

기준 또는 대상 CLI가 없으면 Public Demo adapter에서 Unknown으로 표시하고 삭제/복구를 추정하지 않습니다. Snapshot 20개, 로그 200건으로 제한하며 보고서는 현재 비교만 보관합니다. 브라우저별 TemporaryDirectory는 Reset 또는 세션 객체 해제 시 정리됩니다. 프로세스 강제 종료 시 OS 임시 파일 정리 정책이 적용됩니다.

Windows 자동 검증과 합성 데이터 검증은 실제 장비 검증을 의미하지 않습니다. v2의 공개 배포는 main 반영 전에 별도 검토합니다.
