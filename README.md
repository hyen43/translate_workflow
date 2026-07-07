# 번역시트 자동화

> Figma 기획서의 `Trans*` 프레임 텍스트를 Confluence 번역시트에 자동 추가하고, 빈 다국어 셀을 Claude가 채우는 팀 공용 웹 도구입니다.
> 상세 레퍼런스는 [WORKFLOW.md](./WORKFLOW.md), 개발 계획은 [PLAN.md](./PLAN.md) 참고.

---

## 팀원용 — 사용법 (30초)

1. 배포 URL 접속 → 팀 비밀번호 입력
2. **Figma URL** + **Confluence URL** 붙여넣기 → **[표 확인]**
3. 번역할 언어 체크 (영어 · 일본어 · 중국어 간체/번체 — 표에 없는 언어는 "컬럼 추가"로 표시)
4. **[🔄 동기화 + 번역 실행]** → 결과 확인
5. Confluence 페이지에서 최종 검수 (주소·전화·더미 텍스트는 정책상 빈 칸으로 남음)

준비물은 단 두 가지:
- Figma에서 번역할 프레임 이름 앞에 `Trans`를 붙일 것 (예: `Trans홈화면`)
- Confluence 페이지에 **"한국어" 컬럼이 있는 표**가 있을 것

같은 링크로 다시 실행해도 중복 행은 생기지 않습니다 (한국어 기준 자동 중복 제거).

---

## 관리자용 — 로컬 실행

```powershell
pip install -r requirements.txt

# .env 작성 (.env.example 참고)
#   FIGMA_TOKEN / CONFLUENCE_EMAIL / CONFLUENCE_TOKEN / ANTHROPIC_API_KEY
#   APP_PASSWORD 는 로컬에서는 생략 가능 (생략 시 비밀번호 게이트 없이 실행)

streamlit run app.py
```

토큰 발급 방법은 [WORKFLOW.md §토큰 발급](./WORKFLOW.md) 참고.
⚠️ Confluence 토큰은 반드시 **Classic** `Create API token` (Scoped 토큰은 거부됨).

---

## 관리자용 — Fly.io 배포

```powershell
# 1. flyctl 설치 + 로그인
iwr https://fly.io/install.ps1 -useb | iex
flyctl auth login

# 2. 앱 생성 (fly.toml의 앱 이름이 선점됐으면 다른 이름으로 바꾸고 실행)
flyctl apps create translate-sheet-sync

# 3. 시크릿 등록 (팀 공용 봇 계정 토큰 권장)
flyctl secrets set FIGMA_TOKEN=... CONFLUENCE_EMAIL=... CONFLUENCE_TOKEN=... ANTHROPIC_API_KEY=... APP_PASSWORD=...

# 4. 배포 → https://<앱이름>.fly.dev 로 접속 가능
flyctl deploy
```

### 커스텀 도메인 연결 (선택)

```powershell
# 1. 도메인 구입 (Cloudflare, 가비아 등)
# 2. Fly에 인증서 요청
flyctl certs add translate.example.com

# 3. DNS 레코드 추가 (도메인 관리 콘솔에서)
#    서브도메인이면: CNAME  translate  →  <앱이름>.fly.dev
#    루트 도메인이면: flyctl ips list 로 나온 IPv4/IPv6를 A/AAAA 레코드로 등록

# 4. 인증서 발급 확인 (Let's Encrypt 자동 발급, 보통 수 분)
flyctl certs show translate.example.com
```

### 운영 메모

- 시크릿 변경: `flyctl secrets set KEY=...` → 자동 재배포
- 코드 변경 배포: `flyctl deploy`
- 로그: `flyctl logs`
- 비용: 트래픽 없을 때 자동 정지(`min_machines_running = 0`) — 소규모 팀 기준 월 $0~5 + Claude API 월 $1~3 수준

---

## 폴더 구성

```
app.py                # Streamlit 단일 플로우 UI (비밀번호 게이트 포함)
figma_client.py       # Figma API — Trans* 프레임 텍스트 수집 + 중복 제거
confluence_client.py  # Confluence API — 표 동적 파싱, 컬럼 추가, 단일 PUT 동기화 (409 재시도)
translator.py         # Claude Haiku 번역 배치 (structured outputs + prompt caching)
Dockerfile / fly.toml # Fly.io 배포
.env.example          # 필요한 환경변수 목록
WORKFLOW.md           # 상세 레퍼런스 (규칙·정책·트러블슈팅)
PLAN.md               # 전환 계획서
```

## 현재 상태

- ✅ Figma → Confluence 동기화 + Claude 자동 번역 (단일 실행)
- ✅ 기존 표 헤더 동적 인식, 지원 언어 컬럼 추가
- ✅ 중복 제거(공백·대소문자·줄바꿈 무시), PUT 409 자동 재시도
- ✅ 비밀번호 게이트, Fly.io 배포 구성
- ⚠️ Confluence **Cloud** 전용 (Server/Data Center 미지원)
- ⚠️ 지원 언어는 5개 고정: 한국어(필수) + 영어·일본어·중국어(간체)·중국어(번체)
