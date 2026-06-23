# 번역시트 자동화 — 팀 가이드

> Figma 기획서의 한국어 텍스트를 Confluence 번역시트에 자동으로 끌어다 놓고, 빈 다국어 셀은 Claude가 채우는 도구입니다.
> 상세 레퍼런스는 [WORKFLOW.md](./WORKFLOW.md) 를 참고하세요. 이 문서는 **개요 + 앞으로 할 일** 만 다룹니다.

---

## 1. 무엇을 해결하나

| 문제 | 기존 방식 | 이 도구 |
|---|---|---|
| 기획서에 새 용어가 추가됨 | 디자이너가 슬랙으로 알림 → 누가 시트에 옮겨야 함 | Figma 의 `Trans*` 프레임만 만들면 자동 수집 |
| 시트에 같은 용어가 중복으로 들어감 | 사람이 손으로 점검 | 한국어 컬럼 기준 자동 중복 제거 |
| 영어/일/중 번역을 누가 채울지 | 번역 외주 또는 PM 수작업 | Claude 가 디폴트 정책으로 일괄 채움 → 사람은 검수만 |
| 새 페이지가 늘어날 때마다 스크립트 수정 | 코드를 고쳐야 함 | 웹 UI 에서 페어 등록 (sqlite 영구 저장) |

---

## 2. 30 초 요약

```
1) Figma 에 "Trans*" 로 시작하는 프레임을 만든다
2) 웹 UI 에서 Figma URL + Confluence URL 을 한 번 등록한다
3) "🔄 동기화" → 신규 용어가 시트에 자동으로 추가된다
4) 화면에 뜨는 "Claude에게 던질 요청문" 을 복사해 채팅창에 붙여넣으면 다국어가 채워진다
```

---

## 3. 빠른 시작

```powershell
# 의존성 설치
pip install -r requirements.txt

# .env 작성 (FIGMA_TOKEN / CONFLUENCE_EMAIL / CONFLUENCE_TOKEN)
# 토큰 발급은 WORKFLOW.md §1~2 참고

# 연결 확인 (선택)
python test_connection.py

# 웹 UI 실행
streamlit run app.py
```

> Confluence API 토큰은 반드시 **Classic** `Create API token` 으로 발급할 것. `Create API token with scopes` (Scoped) 는 Confluence 에서 거부됩니다.

---

## 4. 일상 사용

- **새 화면이 추가됐을 때**: Figma 에서 프레임 이름 앞에 `Trans` 만 붙이면 끝. 별도 등록 작업 없음.
- **새 번역시트 페이지가 생겼을 때**: 웹 UI 사이드바에서 페어 등록 1회.
- **주기적 동기화**: 메인 화면 우측 상단 `🔄 전체 동기화` 또는 `python sync.py`.
- **번역 채우기**: 동기화 결과 화면의 회색 코드 블록을 복사 → Claude 채팅창 붙여넣기.

---

## 5. 폴더 구성 (요약)

```
app.py                # Streamlit 웹 UI (등록·동기화 진입점)
sync.py               # CLI 동기화 (등록된 모든 페어 일괄)
figma_client.py       # Figma API + 텍스트 수집/중복 제거 로직
confluence_client.py  # Confluence API + 표 파싱/추가/번역 채우기
db.py                 # sqlite (mappings.db) 매핑 저장소
test_connection.py    # 토큰·페이지 접근 점검
config.json           # 팀 공유 페어 매핑 (커밋 대상) — 새 팀원은 첫 실행 시 자동 import
WORKFLOW.md           # 상세 사용 매뉴얼
```

---

## 6. 현재 상태

- ✅ Figma → Confluence 단방향 동기화 동작
- ✅ Streamlit 웹 UI 로 페어 등록/삭제/동기화/결과 미리보기
- ✅ 한국어 컬럼 기준 중복 제거, 페이지 구분 라벨 자동 부여
- ✅ Claude 호출 시 사용할 요청문 자동 생성
- ⚠️ **아직 1인 사용 단계** — 팀 공유는 아래 Phase 0/1 완료 후 가능
- ⚠️ 다국어 채우기는 사람이 채팅창에 붙여넣어야 함 — Phase 2 에서 자동화
- ⚠️ Confluence **Cloud** 전용 (Server/Data Center 미지원)
- ⚠️ 동시 편집 중 PUT 충돌 시 재시도 로직 없음 — 실패하면 한 번 더 누르기

---

## 7. 액션 플랜

> **목표 운영 모델**: 팀 공용 봇 계정 1개 + 깃 레포의 `config.json` 으로 페어 매핑 공유 + 각자 PC 에서 `streamlit run app.py`
> **원칙**: 코드는 지금 상태 유지. Phase 0/1 은 사람의 결정과 문서 작업, Phase 2 부터 코드 추가.

### Phase 0 — 운영 모델 셋업 (코드 0줄, 결정·발급 작업)

- [ ] **봇 계정 발급**
  - 팀 공용 메일(예: `translation-bot@회사.com`) 로 Atlassian + Figma 가입
  - Atlassian: 번역시트가 있는 Confluence 워크스페이스에 초대 → 대상 페이지에 **편집 권한** 부여
  - Figma: 번역 대상 파일에 **View 권한** 부여
  - 토큰 발급
    - Atlassian: `id.atlassian.com` → `Create API token` (반드시 **Classic**, Scoped 아님)
    - Figma: Settings → Security → Personal access tokens
- [ ] **Anthropic API 키 발급** (Phase 2 용 — 지금 받아두면 됨)
  - console.anthropic.com 에서 봇 메일로 가입 → 결제수단 등록 → 키 발급
  - 예상 비용: **월 $1~3** (Haiku, 신규 용어 1,000건 가정)
- [ ] **토큰 보관처 결정**: 1Password / Bitwarden / 사내 시크릿 매니저 중 하나. `.env` 파일 자체 공유는 금지(반드시 각자 만들기)
- [ ] **첫 `config.json` 한 명이 만들어 커밋**
  - 지금 `mappings.db` 가지고 있는 사람이 페어 내용을 `config.json` 으로 옮겨 깃에 푸시
  - `confluence_domain` 은 **봇 계정이 접근 가능한 도메인**으로 (현재 `linapersonal` 은 개인 도메인이라 교체 필요)

### Phase 1 — 팀이 바로 쓸 수 있게 (코드 거의 0줄, 문서/구성)

- [ ] **`.gitignore` 추가**: `.env`, `mappings.db`, `__pycache__/`, `*.pyc` — `.env`/`mappings.db` 가 절대 커밋되지 않게
- [ ] **README 셋업 가이드 보강**
  - 봇 토큰 어디서 가져오는지 (1Password 항목명 등) / `.env` 어떻게 채우는지 / 누구한테 요청
  - 첫 실행 시 `config.json` 이 자동으로 `mappings.db` 로 import 되는 동작 (`db.py:43-73`) 명시
- [ ] **페어 추가/공유 운영 절차 문서화** — 코드 변경 없이 가능한 흐름
  - **새 페어 추가**: Streamlit UI 에서 등록(본인 `mappings.db` 에 들어감) → `config.json` 에 같은 내용을 손으로 추가 → PR
  - **다른 팀원이 새 페어 받기**: `git pull` → **본인 `mappings.db` 삭제 후 streamlit 재실행** → `_migrate_from_config_if_needed()` 가 자동 import
    - ⚠️ `mappings.db` 가 비어있을 때만 마이그레이션이 동작하므로 삭제 필수 (`db.py:47`). 이 불편함은 Phase 3 에서 해소
- [ ] **`test_connection.py` 는 그대로 유지** — `config.json` 의 `jobs` 를 읽는 현재 구조가 팀 공유 방향과 정확히 맞음. 새 팀원이 셋업 후 `python test_connection.py` 한 번으로 모든 페어 접근 검증 가능

### Phase 2 — 핵심 기능: 자동 번역 (코드 추가)

> 지금 비어 있는 단 한 줄. URL 두 개 넣으면 → 번역된 시트가 나오는 흐름이 여기서 완성됨.

- [ ] **`.env` 에 `ANTHROPIC_API_KEY` 항목 추가** + `anthropic` 패키지를 `requirements.txt` 에 추가
- [ ] **`app.py` 동기화 결과에 "🤖 자동 번역" 버튼**
  - 신규 + 기존 빈 셀 모두 수집 → Claude (Haiku) 호출 → JSON 응답 파싱 → `confluence_client.update_translations()` 로 일괄 쓰기
  - WORKFLOW.md §"디폴트 번역 정책" 표를 **시스템 프롬프트**로 박아두면 누가 호출하든 동일 정책
  - prompt caching 사용 → 입력 토큰 90% 절감 (단가가 워낙 작아 필수는 아님)
- [ ] **`sync.py` 에 `--auto-translate` 옵션** — CLI 만으로 동기화 + 번역 한 번에 끝나는 경로 확보
- [ ] **결과 화면 표시**: 어느 행이 채워졌는지 / 사람이 검수할 행은 어디인지 표시

### Phase 3 — 운영 안정성 / 사용성 개선

- [ ] **`config.json` 변경 자동 재import**: `mappings.db` 가 있어도 `config.json` 의 신규 페어를 감지해서 추가 — Phase 1 의 "DB 삭제 후 재실행" 불편함 해소
- [ ] **PUT 충돌 자동 재시도**: `confluence_client._update_page` 가 409 받으면 `_get_page` 부터 1~2회 재시도 (`confluence_client.py:142-159`)
- [ ] **검수 현황 표시**: 동기화 결과 카드에 "다국어 빈 셀 남은 행 N개"
- [ ] **동기화 이력 누적**: 현재 `pairs.last_sync_*` 한 줄만 보관 → 별도 이력 테이블로 쌓아 "이번 주 새 용어" 요약 가능
- [ ] **"페이지 구분" 다중 화면 처리 정책 재검토** (`figma_client.py:87-98`): 같은 한국어가 여러 프레임에 등장 시 현재는 첫 발견 1개만 — 콤마 결합으로 바꿀지 결정
- [ ] **다국어 컬럼 커스터마이즈** (`confluence_client.py:6-12`): `2col` / `5col` 고정 → 베트남어 등 추가 요청 시 페어별 컬럼 정의 필요
- [ ] **단위 테스트 추가**: 분기 많은 `figma_client._collect_texts` 부터 pytest 픽스처

---

## 8. 도움이 필요할 때

- 사용법: `WORKFLOW.md` (이 디렉토리)
- 토큰/권한 에러: `python test_connection.py` 먼저 실행해서 어느 단계인지 확인
- 그 외: 이 디렉토리 담당자에게 문의
