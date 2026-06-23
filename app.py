"""Streamlit 웹 UI — Figma↔Confluence 매핑 등록 및 동기화."""
import os
import re

import requests
import streamlit as st
from dotenv import load_dotenv

import db
from confluence_client import ConfluenceClient
from figma_client import FigmaClient

load_dotenv()
db.init_db()


# ---------- URL 파서 ----------

FIGMA_URL_RE = re.compile(r"figma\.com/(?:design|file)/([A-Za-z0-9]+)")
CONFLUENCE_PAGE_RE = re.compile(r"/pages/(\d+)")
CONFLUENCE_DOMAIN_RE = re.compile(r"https?://([^.]+)\.atlassian\.net")
CONFLUENCE_TINY_RE = re.compile(r"/wiki/x/([A-Za-z0-9_-]+)")


def parse_figma_url(url: str) -> str | None:
    m = FIGMA_URL_RE.search(url)
    return m.group(1) if m else None


def parse_confluence_url(url: str, email: str, token: str) -> tuple[str | None, str | None]:
    """정식 URL → (domain, page_id). 단축 URL 이면 redirect 따라가서 page_id 추출."""
    domain_m = CONFLUENCE_DOMAIN_RE.search(url)
    domain = domain_m.group(1) if domain_m else None

    page_m = CONFLUENCE_PAGE_RE.search(url)
    if page_m:
        return domain, page_m.group(1)

    tiny_m = CONFLUENCE_TINY_RE.search(url)
    if tiny_m and domain:
        try:
            r = requests.get(url, auth=(email, token), allow_redirects=True, timeout=10)
            final_url = r.url
            page_m = CONFLUENCE_PAGE_RE.search(final_url)
            if page_m:
                return domain, page_m.group(1)
        except Exception:
            pass

    return domain, None


# ---------- UI ----------

st.set_page_config(page_title="번역시트 동기화", layout="wide")
st.title("Figma → Confluence 번역시트 동기화")

email = os.getenv("CONFLUENCE_EMAIL", "")
token = os.getenv("CONFLUENCE_TOKEN", "")
figma_token = os.getenv("FIGMA_TOKEN", "")

if not (email and token and figma_token):
    st.error(".env 파일에 FIGMA_TOKEN, CONFLUENCE_EMAIL, CONFLUENCE_TOKEN 을 채워주세요.")
    st.stop()

# ===== Sidebar: 새 페어 등록 =====
with st.sidebar:
    st.header("➕ 새 페어 등록")

    name = st.text_input("페어 이름", placeholder="예: 회사소개 페이지")
    figma_url = st.text_input("Figma URL", placeholder="https://www.figma.com/design/...")
    page_name = st.text_input("Figma 페이지 이름", value="Page 1")
    filter_type = st.selectbox(
        "필터 타입",
        ["frame_prefix", "frame_name", "layer_prefix"],
        index=0,
        help="frame_prefix: 프레임 이름이 prefix로 시작 (예: 'Trans홈화면')\n"
             "frame_name: 프레임 이름이 정확히 일치\n"
             "layer_prefix: 텍스트 레이어 이름이 prefix로 시작",
    )
    filter_values_raw = st.text_input(
        "필터 값 (콤마 구분)",
        value="Trans",
        help="frame_prefix면 prefix 들. 예: Trans, [T]",
    )
    confluence_url = st.text_input(
        "Confluence 페이지 URL", placeholder="https://....atlassian.net/wiki/spaces/.../pages/..."
    )
    table_type = st.radio("컬럼 형식", ["5col", "2col"], horizontal=True)

    if st.button("등록", type="primary", use_container_width=True):
        errors = []
        if not name.strip():
            errors.append("페어 이름")
        if not figma_url.strip():
            errors.append("Figma URL")
        if not confluence_url.strip():
            errors.append("Confluence URL")

        if errors:
            st.error(f"필수 항목 누락: {', '.join(errors)}")
        else:
            file_key = parse_figma_url(figma_url)
            domain, page_id = parse_confluence_url(confluence_url, email, token)

            if not file_key:
                st.error("Figma URL 에서 file_key 를 추출하지 못했습니다.")
            elif not domain:
                st.error("Confluence URL 에서 도메인을 추출하지 못했습니다.")
            elif not page_id:
                st.error("Confluence URL 에서 page_id 를 추출하지 못했습니다 (단축 URL 인증 실패일 수 있음).")
            else:
                filter_values = [v.strip() for v in filter_values_raw.split(",") if v.strip()]
                try:
                    db.add_pair(
                        name=name.strip(),
                        file_key=file_key,
                        page_name=page_name.strip(),
                        filter_type=filter_type,
                        filter_values=filter_values,
                        confluence_domain=domain,
                        page_id=page_id,
                        table_type=table_type,
                    )
                    st.success(f"등록 완료: {name}")
                    st.rerun()
                except Exception as e:
                    st.error(f"등록 실패: {e}")


# ===== Main: 페어 리스트 + 동기화 =====

pairs = db.list_pairs()

col1, col2 = st.columns([3, 1])
col1.subheader(f"등록된 페어 ({len(pairs)})")
sync_all = col2.button("🔄 전체 동기화", type="primary", use_container_width=True, disabled=not pairs)

if "results" not in st.session_state:
    st.session_state["results"] = {}


def run_sync(pair: dict) -> dict:
    figma = FigmaClient(figma_token)
    confluence = ConfluenceClient(domain=pair["confluence_domain"], email=email, token=token)
    try:
        figma_terms = figma.get_terms(
            file_key=pair["file_key"],
            page_name=pair["page_name"],
            filter_config={"type": pair["filter_type"], "values": pair["filter_values"]},
        )
        existing = confluence.get_terms(pair["page_id"], pair["table_type"])
        existing_set = {t.strip().lower() for t in existing}
        new_terms = [
            (text, label)
            for text, label in figma_terms
            if text.strip().lower() not in existing_set
        ]
        if new_terms:
            confluence.add_terms(pair["page_id"], new_terms, pair["table_type"])
        db.update_last_sync(pair["id"], "OK", len(new_terms))
        return {
            "figma_count": len(figma_terms),
            "existing_count": len(existing),
            "added": len(new_terms),
            "added_terms": new_terms,
        }
    except Exception as e:
        db.update_last_sync(pair["id"], f"ERROR: {e}", 0)
        return {"error": str(e)}


if sync_all:
    progress = st.progress(0.0, text="동기화 중...")
    for i, pair in enumerate(pairs, 1):
        progress.progress(i / len(pairs), text=f"[{i}/{len(pairs)}] {pair['name']}")
        st.session_state["results"][pair["id"]] = run_sync(pair)
    progress.empty()
    st.rerun()


if not pairs:
    st.info("좌측 사이드바에서 새 페어를 등록하세요.")
else:
    for pair in pairs:
        with st.container(border=True):
            top_l, top_r = st.columns([5, 1])
            top_l.markdown(
                f"**{pair['name']}**  \n"
                f"_Figma `{pair['file_key']}` · {pair['filter_type']}={pair['filter_values']}_  \n"
                f"_Confluence `{pair['confluence_domain']}` page `{pair['page_id']}` ({pair['table_type']})_"
            )

            if pair["last_sync_at"]:
                top_l.caption(
                    f"마지막 동기화: {pair['last_sync_at']} · "
                    f"상태: {pair['last_sync_status']} · "
                    f"신규: {pair['last_sync_new_count']}"
                )

            if top_r.button("🔄 동기화", key=f"sync_{pair['id']}", use_container_width=True):
                st.session_state["results"][pair["id"]] = run_sync(pair)
                st.rerun()
            if top_r.button("🗑️ 삭제", key=f"del_{pair['id']}", use_container_width=True):
                db.delete_pair(pair["id"])
                st.session_state["results"].pop(pair["id"], None)
                st.rerun()

            r = st.session_state["results"].get(pair["id"])
            if r is None:
                continue
            if "error" in r:
                st.error(f"❌ {r['error']}")
                continue

            st.success(
                f"Figma {r['figma_count']}개 / 기존 {r['existing_count']}개 → 신규 **{r['added']}개**"
            )
            if r["added"]:
                with st.expander(f"신규 용어 {r['added']}개 보기", expanded=True):
                    st.dataframe(
                        [
                            {"페이지 구분": label, "한국어": text}
                            for text, label in r["added_terms"]
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                st.markdown("📋 **Claude에게 던질 요청문** (복사해서 채팅창에 붙여넣기)")
                request_block = (
                    f"'{pair['name']}' 페어에 신규 용어 {r['added']}개가 추가됐어. "
                    f"page_id={pair['page_id']}, table_type={pair['table_type']}. "
                    f"디폴트 정책대로 다국어 번역 채워줘."
                )
                st.code(request_block, language="text")
