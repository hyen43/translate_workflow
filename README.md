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

## 관리자용 — Streamlit Community Cloud 배포 (무료)

1. [share.streamlit.io](https://share.streamlit.io) 접속 → GitHub 계정으로 로그인
2. **New app** → 저장소 `hyen43/translate_workflow`, 브랜치 `main`, 메인 파일 `app.py`
3. **Advanced settings → Secrets**에 아래 TOML 붙여넣기 (팀 공용 봇 계정 토큰 권장):

   ```toml
   FIGMA_TOKEN = "..."
   CONFLUENCE_EMAIL = "..."
   CONFLUENCE_TOKEN = "..."
   ANTHROPIC_API_KEY = "..."
   APP_PASSWORD = "..."
   ```

   (최상위 시크릿은 환경변수로도 주입되므로 코드 수정 불필요)

4. **Deploy** → `https://<앱이름>.streamlit.app` 으로 접속 가능

### 운영 메모

- 코드 변경 배포: `main` 브랜치에 push하면 자동 재배포
- 시크릿 변경: 대시보드 → 앱 **Settings → Secrets** 수정 (즉시 반영)
- 로그: 대시보드 → **Manage app**
- 한동안 접속이 없으면 앱이 잠듦 — 방문자가 **"Yes, get this app back up"** 버튼을 누르면 수십 초 내에 깨어남
- 비용: 호스팅 $0 + Claude API 월 $1~3 수준

---

## 폴더 구성

```
app.py                # Streamlit 단일 플로우 UI (비밀번호 게이트 포함)
figma_client.py       # Figma API — Trans* 프레임 텍스트 수집 + 중복 제거
confluence_client.py  # Confluence API — 표 동적 파싱, 컬럼 추가, 단일 PUT 동기화 (409 재시도)
translator.py         # Claude Haiku 번역 배치 (structured outputs + prompt caching)
.env.example          # 필요한 환경변수 목록
WORKFLOW.md           # 상세 레퍼런스 (규칙·정책·트러블슈팅)
PLAN.md               # 전환 계획서
```

## 현재 상태

- ✅ Figma → Confluence 동기화 + Claude 자동 번역 (단일 실행)
- ✅ 기존 표 헤더 동적 인식, 지원 언어 컬럼 추가
- ✅ 중복 제거(공백·대소문자·줄바꿈 무시), PUT 409 자동 재시도
- ✅ 비밀번호 게이트, Streamlit Community Cloud 배포
- ⚠️ Confluence **Cloud** 전용 (Server/Data Center 미지원)
- ⚠️ 지원 언어는 5개 고정: 한국어(필수) + 영어·일본어·중국어(간체)·중국어(번체)
