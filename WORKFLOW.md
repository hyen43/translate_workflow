# Figma → Confluence 번역시트 자동화

기획서(Figma)의 용어를 번역시트(Confluence)에 동기화합니다. 다국어 번역은 Claude가 직접 채웁니다.

---

## 워크플로우

```
[등록] 웹 UI 에서 Figma URL + Confluence URL 등록 (1회)
   ↓ (sqlite 에 매핑 저장)
[수집] 동기화 버튼 클릭 또는 python sync.py
   ↓ Figma 파일 트리 재귀 순회
   ↓ 프레임 이름이 prefix(예: "Trans")로 시작하면 그 안 모든 텍스트 push
   ↓ 중복 제거 + Confluence 기존 용어와 비교
   ↓ 신규 용어만 한국어 컬럼에 추가
[번역] Claude 에게 "다국어 채워줘" 요청
   ↓ update_translations() 로 빈 셀 일괄 채움
[검수] 사람이 시트에서 수정
```

---

## 파일 구조

```
translate/
├── app.py                 # Streamlit 웹 UI (등록·동기화)
├── sync.py                # CLI 진입점 (등록된 모든 페어 일괄 동기화)
├── db.py                  # sqlite 매핑 저장소
├── figma_client.py        # Figma API 클라이언트
├── confluence_client.py   # Confluence API 클라이언트
├── test_connection.py     # 토큰·페이지 접근 검증
├── mappings.db            # sqlite (자동 생성, git 제외)
├── config.json            # (deprecated) 최초 1회 sqlite 로 자동 마이그레이션
├── .env                   # API 토큰 (직접 생성, git 제외)
├── requirements.txt
└── WORKFLOW.md
```

---

## 설치 및 초기 설정

### 1. 패키지 설치

```powershell
pip install -r requirements.txt
```

### 2. `.env` 파일 생성

```
FIGMA_TOKEN=figd_xxxx
CONFLUENCE_EMAIL=you@personal.com
CONFLUENCE_TOKEN=xxxx
```

| 키 | 발급 위치 |
|---|---|
| `FIGMA_TOKEN` | Figma → Settings → Security → Personal access tokens |
| `CONFLUENCE_EMAIL` | Confluence 워크스페이스 접근 권한이 있는 Atlassian 계정 이메일 |
| `CONFLUENCE_TOKEN` | id.atlassian.com → Security → API tokens → **Create API token** (Classic) |

> ⚠️ `Create API token with scopes` (Scoped) 로 만들면 Confluence 거부됨. 반드시 일반 **Create API token** 사용.

### 3. Figma 기획서 준비

번역 대상 프레임 이름 앞에 약속된 prefix(예: `Trans`)를 붙입니다.

```
Page 1
├─ Trans홈화면          ← 이 안의 모든 텍스트 수집
│   ├─ 헤더
│   ├─ "로그인" (텍스트)
│   └─ ...
├─ Trans상품상세        ← 이 안의 모든 텍스트도 수집
│   └─ ...
├─ #comments_...        ← prefix 없으므로 무시
└─ 디자인메모           ← 무시
```

여러 prefix 매칭 프레임의 텍스트가 합쳐져서 같은 Confluence 시트로 push 됩니다.

### 4. 웹 UI 실행

```powershell
streamlit run app.py
```

브라우저가 열리면 좌측 사이드바에서 새 페어 등록 → 메인 화면에서 동기화.

---

## 페어 등록 (웹 UI)

좌측 사이드바 폼에 다음을 입력:

| 항목 | 예시 |
|---|---|
| 페어 이름 | `회사소개 페이지` (자유 텍스트, 로그 표시용) |
| Figma URL | `https://www.figma.com/design/V6Mv.../...` (file_key 자동 추출) |
| Figma 페이지 이름 | `Page 1` (Figma 하단 탭 이름과 정확히 일치) |
| 필터 타입 | `frame_prefix` (디폴트 추천) |
| 필터 값 | `Trans` (콤마로 여러 개 가능) |
| Confluence URL | 정식 URL 또는 단축 URL (자동 redirect 추적) |
| 컬럼 형식 | `5col` 또는 `2col` |

등록 후 매핑은 `mappings.db` 에 저장돼서 다음 실행 때도 유지됩니다.

---

## 동기화 실행

### 방법 1. 웹 UI (개별 페어 또는 전체)
- 메인 화면 우측 상단 **"🔄 전체 동기화"** — 등록된 모든 페어 한 번에
- 각 페어 우측 **"🔄 동기화"** — 개별 실행

### 방법 2. CLI
```powershell
python sync.py
```
- sqlite 에 등록된 모든 페어 일괄 처리

### 실행 결과 예시

```
총 2개 페어 실행 시작

[1/2] 회사소개 페이지
  Figma 12개 / Confluence 기존 8개 → 신규 4개
    추가: ['[홈화면] 내 서재', '[독서노트] 독서 노트', '[홈화면] 읽는 중', '[홈화면] 다 읽음']

[2/2] 상품 페이지
  Figma 5개 / Confluence 기존 5개 → 신규 0개

==================================================
완료: 2개 페어, 신규 총 4개 추가, 실패 0개

📝 다음 단계 — Claude에게 다국어 번역을 요청하세요:
  - '회사소개 페이지' (page_id: 217055245, 5col): 4개 신규
```

---

## Confluence 번역시트 형식

스크립트가 아래 형식의 테이블을 찾아 새 행을 추가합니다. 테이블이 없으면 자동 생성.
첫 컬럼은 **"페이지 구분"** — 인간 검수자가 어느 화면에서 온 용어인지 확인하는 용도.

**5컬럼 (`5col`)** — 실제 셀 수는 6개 (페이지 구분 포함)

| 페이지 구분 | 한국어 | 영어 | 일본어 | 중국어(간체) | 중국어(번체) |
|---|---|---|---|---|---|
| 홈화면 | 내 서재 | | | | |
| 독서노트 | 독서 노트 | | | | |

**2컬럼 (`2col`)** — 실제 셀 수는 3개 (페이지 구분 포함)

| 페이지 구분 | 한국어 | 영어 |
|---|---|---|
| 홈화면 | 내 서재 | |

> `sync.py`는 페이지 구분 + 한국어 컬럼을 채웁니다. 다국어 번역은 아래 섹션 참고.

### 페이지 구분 라벨 규칙

| 필터 타입 | 라벨로 채워지는 값 |
|---|---|
| `frame_prefix` | 매칭된 프레임 이름에서 prefix 제거 (예: `Trans홈화면` → "홈화면") |
| `frame_name`   | 일치한 프레임 이름 그대로 |
| `layer_prefix` | 가장 가까운 조상 프레임 이름 (없으면 빈 칸) |

같은 한국어 텍스트가 여러 프레임에 등장하면 **첫 발견 프레임의 라벨**만 기록됩니다 (중복 행은 만들지 않음).

---

## 다국어 번역

### 번역 버전

| 버전 | `table_type` | 컬럼 구성 |
|---|---|---|
| **ver1** | `2col` | 한국어 \| 영어 |
| **ver2** | `5col` | 한국어 \| 영어 \| 일본어 \| 중국어(간체) \| 중국어(번체) |

### 번역 흐름

별도 번역 API 를 붙이지 않고 **Claude가 한국어 컬럼을 읽고 직접 번역**해서 빈 셀을 채웁니다.

1. `python sync.py` 또는 웹 UI 동기화 → 신규 용어가 한국어 컬럼에 추가됨
2. 화면에 표시된 "Claude에게 던질 요청문" 을 복사 → 채팅창에 붙여넣기
3. Claude가 `confluence_client.update_translations()` 를 호출해 빈 셀 일괄 채움
4. 사람이 시트에서 검수/수정

`update_translations(page_id, table_type, translations)` — **한국어 컬럼**(페이지 구분 다음)으로 행을 매칭해서 영어 이후 언어 컬럼만 덮어씁니다. 페이지 구분 컬럼은 절대 건드리지 않습니다. `translations` 는 `{"한국어": ["영어", "일본어", "중국어(간체)", "중국어(번체)"]}` 형태이며, `2col`이면 리스트의 첫 항목(영어)만 사용합니다.

### 디폴트 번역 정책

| 분류 | 처리 |
|---|---|
| 메뉴/카테고리/일반 용어 (예: 회사소개, 채용, 비전) | 일반적 직역 |
| 마케팅 카피/슬로건 (긴 문장·단락) | 자연스러운 **의역** |
| 회사명/브랜드명 (예: 이롬넷, 페이버스) | 영어는 공식 표기 / 일·중은 음역 → **정확성 검수 필요** |
| 업계 약어 (예: PG = Payment Gateway) | **원문 보존** |
| 주소·전화·이메일·사업자번호 | **번역 스킵** (빈 칸 유지) |
| 더미/placeholder 텍스트 | **번역 스킵** (Figma 정리 권장) |
| 이미 영어인 항목 (예: `Contact Us`) | 영어 컬럼은 그대로 / 일·중만 번역 |

> 특수 케이스가 있으면 Claude에게 어떻게 처리할지 한 마디 덧붙이세요.

---

## 필터 타입 (figma_client 내부)

| `filter_type` | 동작 | 예시 |
|---|---|---|
| `frame_prefix` (추천) | 프레임 이름이 prefix 로 시작하면 그 안 모든 텍스트 수집 | `Trans` → `Trans홈화면`, `Trans상품` |
| `frame_name` | 프레임 이름이 정확히 일치하면 그 안 모든 텍스트 수집 | `용어집` |
| `layer_prefix` | 텍스트 레이어 이름이 prefix 로 시작하면 해당 텍스트만 수집 | `[T]` → `[T]제목` 텍스트 노드 |

---

## 중복 판정 기준

- **한국어 컬럼**(페이지 구분 다음) 기준으로 비교
- 대소문자 구분 없음, 앞뒤 공백 무시
- Figma 내에서도 동일 텍스트가 여러 번 등장하면 1개만 추가 (페이지 구분은 첫 발견 프레임 라벨로 기록)

---

## 주의사항

- `.env` 와 `mappings.db` 는 git 에 올리지 않습니다 (`.gitignore` 권장)
- Confluence API 는 **Cloud 버전** 기준 (Server/Data Center 는 엔드포인트 다름)
- 단축 URL 파싱은 본인 토큰으로 redirect 따라가서 page_id 를 얻습니다 — 페이지 접근 권한이 없으면 실패
- 같은 페이지를 다른 사람이 동시 편집 중이면 PUT 충돌 가능. 한 번 더 동기화 권장
