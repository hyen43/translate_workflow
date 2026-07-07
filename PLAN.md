# Streamlit 클라우드 배포 전환 계획서

> 목표: 1인용 로컬 Streamlit을 **Fly.io에 상시 배포된 팀 공용 웹 UI**로 전환한다.
> 팀원은 URL 접속 + 비밀번호만으로 사용. 링크 두 개를 넣으면 동기화 + 자동 번역까지 한 번에 끝난다.
> (슬랙 슬래시 커맨드 안은 워크스페이스 앱 생성 불가로 폐기)

---

## 0. 확정된 결정

| 항목 | 선택 | 비고 |
|---|---|---|
| **접점** | Streamlit 웹 UI (Fly.io 배포) | 슬랙 봇 폐기 |
| **사용 방식** | 매번 링크 입력 (stateless) | 페어 등록/저장 없음 |
| **DB** | 없음 | 실행 이력 불필요 (현재 버전 기준). sqlite/config.json 폐기 |
| **Figma 필터** | `Trans` prefix 고정 | 파일 전체 페이지에서 `Trans*` 프레임 탐색 |
| **언어 컬럼** | 기존 Confluence 표 헤더를 동적 인식 | 2col/5col 프리셋 폐기 |
| **지원 언어** | 한국어(필수) + 영어·일본어·중국어(간체)·중국어(번체) 고정 | 이 5개 외 언어는 미지원 |
| **새 언어 추가** | 지원 언어 중 표에 없는 컬럼만 추가 가능 | |
| **자동 번역** | Anthropic API 직접 (Claude Haiku, prompt caching) | 체크된 언어만 채움, 미체크는 공백 |
| **접근 제어** | `APP_PASSWORD` 환경변수 (간단 게이트) | Fly secrets로 관리 |
| **PUT 409 처리** | 자동 재시도 2회 (500ms 백오프) | |

---

## 1. 스코프

### 다루는 것
- 단일 플로우 UI (링크 입력 → 표 확인 → 언어 체크 → 실행 → 결과)
- Confluence 표 헤더 동적 파싱 + 언어 컬럼 추가
- `translator.py` — Claude Haiku 통합 (기존 표 few-shot + prompt caching)
- PUT 409 재시도
- Fly.io 배포 (Dockerfile, fly.toml) + 비밀번호 게이트
- 기존 저장 계층(db.py, config.json, mappings.db, sync.py) 제거

### 다루지 않는 것
- 페어 저장/실행 이력 (필요해지면 다음 버전)
- 슬랙 연동 일체
- prefix 커스터마이즈 (`Trans` 고정)
- 지원 5개 언어 외 언어 (베트남어 등) / 표 없는 페이지에 새 표 자동 생성 외 고급 케이스

---

## 2. 최종 아키텍처

```
팀원 브라우저                    Fly.io 앱 (Streamlit)               외부 API
────────────                    ─────────────────────               ────────
URL 접속 + 비밀번호  ──HTTPS──▶  ① APP_PASSWORD 게이트
Figma URL 입력                  ② figma_client                      Figma API
Confluence URL 입력             ③ confluence_client (409 재시도)     Confluence API
언어 체크 → 실행                 ④ translator (신규)                 Anthropic API
        ◀── 결과 요약 ──────────  ⑤ 결과 렌더 (저장 없음)
```

- **인증 주체**: 서버에 저장된 봇 계정 토큰 (Figma·Confluence·Anthropic) 하나. 팀원 각자 토큰 발급 X.
- **팀원 시점**: URL + 비밀번호만 있으면 끝.

---

## 3. UI 플로우 스펙

### 3.1 화면 구성 (단일 페이지)

```
┌ Figma → Confluence 번역시트 동기화 ──────────────────────┐
│                                                         │
│ Figma URL       [https://www.figma.com/design/...    ]  │
│ Confluence URL  [https://xxx.atlassian.net/wiki/...  ]  │
│                                                         │
│                          [ 표 확인 ]                     │
│ ─────────────────────────────────────────────────────── │
│ 감지된 표: 페이지 구분 | 한국어 | 영어 | 일본어            │
│                                                         │
│ 번역할 언어:  ☑ 영어  ☑ 일본어                            │
│ 컬럼 추가:    ☐ 중국어(간체)  ☐ 중국어(번체)  (표에 없는 지원 언어) │
│                                                         │
│                     [ 🔄 동기화 + 번역 실행 ]             │
│ ─────────────────────────────────────────────────────── │
│ ✅ 신규 12개 추가 · 번역 48셀 채움 · [Confluence 열기]    │
└─────────────────────────────────────────────────────────┘
```

### 3.2 단계별 동작

1. **표 확인** (Confluence 조회만)
   - URL 파싱 (`parse_confluence_url` 재사용, 단축 URL redirect 지원)
   - "한국어" 컬럼이 있는 첫 번째 표 탐지 → 헤더 전체를 읽어 언어 컬럼 목록 표시
   - 표가 없으면 에러 안내 (자동 생성은 하지 않음 — 기존 표 기준이 원칙)
2. **언어 선택** — 지원 언어는 한국어(필수) + 영어·일본어·중국어(간체)·중국어(번체) 고정
   - 기존 언어 컬럼: 체크박스 (기본 전부 체크)
   - 표에 없는 지원 언어: 체크 시 컬럼 추가. 실행 시 헤더 `<th>` + 전 행 빈 `<td>` 추가
3. **동기화 + 번역 실행**
   - Figma 파일 전체 페이지에서 `Trans*` 프레임 탐색 → 텍스트 수집 → strip/lower 중복 제거
   - Confluence 기존 한국어와 차집합 → 신규만 표 뒤에 append (페이지 구분 = prefix 뗀 프레임 이름)
   - 체크된 언어의 빈 셀(신규 행 + 기존 행 모두)을 `translator.suggest_batch()`로 채움
   - 미체크 언어 컬럼은 건드리지 않음 (공백 유지)
   - PUT은 409 시 2회 재시도 (500ms 백오프)
4. **결과 요약**: 신규 N개 / 번역 M셀 / 실패 K건 + Confluence 링크. 저장 없음.

---

## 4. Claude 자동 번역 (translator.py)

### 4.1 학습 재료
- 표 확인 단계에서 파싱한 기존 표 전체 (전 컬럼 dict 리스트)
- 시스템 프롬프트에 삽입 → **prompt caching** 으로 입력 토큰 절감

### 4.2 프롬프트 뼈대
```
[system, cache]
너는 이 프로젝트의 번역 어시스턴트다.
== 디폴트 번역 정책 == (WORKFLOW.md에서 복붙)
== 이 표의 기존 번역 == (JSON dump)
새 용어를 번역할 때 위 표의 스타일·용어 선택을 최우선 참고한다.
동일/유사 용어가 표에 있으면 그대로 재사용한다.

[user]
다음 한국어를 아래 언어로 번역해줘. 응답은 JSON.
언어: ["영어", "일본어"]
[{"페이지 구분": "홈화면", "한국어": "독서 노트"}, ...]
```

### 4.3 API
- `translator.suggest_batch(existing_table, ko_list, target_langs) -> list[dict]`
- 대상 언어는 체크된 것만 — 미체크 언어는 요청 자체에서 제외
- JSON 파싱 실패 시 빈 문자열 반환 + 로깅. 사람이 검수하면 됨.
- 기존 표 500행 초과 시 최근 N행 샘플링 (실제 크기 확인 후 결정)

### 4.4 비용 예상
- Haiku + prompt caching, 신규 용어 1,000건/월 = **월 $1~3**

---

## 5. 파일 변경 요약

### 신규
| 파일 | 역할 |
|---|---|
| `translator.py` | Anthropic 래퍼 (`suggest_batch`), prompt caching |
| `Dockerfile` | Python 3.12 slim + `streamlit run app.py` |
| `fly.toml` | Fly.io 앱 설정 (region, HTTPS, health check) |

### 수정
| 파일 | 변경 |
|---|---|
| `app.py` | 사이드바(페어 등록)·목록 제거 → 단일 플로우 (§3). `APP_PASSWORD` 게이트 추가 |
| `figma_client.py` | 페이지 지정 제거 → 전체 페이지 순회. 필터는 `frame_prefix="Trans"` 고정 |
| `confluence_client.py` | ① 고정 헤더 매칭 폐기 → "한국어" 컬럼 기준 표 탐지 + 헤더 동적 파싱 ② `add_language_columns()` 추가 ③ `get_full_translations()` 추가 (번역 few-shot용) ④ `_update_page` 409 재시도 |
| `requirements.txt` | `anthropic` 추가. 유지: streamlit, requests, bs4, lxml, python-dotenv |
| `.env.example` | `ANTHROPIC_API_KEY`, `APP_PASSWORD` 추가 |
| `README.md` / `WORKFLOW.md` | 배포 URL 접속 기준으로 재작성 (Phase D) |

### 삭제
- `db.py`, `mappings.db` (저장 계층 자체가 없어짐)
- `config.json`
- `sync.py` (UI가 유일한 진입점)
- `test_connection.py` (표 확인 단계가 대체)

---

## 6. Phase별 실행 순서

### Phase A. 계정·인프라 준비 (반나절, 코드 0줄)
- [ ] **봇 계정 준비**: Confluence·Figma에 초대 + 대상 페이지 편집/열람 권한, 토큰 발급 (Confluence는 반드시 Classic API token)
- [ ] **Anthropic API 키 발급** (봇 이메일로)
- [ ] **Fly.io 계정 + CLI 설치** (`flyctl`)
- [ ] **팀 비밀번호 결정** (`APP_PASSWORD`)

### Phase B. 코어 로직 (1일)
- [ ] `confluence_client.py` — 동적 헤더 파싱, 표 탐지 리팩터, `add_language_columns()`, `get_full_translations()`, 409 재시도
- [ ] `figma_client.py` — 전체 페이지 순회 + `Trans` prefix 고정
- [ ] `translator.py` — `suggest_batch` + prompt caching
- [ ] 로컬 검증: 실제 표 하나로 표 확인 → 동기화 → 자동 번역까지

### Phase C. UI + 배포 (1일)
- [ ] `app.py` 단일 플로우 재작성 + `APP_PASSWORD` 게이트
- [ ] 저장 계층 삭제 (`db.py`, `sync.py`, `config.json`, `mappings.db`, `test_connection.py`)
- [ ] `Dockerfile` + `fly.toml` → `flyctl deploy`, secrets 등록
- [ ] 실배포 URL에서 전체 흐름 검증

### Phase D. 다듬기 + 문서 (0.5일)
- [ ] 에러 배너 (409 재시도 실패, Claude 파싱 실패, 표 미발견)
- [ ] `README.md` / `WORKFLOW.md` 재작성 (팀원 = URL + 비밀번호)
- [ ] `.env.example` 갱신

**총 예상: 2~3일**

---

## 7. 위험 요소 · 대비

| 리스크 | 대비책 |
|---|---|
| 표 헤더 표기 불일치 ("영어" vs "English") | 지원 5개 언어의 흔한 표기 별칭 매핑. 미매칭 컬럼은 무시 (건드리지 않음) |
| Figma 파일이 커서 전체 페이지 순회가 느림 | Figma files API는 원래 파일 전체 반환 — 추가 비용 없음. 응답 큰 파일은 spinner 표시 |
| Slack 3초 같은 시간 제약 | 없음 (Streamlit은 동기 실행 + spinner) |
| Claude 응답 JSON 파싱 실패 | 빈 문자열로 채워 사람 검수. 재시도 X |
| Confluence PUT 409 (동시 편집) | 2회 재시도 (500ms 백오프). 실패 시 에러 배너 |
| 봇 토큰 유출 | Fly secrets로만 관리. `.env`는 로컬 개발용 |
| 비밀번호 게이트의 한계 | 내부 도구 수준으로 충분. 민감해지면 Cloudflare Access 등 검토 |
| 기존 표가 너무 커서 프롬프트 초과 | 500행 넘으면 샘플링 — Phase B에서 실제 크기 확인 후 결정 |
| 동시 사용자 2명이 같은 표 실행 | 409 재시도로 대부분 흡수. 잦으면 다음 버전에서 락 검토 |

---

## 8. 검증 시나리오 (수동, Phase C 완료 시점)

1. **비밀번호 게이트**: 틀린 비밀번호 → 접근 거부
2. **표 확인**: 5col 표 URL 입력 → 언어 4개 체크박스 정상 표시
3. **동기화**: Figma 신규 용어 있는 상태에서 실행 → 신규 append + 체크 언어만 채워짐, 미체크 언어 공백 확인
4. **컬럼 추가**: 2col 표(영어만)에서 "일본어" 체크 후 실행 → 컬럼 생성 + 번역 채움, 기존 행 다른 셀 안 건드림
5. **중복 방지**: 같은 링크로 재실행 → 신규 0개
6. **409 재시도**: 다른 세션에서 Confluence 편집 중 실행 → 재시도 성공/실패 로그 확인
7. **표 미발견**: 표 없는 페이지 URL → 명확한 에러 안내

---

## 9. 팀 사용 가이드 (Phase D 후 README 반영 초안)

```
1. 배포 URL 접속 → 팀 비밀번호 입력
2. Figma URL + Confluence URL 붙여넣기 → [표 확인]
3. 번역할 언어 체크 (영어·일본어·중국어(간체)·중국어(번체) 중에서, 표에 없으면 컬럼 추가)
4. [동기화 + 번역 실행] → 결과 확인
5. 최종 검수는 Confluence 페이지에서 직접
```

토큰 발급·서버 관리는 관리자(1명) 몫. 팀원은 URL + 비밀번호만 있으면 됨.
