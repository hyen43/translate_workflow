"""Streamlit 웹 UI — Figma → Confluence 번역시트 동기화 + 자동 번역 (stateless)."""
import hmac
import os
import re

import requests
import streamlit as st
from dotenv import load_dotenv

import translator
from confluence_client import KO_LANG, SUPPORTED_LANGS, ConfluenceClient, norm_key
from figma_client import FigmaClient

load_dotenv()

# ---------- URL 파서 ----------

FIGMA_URL_RE = re.compile(r"figma\.com/(?:design|file)/([A-Za-z0-9]+)")
CONFLUENCE_PAGE_RE = re.compile(r"/pages/(\d+)")
CONFLUENCE_DOMAIN_RE = re.compile(r"https?://([^.]+)\.atlassian\.net")


def parse_figma_url(url: str) -> str | None:
    m = FIGMA_URL_RE.search(url)
    return m.group(1) if m else None


_HANGUL_RE = re.compile(r"[가-힣]")


def is_english_source(text: str) -> bool:
    """한글이 전혀 없고 영문자가 있으면 영어 원문으로 간주 (한국어 번역 대상)."""
    return bool(re.search(r"[A-Za-z]", text)) and not _HANGUL_RE.search(text)


def parse_confluence_url(url: str, email: str, token: str) -> tuple[str | None, str | None]:
    """정식 URL → (domain, page_id). 단축 URL(/wiki/x/..)이면 redirect 따라가서 추출."""
    domain_m = CONFLUENCE_DOMAIN_RE.search(url)
    domain = domain_m.group(1) if domain_m else None

    page_m = CONFLUENCE_PAGE_RE.search(url)
    if page_m:
        return domain, page_m.group(1)

    if domain:
        try:
            r = requests.get(url, auth=(email, token), allow_redirects=True, timeout=10)
            page_m = CONFLUENCE_PAGE_RE.search(r.url)
            if page_m:
                return domain, page_m.group(1)
        except requests.RequestException:
            pass
    return domain, None


# ---------- 기본 설정 + 비밀번호 게이트 ----------

st.set_page_config(page_title="번역시트 동기화", layout="centered")

APP_PASSWORD = os.getenv("APP_PASSWORD", "")
if APP_PASSWORD and not st.session_state.get("authed"):
    st.title("🔒 번역시트 동기화")
    pw = st.text_input("팀 비밀번호", type="password")
    if st.button("입장", type="primary"):
        if hmac.compare_digest(pw, APP_PASSWORD):
            st.session_state["authed"] = True
            st.rerun()
        st.error("비밀번호가 틀렸습니다.")
    st.stop()

email = os.getenv("CONFLUENCE_EMAIL", "")
conf_token = os.getenv("CONFLUENCE_TOKEN", "")
figma_token = os.getenv("FIGMA_TOKEN", "")
missing = [
    name
    for name, v in [
        ("FIGMA_TOKEN", figma_token),
        ("CONFLUENCE_EMAIL", email),
        ("CONFLUENCE_TOKEN", conf_token),
        ("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", "")),
    ]
    if not v
]
if missing:
    st.error(f"환경변수 누락: {', '.join(missing)}")
    st.stop()

st.title("Figma → Confluence 번역시트 동기화")
st.caption("Figma의 `Trans*` 프레임 텍스트를 수집해 번역시트에 추가하고, 빈 다국어 셀을 Claude가 채웁니다.")

# ---------- ① URL 입력 + 표 확인 ----------

figma_url = st.text_input("Figma URL", placeholder="https://www.figma.com/design/...")
confluence_url = st.text_input(
    "Confluence URL",
    value=os.getenv("DEFAULT_CONFLUENCE_URL", ""),
    placeholder="https://xxx.atlassian.net/wiki/... (단축 URL 가능)",
)

if st.button("표 확인", type="primary"):
    st.session_state.pop("table", None)
    file_key = parse_figma_url(figma_url)
    domain, page_id = parse_confluence_url(confluence_url, email, conf_token)

    if not file_key:
        st.error("Figma URL에서 file key를 추출하지 못했습니다.")
    elif not domain or not page_id:
        st.error("Confluence URL에서 페이지를 찾지 못했습니다 (접근 권한 또는 URL 형식 확인).")
    else:
        try:
            with st.spinner("Confluence 표 확인 중..."):
                cc = ConfluenceClient(domain, email, conf_token)
                info = cc.get_table_info(page_id)
            st.session_state["table"] = {
                "file_key": file_key,
                "domain": domain,
                "page_id": page_id,
                "info": info,
            }
        except ValueError as e:
            st.error(str(e))
        except requests.HTTPError as e:
            st.error(f"Confluence 조회 실패: {e}")

table = st.session_state.get("table")
if not table:
    st.stop()

info = table["info"]
page_url = (
    f"https://{table['domain']}.atlassian.net/wiki/pages/viewpage.action"
    f"?pageId={table['page_id']}"
)

st.divider()
st.markdown(
    f"**감지된 표**: [{info['page_title']}]({page_url}) — "
    f"`{' | '.join(info['headers'])}` · 기존 {len(info['rows'])}행"
)

# ---------- ② 언어 선택 ----------

st.markdown("**번역할 언어** (체크된 언어만 채움, 미체크는 공백 유지)")
selected_langs = []
ko_col, *lang_cols = st.columns(1 + len(SUPPORTED_LANGS))
translate_ko = ko_col.checkbox(
    KO_LANG,
    value=True,
    key="lang_ko",
    help="원문이 영어인 신규 항목의 한국어 셀을 번역으로 채웁니다. 해제 시 한국어 셀에 영어 원문이 그대로 들어갑니다.",
)
for col, lang in zip(lang_cols, SUPPORTED_LANGS):
    exists = lang in info["langs"]
    label = lang if exists else f"{lang} (컬럼 추가)"
    if col.checkbox(label, value=exists, key=f"lang_{lang}"):
        selected_langs.append(lang)

# ---------- ③ 동기화 + 번역 실행 ----------

if st.button(
    "🔄 동기화 + 번역 실행",
    type="primary",
    disabled=not (selected_langs or translate_ko),
):
    try:
        with st.spinner("Figma 텍스트 수집 중..."):
            terms = FigmaClient(figma_token).get_terms(table["file_key"])

        if not terms:
            st.warning(
                "Figma에서 `Trans*` 프레임을 찾지 못했습니다 — 번역할 프레임 이름이 "
                "`Trans`로 시작하는지 확인하세요. (기존 표의 빈 셀 번역은 계속 진행합니다)"
            )

        # 원문이 영어인 행은 영어 셀에 저장되므로 전체 언어 컬럼 기준으로 중복 판정
        existing_keys = {
            norm_key(row.get(col, ""))
            for row in info["rows"]
            for col in (KO_LANG, *info["langs"])
        }
        existing_keys.discard("")
        new_rows = [(t, l) for t, l in terms if norm_key(t) not in existing_keys]

        items = [{"페이지 구분": label, "원문": src} for src, label in new_rows]
        for row in info["rows"]:
            ko = row.get(KO_LANG, "").strip()
            if ko and any(not row.get(lang, "").strip() for lang in selected_langs):
                items.append({"페이지 구분": row.get("페이지 구분", ""), "원문": ko})

        translations = {}
        english_sources = {src for src, _ in new_rows if is_english_source(src)}
        request_langs = selected_langs + (
            [KO_LANG] if translate_ko and english_sources else []
        )
        if items and request_langs:
            with st.spinner(f"Claude 번역 중... ({len(items)}건 × {len(request_langs)}개 언어)"):
                results = translator.suggest_batch(info["rows"], items, request_langs)
            translations = {
                norm_key(item["원문"]): res for item, res in zip(items, results)
            }
            # 영어 원문은 영어 셀에 원문 그대로 보존 (영어 미체크 시에도)
            for src in english_sources:
                translations.setdefault(norm_key(src), {})["영어"] = src

        with st.spinner("Confluence 표 업데이트 중..."):
            cc = ConfluenceClient(table["domain"], email, conf_token)
            summary = cc.sync_table(table["page_id"], selected_langs, new_rows, translations)

        st.session_state.pop("table", None)
        added_cols = (
            f" · 컬럼 추가: {', '.join(summary['added_columns'])}"
            if summary["added_columns"]
            else ""
        )
        st.success(
            f"✅ 완료 — Figma {len(terms)}개 수집 → 신규 **{summary['added_rows']}행** 추가 · "
            f"번역 **{summary['filled_cells']}셀** 채움{added_cols}"
        )
        if new_rows:
            with st.expander(f"신규 용어 {len(new_rows)}개", expanded=True):
                st.dataframe(
                    [{"페이지 구분": label, KO_LANG: ko} for ko, label in new_rows],
                    use_container_width=True,
                    hide_index=True,
                )
        st.markdown(f"👉 [Confluence에서 검수하기]({page_url})")
        st.caption("주소·전화·더미 텍스트 등 번역 스킵 대상은 빈 칸으로 남습니다 — 검수 시 확인하세요.")
    except requests.HTTPError as e:
        st.error(f"API 호출 실패: {e}")
    except ValueError as e:
        st.error(str(e))
