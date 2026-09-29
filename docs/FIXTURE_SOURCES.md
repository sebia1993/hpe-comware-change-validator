# Public Demo Fixture Sources

이 문서는 Public Web Edition의 합성 CLI fixture가 어떤 HPE 공식 공개 자료의 **출력 형식과 필드 구조**를 참고했는지 기록합니다.

## 원칙

- 실제 사내 운영망의 장비 출력, IP, Hostname, 로그는 사용하지 않습니다.
- 공식 문서의 긴 출력 예제를 그대로 복제하지 않습니다.
- 명령명, 필드 구성, 표 형태, 상태 표현을 참고해 **RFC 문서용 주소와 합성 수치로 재구성**합니다.
- 실제 비교와 판정은 SnapshotStore, DiffEngine, ExpectedChangeRule, ReportWriter production 코드를 사용합니다.

## HPE 공식 자료 매핑

| Public Demo 명령 | 참고한 공식 출력/자료 |
|---|---|
| `display version`, `display device`, `display interface brief` | HPE 5900/5920 Comware 7 ISSU 및 IRF 검증 예제 |
| `display link-aggregation summary`, `display link-aggregation verbose` | HPE Comware Link Aggregation command/configuration examples |
| `display vlan` | HPE Comware Fundamentals의 VLAN display output example |
| `display ospf peer` | HPE Comware OSPF verification/troubleshooting examples |
| `display ip routing-table protocol ospf` | HPE Comware OSPF routing-table verification example |
| `display vrrp verbose` | HPE IPv4 VRRP configuration/verification example |
| `display cpu-usage` | HPE Comware CPU usage command example |
| `display memory` | HPE Comware memory output 및 7500 FreeRatio examples |
| `display fan`, `display environment` | HPE Comware fan/environment status examples |
| `display power`, `display alarm` | HPE Comware power/alarm troubleshooting examples |
| `display logbuffer` | HPE Comware information-center/logbuffer guidance |

## 공식 링크

- https://support.hpe.com/hpesc/public/docDisplay?docId=sf000057387en_us&docLocale=en_US
- https://support.hpe.com/hpesc/public/docDisplay?docId=c03152927&docLocale=en_US
- https://support.hpe.com/hpesc/public/api/document/c05028262
- https://support.hpe.com/hpesc/public/docDisplay?docId=c03444944&docLocale=en_US
- https://support.hpe.com/hpesc/public/docDisplay?docId=c03262720&docLocale=en_US
- https://support.hpe.com/hpesc/public/api/document/c05030686
- https://support.hpe.com/hpesc/public/docDisplay?docId=sf000045635en_us&docLocale=en_US
- https://support.hpe.com/hpesc/public/docDisplay?docId=sf000096307en_us&docLocale=en_US
- https://support.hpe.com/hpesc/public/api/document/c03953856
- https://support.hpe.com/hpesc/public/api/document/c03721509
- https://support.hpe.com/hpesc/public/api/document/c05367111

자료의 제품군과 Comware 릴리스에 따라 세부 출력은 달라질 수 있습니다. Public Demo fixture는 특정 장비의 완전한 원본 출력을 주장하지 않으며, **HPE 공식 Comware 출력 형식을 참고한 비식별 합성 샘플**입니다.
