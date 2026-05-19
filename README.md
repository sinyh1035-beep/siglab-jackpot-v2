# SIGVIEW 잭팟 도구 시즌2

경기민감주(Cyclical) 슈퍼사이클의 c자리(기러기 자리)를 자동 검출하는 패턴 매칭 도구.

> **시즌1과 완전 분리** — 기존 SSS+골든 9종목은 그대로 라이브 유지, 시즌2는 별도 시스템.

## 핵심 알고리즘 (MFAS v2)

```
f(x) - g(x) = k(x - a)(x - b)(x - c)²
```
- **a, b**: 단순근 (큰 사이클의 고점/저점)
- **c (이중근)**: 기러기 자리 — 마지막 눌림 후 폭발 직전
- **다중 프레임 일치**: 일봉/주봉/월봉에서 동시에 c자리 검출되면 강신호
- **시간 일치 제약**: 일+주 ≤6개월, 주+월 ≤12개월

## 별점

| 등급 | 조건 | 의미 |
|---|---|---|
| ★★★★★ | 일+주+월 3프레임 동시 (≤12m) | 슈퍼잭팟 신호 (희귀) |
| ★★★★ | 2프레임 시간 일치 | 강한 잭팟 후보 |
| ★★★ | 1프레임 단독 | 보조 신호 |

## 검증 케이스 (백테스트 입증)

- 한미반도체 ★★★★ 주+월 → **+783%/+663%**
- 에코프로 ★★★★ 일+주 → **+464%/+431%**
- SK하이닉스 ★★★★ 일+주 → **+602%/+489%**
- 풍산 ★★★★ 일+주 (시간차 0일!) → **+266%/+276%**

## 파일 구조

```
season2/
├── jackpot_v2_backend.py      # 백엔드 스캔 스크립트 (pykrx 기반)
├── jackpot-v2.json            # 매일 자동 업데이트되는 결과 데이터
├── jackpot-v2.html            # 운영 페이지 (siglab.kr/tools-jackpot-v2)
├── README.md
└── .github/
    └── workflows/
        └── jackpot-v2-update.yml  # 매일 자정 자동 실행
```

## 배포 절차

### 1. GitHub 저장소 생성
- 새 저장소: `siglab-jackpot-v2` (또는 원하는 이름)
- 위 파일들 그대로 푸시

### 2. GitHub Actions 활성화
- 저장소 Settings → Actions → 'Allow all actions' 체크
- `Settings → Actions → General → Workflow permissions` → **Read and write permissions** 체크 (JSON 자동 커밋용)

### 3. 첫 수동 실행
- Actions 탭 → `jackpot-v2-update` → `Run workflow`
- 10~30분 후 `jackpot-v2.json` 자동 생성/업데이트 확인

### 4. siglab.kr 페이지 연동
- **옵션 A (GitHub Pages):** 저장소 Settings → Pages 활성화 → `https://<유저>.github.io/<저장소>/jackpot-v2.html` 접속
- **옵션 B (Gabia 호스팅):** `jackpot-v2.html` + `jackpot-v2.json` 두 파일을 siglab.kr 호스팅 `/tools-jackpot-v2/` 경로에 업로드. JSON은 매일 GitHub에서 다운로드해 덮어쓰는 cron 또는 수동 동기화 필요
- **옵션 C (WordPress 고정 페이지):** 새 페이지 슬러그 `tools-jackpot-v2`, 본문에 `<iframe>` 또는 HTML 직접 삽입

### 5. 사이트맵 분리
- 시즌1 sitemap.xml과 별도로 시즌2 페이지만 포함하는 `sitemap-jackpot-v2.xml` 생성 권장
- 또는 기존 sitemap에 `/tools-jackpot-v2/` URL 추가

## 종목 풀 (현재 41개 경기민감주)

반도체 / 2차전지 / 자동차 / 조선 / 철강·비철 / 화학·정유 / 건설 / 해운·항공 / 방산 / 풍력·원자력 / 중공업

**확장 시:** `jackpot_v2_backend.py`의 `CYCLICAL` 딕셔너리에 추가만 하면 됨.

## 주의사항

- pykrx는 KRX 정보데이터시스템에 접근. GitHub Actions(Ubuntu) 환경에서 정상 동작.
- 로컬 테스트 시 KRX 접근 제한 가능 — yfinance fallback 버전(`jackpot_v2_mfas_v2.py`)으로 시뮬레이션 가능.
- 별점은 통계적 신호일 뿐 — 매수 신호 아님. 분산 투자 원칙 준수.

---

**버전:** 2.0  
**알고리즘:** MFAS v2 (Multi-Frame Alignment Score)  
**철학:** 형(주니아범)의 4차함수 직관 + 통계적 검증
