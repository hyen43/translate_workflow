# 슬랙 봇 전환 계획서

> 목표: 지금의 1인용 Streamlit UI를 **팀 슬랙 채널에서 슬래시 커맨드로 호출하는 봇**으로 전환한다.
> 서버는 클라우드에 상시 배포하고, 팀원은 슬랙 아이디만 있으면 별도 셋업 없이 바로 쓴다.

---

## 0. 확정된 결정

| 항목 | 선택 | 비고 |
|---|---|---|
| **접점** | 슬랙 슬래시 커맨드 (only) | Streamlit UI 폐기 |
| **호스팅** | Fly.io (대안: Render) | 무료 tier + 상시 실행. 슬래시 3초 ack 안전 확보 |
| **DB** | Neon Postgres (managed, free tier) | 서버 재배포·이관 안전. sqlite / config.json 폐기 |
| **자동 번역** | Anthropic API 직접 (Claude Haiku, prompt caching) | 요청문 복붙 방식 폐기 |
| **접근 제어** | 채널 allowlist (env var `ALLOWED_CHANNEL_IDS`) | 워크스페이스 내 특정 채널에서만 |
| **row 추가 UX** | 슬랙 모달로 다국어 미리보기 + 편집 후 push | Block Kit `views.open` |
| **PUT 409 처리** | 자동 재시도 2회 (500ms 백오프) | README §7 Phase 3 항목 흡수 |
| **Batch 추가** | 이번 스코프 제외 | 단건 `/번역추가` + 동기화 자동 채움으로 커버 |

---

## 1. 스코프

### 이번 계획에서 다루는 것
- Slack Bolt(Python) + FastAPI 서버 스캐폴딩
- 슬래시 커맨드 4개 (`/번역목록`, `/번역동기화`, `/번역추가`, `/번역페어등록`)
- Anthropic Haiku 통합 (기존 번역표 few-shot + prompt caching)
- sqlite → Neon Postgres 이관
- Fly.io 배포 (Dockerfile, fly.toml)
- 채널 allowlist, 서명 검증, PUT 409 재시도

### 다루지 않는 것
- Slack Enterprise Grid / SSO
- 여러 워크스페이스 지원 (single-workspace 전제)
- Batch 여러 줄 추가 (필요 확인 후 별도)
- 사내 인프라 배포 (Fly.io 무료tier 전제)
- 회귀 테스트 자동화 — 최소 수동 검증만 (§8)

---

## 2. 최종 아키텍처

```
Slack Workspace (지정 채널)          Fly.io 앱 (FastAPI + Bolt)          Neon Postgres
─────────────────────────           ────────────────────────────         ─────────────
/번역목록          ─────HTTPS───▶  ① Slack 서명 검증 (HMAC)              pairs
/번역동기화 [pair|all]              ② 채널 allowlist 검증                 (스키마 그대로)
/번역추가 [pair] [한국어]           ③ 3초 내 ack (defer / views.open)
/번역페어등록                       ④ 백그라운드 처리
                                       ├─ figma_client (그대로)
                                       ├─ confluence_client (409 재시도 추가)
                                       └─ translator.py (신규, Haiku)
                                    ⑤ response_url / views.update 로 결과
       ◀────────────────────────────
```

- **인증 주체**: 서버 `.env`에 저장된 봇 계정 토큰 (Confluence·Figma·Anthropic) 하나. 팀원 각자 토큰 발급 X.
- **팀원 시점**: 슬랙 워크스페이스 멤버 + 지정 채널 접근권만 있으면 끝.

---

## 3. 슬래시 커맨드 스펙

| 명령 | 파라미터 | 응답 | 비고 |
|---|---|---|---|
| `/번역목록` | 없음 | ephemeral: 페어 카드 리스트 (진행률·마지막 동기화 포함) | 즉시 응답 (DB 조회만) |
| `/번역동기화` | `[페어명\|all]` (기본 all) | ack → 스레드 답장: 페어별 결과 + 자동 번역까지 완료 요약 | 백그라운드, `response_url` 사용 |
| `/번역추가` | `[페어명] [한국어]` | 모달 오픈 (다국어 pre-filled, 편집 가능) | Claude Haiku 호출 → `views.open` |
| `/번역페어등록` | 없음 | 모달 오픈 (Figma URL / Confluence URL / 필터 등) | 등록 후 ephemeral 확정 |

### 3.1 `/번역동기화` 흐름
1. 즉시 ack (`"동기화 시작..."` ephemeral)
2. 백그라운드에서 각 페어별로:
   - `figma_client.get_terms()` → `confluence_client.get_terms()` 차집합
   - 신규 있으면 `add_terms()` (KO 컬럼만 채움)
   - **바로 이어서** `translator.suggest()` 로 다국어 자동 채움 (신규 + 기존 빈 셀)
   - `update_translations()` 로 push
3. `response_url`로 요약 답장 (신규 N개, 자동 번역 M개, 실패 K개)

### 3.2 `/번역추가` 모달 (미리보기 + 편집)

```
┌ 번역 추가 — [회사소개 페이지] ─────────────────────────┐
│                                                       │
│ 페이지 구분  [홈화면 ▼]  (기존 라벨 목록 + 자유 입력)   │
│ 한국어       독서 노트                     (readonly) │
│                                                       │
│ 영어         [Reading Notes                        ]  │
│ 일본어       [読書ノート                            ]  │
│ 중국어(간체) [阅读笔记                              ]  │
│ 중국어(번체) [閱讀筆記                              ]  │
│                                                       │
│                          [ 취소 ]  [ 시트에 추가 ]     │
└───────────────────────────────────────────────────────┘
```

- 명령 수신 → Claude Haiku 호출 (~1-2s) → 결과로 모달 pre-fill → 오픈 (3초 내)
- 사용자 편집 → 제출 → `append_row()` 호출 → ephemeral "✅ 추가됨"
- 이미 존재하는 한국어면 모달 오픈 전에 ephemeral 경고 후 중단

### 3.3 `/번역페어등록` 모달
- Figma URL, Figma 페이지 이름, 필터 타입/값, Confluence URL, 컬럼 형식(`2col`/`5col`), 페어 이름
- 제출 시 기존 `parse_figma_url` / `parse_confluence_url` 로직 재사용 → `db.add_pair()`

---

## 4. Claude 자동 번역 (translator.py)

### 4.1 학습 재료
- `confluence_client.get_full_translations(page_id, table_type)` (신규) — 전 컬럼 dict 리스트
- 시스템 프롬프트에 삽입 → **prompt caching** (1h TTL) 으로 입력 토큰 90% 절감

### 4.2 프롬프트 뼈대
```
[system, cache=1h]
너는 이 프로젝트의 번역 어시스턴트다.
== 디폴트 번역 정책 == (WORKFLOW.md에서 복붙)
== 이 페어의 기존 번역 표 == (JSON dump)
새 용어를 번역할 때 위 표의 스타일·용어 선택을 최우선 참고한다.
동일/유사 용어가 표에 있으면 그대로 재사용한다.

[user]
다음 한국어를 번역해줘. 응답은 JSON.
[{"페이지 구분": "홈화면", "한국어": "독서 노트"}, ...]

[assistant]
[{"영어": "...", "일본어": "...", "중국어(간체)": "...", "중국어(번체)": "..."}, ...]
```

### 4.3 API
- `translator.suggest_one(existing_table, ko: str) -> dict` — `/번역추가` 모달용
- `translator.suggest_batch(existing_table, ko_list: list[str]) -> list[dict]` — `/번역동기화` 자동 채움용
- JSON 파싱 실패 시 빈 문자열 반환 + 로깅. 사람이 검수하면 됨.

### 4.4 비용 예상
- Haiku 기준, prompt caching 적용 시 신규 용어 1,000건/월 = **월 $1~3**

---

## 5. 파일 변경 요약

### 신규
| 파일 | 역할 |
|---|---|
| `slack_app.py` | FastAPI + Slack Bolt. 슬래시 라우팅, 서명 검증, 모달, 채널 allowlist |
| `translator.py` | Anthropic 래퍼 (`suggest_one`, `suggest_batch`), prompt caching |
| `Dockerfile` | Python 3.12 slim + `uvicorn slack_app:api` |
| `fly.toml` | Fly.io 앱 설정 (region, HTTPS, health check) |
| `.env.example` | `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, `ALLOWED_CHANNEL_IDS`, `FIGMA_TOKEN`, `CONFLUENCE_EMAIL`, `CONFLUENCE_TOKEN` |

### 수정
| 파일 | 변경 |
|---|---|
| `db.py` | sqlite → Postgres. `psycopg` 얇게. `_migrate_from_config_if_needed` 삭제 |
| `confluence_client.py` | ① `_update_page`에 **409 재시도 (2회, 500ms)** ② `get_full_translations()` 추가 ③ `append_row()` 추가 ④ `count_untranslated()` 추가 |
| `requirements.txt` | `slack_bolt`, `fastapi`, `uvicorn`, `anthropic`, `psycopg[binary]` 추가. `streamlit` 삭제 |
| `README.md` | 팀 사용 방식을 슬랙 봇 기준으로 재작성 (Phase E) |
| `WORKFLOW.md` | Streamlit 언급 제거, 슬랙 커맨드로 갈음 (Phase E) |

### 삭제
- `app.py` (Streamlit)
- `config.json` (Postgres가 유일한 진실원)
- `test_connection.py` (`/번역목록`이 대체) — 유지하되 로컬 스모크 테스트로 남겨도 무방
- `sync.py` — `/번역동기화`가 대체. 유지 여부는 Phase B에서 결정 (개발용으로 남길 가치 있음)
- `mappings.db` (Postgres 이관)

---

## 6. Phase별 실행 순서

### Phase A. 계정·인프라 준비 (반나절, 코드 0줄)
- [ ] **Slack 앱 생성** (api.slack.com/apps → From scratch)
  - Bot Token Scopes: `commands`, `chat:write`, `chat:write.public`
  - Slash Commands 4개 등록 (엔드포인트는 나중에 Fly.io URL로)
  - Interactivity & Shortcuts 활성화 (모달 제출 endpoint 등록)
  - 워크스페이스에 설치 → `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` 획득
- [ ] **Fly.io 계정 + CLI 설치** (`flyctl`)
- [ ] **Neon 계정 + 프로젝트 생성** → `DATABASE_URL` 획득
- [ ] **Anthropic API 키 발급** (봇 이메일로)
- [ ] **봇 계정 준비**
  - Confluence·Figma에 초대 + 대상 페이지 편집 권한
  - 토큰 발급 (Confluence는 반드시 Classic API token)
- [ ] **허용 채널 결정** → `channel_id` 확보 (슬랙 채널 우클릭 → View channel details)

### Phase B. DB + 서버 뼈대 (1일)
- [ ] `db.py` Postgres 이관 (`psycopg` 사용, 스키마 동일)
- [ ] `slack_app.py` — FastAPI + Slack Bolt 스캐폴딩
  - `/slack/events` 엔드포인트 (서명 검증)
  - 채널 allowlist 미들웨어
  - `/번역목록` 먼저 구현 (DB 조회만) → 로컬 ngrok 으로 슬랙 연결 검증
- [ ] `Dockerfile` + `fly.toml` → `flyctl deploy` 로 실배포
- [ ] Slack 앱의 슬래시 커맨드 URL 을 Fly.io 로 변경

### Phase C. 동기화 자동화 (1일)
- [ ] `confluence_client.get_full_translations()` + `count_untranslated()` 구현
- [ ] `translator.py` — `suggest_one` / `suggest_batch` + prompt caching
- [ ] `confluence_client._update_page` 에 409 재시도 래퍼
- [ ] `/번역동기화` 구현 — 백그라운드 태스크(FastAPI BackgroundTasks) → `response_url` 답장
- [ ] 검증: 실제 페어 하나로 동기화 → 신규 + 자동 번역까지 완료 확인

### Phase D. 단건 추가 + 페어 등록 (1일)
- [ ] `confluence_client.append_row()` 구현
- [ ] `/번역추가` — Claude 호출 → 모달 오픈 → 제출 → `append_row`
- [ ] `/번역페어등록` — 모달 → URL 파서 → `db.add_pair()`
- [ ] 중복 한국어 감지 → 모달 오픈 전 ephemeral 경고

### Phase E. 다듬기 + 문서 (0.5일)
- [ ] `/번역동기화` 결과 메시지에 Figma·Confluence 링크
- [ ] 에러 배너 (예: PUT 재시도 실패, Claude 파싱 실패)
- [ ] `README.md` / `WORKFLOW.md` — Streamlit 언급 걷어내고 슬래시 커맨드 흐름으로 재작성
- [ ] Streamlit 관련 파일 삭제 (`app.py`, sqlite `mappings.db`, `config.json`)
- [ ] `.env.example` 갱신

**총 예상: 3~4일**

---

## 7. 위험 요소 · 대비

| 리스크 | 대비책 |
|---|---|
| Fly.io 무료 tier 리소스 부족 (256MB RAM) | 한 프로세스로 시작, 필요 시 auto-scale 유료 전환 |
| Neon 무료 tier 데이터 초과 (0.5GB) | 페어 스키마 매우 작음(수십 KB) — 실질 우려 없음 |
| Slack 3초 ack 초과 | 모든 처리는 백그라운드 + `response_url`. 모달만 3초 내에 열어야 함 (Claude 호출 <2s Haiku면 안전) |
| Claude 응답 JSON 파싱 실패 | 빈 문자열로 채워 사람 검수. 재시도 X (비용/응답성 우선) |
| Confluence PUT 409 (동시 편집) | 2회 재시도 (500ms 백오프). 그래도 실패 시 슬랙에 에러 배너 |
| 봇 토큰 유출 | Fly secrets(`flyctl secrets set`)로만 관리. `.env`는 로컬 개발용 |
| 봇 오남용 (전체 채널 노출) | 채널 allowlist 필수. 없으면 서버 자체가 거부 |
| 기존 표가 너무 커서 프롬프트 초과 | 500행 넘으면 최근 N행 샘플링 — Phase C에서 실제 크기 확인 후 결정 |

---

## 8. 검증 시나리오 (수동, Phase D 완료 시점)

1. **채널 제한**: 허용 안 된 채널에서 `/번역목록` → ephemeral 거부 메시지
2. **`/번역목록`**: 등록 페어 카드 3개 이상 나열, 진행률 정상 표시
3. **`/번역동기화 all`**: Figma 신규 용어 있는 상태에서 실행 → 스레드에 요약 + 자동 번역까지 채워졌는지 Confluence에서 확인
4. **`/번역추가`**: "환영합니다" 입력 → 모달에 각 언어 pre-filled → 영어만 수정 → 확정 → Confluence에 한 줄만 늘고 다른 행 안 건드림
5. **중복 방지**: 이미 있는 한국어로 `/번역추가` → 모달 안 열리고 ephemeral 경고
6. **409 재시도**: 일부러 Confluence를 다른 세션에서 편집 → 재시도 성공/실패 로그 확인
7. **`/번역페어등록`**: 새 페어 등록 → `/번역목록` 에 반영되는지

---

## 9. 팀 사용 가이드 (Phase E 후 README 반영 초안)

```
1. 슬랙 워크스페이스에 봇이 이미 설치돼 있다.
2. 허용된 채널에서:
   /번역목록                                등록된 페어 확인
   /번역동기화 all                          Figma 신규 용어 수집 + 자동 번역
   /번역추가 회사소개 독서 노트              모달에서 다국어 확인·수정 → 추가
   /번역페어등록                            새 페어 추가 (모달)
3. 최종 검수는 Confluence 페이지에서 직접.
```

토큰 발급·서버 관리는 관리자(1명) 몫. 팀원은 슬랙만 있으면 됨.
