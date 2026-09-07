# 포트폴리오 검토 안내: 변경 전후 상태의 운영 의미

이 프로젝트에서 검토할 역량은 **변경 작업 전후의 상태를 구조화하고, 수집 실패·계획된 변화·추가 확인이 필요한 위험을 구분하는 능력**입니다. 변경 실행 기능은 포함하지 않으며 운영자가 복구 여부를 검토할 근거를 생성합니다.

## 코드로 확인하는 설계 판단

| 검토 질문 | 구현 근거 | 재현 근거 |
|---|---|---|
| 명령 입력이 위험하면 접속 전에 차단하는가? | [command_safety.py](../core/command_safety.py), [collector.py](../core/collector.py) | [test_collection_security.py](../tests/test_collection_security.py)의 `test_unsafe_command_blocks_before_connect_handler` |
| 장비 접속 실패가 수십 개 명령 장애로 부풀려지는가? | [connectivity.py](../core/connectivity.py), [diff_engine.py](../core/diff_engine.py) | [test_diff_engine.py](../tests/test_diff_engine.py)의 `test_unreachable_target_device_is_single_critical_connectivity_item` |
| 작업 계획에 포함된 OFF와 복구를 구분하는가? | [analysis_rules.py](../core/analysis_rules.py), [analysis_rules.yaml](../config/analysis_rules.yaml) | 같은 테스트 파일의 `test_expected_stage_change_marks_backbone3_off_connectivity_failure`, `test_restored_target_device_is_info_without_added_command_noise` |
| 출력이 변하지 않아도 자원 임계 상태를 발견하는가? | [diff_engine.py](../core/diff_engine.py)의 상태 판정 | `test_cpu_usage_critical_even_when_output_is_unchanged`, `test_memory_free_ratio_critical_even_when_output_is_unchanged` |
| 입력에서 공유 가능한 보고서까지 재현되는가? | [mock_validation.py](../core/mock_validation.py), [snapshot.py](../core/snapshot.py), [reporter.py](../core/reporter.py) | [test_mock_validation.py](../tests/test_mock_validation.py)의 3개 스냅샷·HTML·공유 ZIP 검증 |

비교 결과에서 `expected`는 작업 계획에 등록된 변화라는 뜻입니다. 심각도를 지우거나 서비스 정상 여부를 보증하는 값으로 해석하지 않습니다. 상태 판정·임계값의 상세 기준은 [변경 검증 로직](CHANGE_VALIDATION_LOGIC.md)에 있습니다.

## 장비 없이 테스트 재현하기

Windows PowerShell과 Python 3.12에서 시작합니다. 테스트 import 경로가 `backbone_state_tracker`이므로 **clone 디렉터리명을 아래처럼 지정**합니다. CI도 동일한 디렉터리명을 사용합니다. 이미 clone했다면 별도 검토용 경로에 이 절차를 적용할 수 있습니다.

```powershell
git clone https://github.com/sebia1993/hpe-comware-change-validator.git backbone_state_tracker
cd backbone_state_tracker
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-windows.lock
$env:PYTHONPATH=(Split-Path (Get-Location) -Parent)
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_mock_validation.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_diff_engine.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_collection_security.py -v
```

첫 테스트는 합성 데이터를 임시 디렉터리에 저장하고 보고서까지 검사한 뒤 정리합니다. 실제 장비의 전원을 내리거나 SSH로 접속하는 절차가 아닙니다. 보존되는 화면·보고서를 보고 싶다면 `.\.venv\Scripts\python.exe app.py`로 GUI를 열고 **샘플 검증 생성**을 사용합니다. [사용자 가이드](USER_GUIDE.md)의 샘플 검증 흐름으로 이어집니다.

## 결과를 읽을 때 확인할 사례

1. **기준 → 백본 OFF 샘플:** 해당 장비의 `device_connectivity` 결과는 하나로 묶이고, 관측 가능한 상대 장비의 링크·LACP·라우팅 변화는 별도로 나타나는지 확인합니다.
2. **OFF → 복구 샘플:** 접속 복구가 표시되며 모든 명령이 새로 생겼다는 중복 경고를 만들지 않는지 확인합니다.
3. **기준 → 최종 샘플:** 계획된 변경 표시 외에 남은 위험 신호를 확인합니다. 샘플의 복구 결과가 현장 서비스 복구를 증명하지는 않습니다.

## 검증 근거와 남은 범위

- [Windows 검증 실행](https://github.com/sebia1993/hpe-comware-change-validator/actions/workflows/pr-build.yml)에서 검토한 커밋 SHA의 완료 결과를 확인합니다. [워크플로 정의](../.github/workflows/pr-build.yml)는 Python 3.12 테스트·GUI/Web smoke·보안 검사·Windows 통합 ZIP·자산 검증을 연결합니다.
- [Releases](https://github.com/sebia1993/hpe-comware-change-validator/releases)의 ZIP을 검토할 때는 태그·source commit·checksum·manifest·SBOM을 함께 대조합니다. 생성된 CI 후보 artifact와 공개 Release는 별개입니다.
- [검증 보고서](VALIDATION_REPORT.md)에 정의된 실제 펌웨어 출력, 조직별 임계값, 수동 점검 결과와의 일치, 현장 변경관리 절차는 별도 검증이 필요합니다.
- 접속 실패를 장비 장애의 원인으로 확정하거나, OSPF·VRRP 변화만으로 전체 서비스 영향을 단정하지 않습니다. [보안 정책](../SECURITY.md)의 호스트 키·의존성 예외도 검토 범위에 포함합니다.

이 포트폴리오의 설명 초점은 변경 명령을 많이 자동화했다는 주장이 아니라 **관측 가능한 상태와 관측 실패를 나누고 복구 확인을 빠뜨리지 않도록 만든 설계**입니다.
