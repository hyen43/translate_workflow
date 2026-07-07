import base64
import time

import requests
from bs4 import BeautifulSoup, Tag

KO_LANG = "한국어"
SUPPORTED_LANGS = ["영어", "일본어", "중국어(간체)", "중국어(번체)"]
LABEL_HEADER = "페이지 구분"

_LANG_ALIASES: dict[str, set[str]] = {
    KO_LANG: {"한국어", "korean", "ko", "국문", "kr"},
    "영어": {"영어", "english", "en", "영문"},
    "일본어": {"일본어", "japanese", "ja", "jp", "일어"},
    "중국어(간체)": {"중국어(간체)", "중국어간체", "간체", "중문(간체)", "chinese(simplified)", "zh-cn", "zh-hans"},
    "중국어(번체)": {"중국어(번체)", "중국어번체", "번체", "중문(번체)", "chinese(traditional)", "zh-tw", "zh-hant"},
}


def norm_key(text: str) -> str:
    """중복 판정용 키: 모든 공백(줄바꿈 포함) 단일 스페이스로 접고 lower.

    Confluence 저장 시 줄바꿈이 유실되므로 strip().lower() 만으로는
    다행(多行) 텍스트가 매번 신규로 재판정된다.
    """
    return " ".join(text.split()).lower()


def normalize_lang(header: str) -> str | None:
    """표 헤더 문자열 → 정규화된 언어명. 지원 언어가 아니면 None."""
    key = "".join(header.split()).lower()
    for lang, aliases in _LANG_ALIASES.items():
        if key in aliases:
            return lang
    return None


class ConfluenceClient:
    def __init__(self, domain: str, email: str, token: str):
        self.base_url = f"https://{domain}.atlassian.net/wiki/rest/api"
        credentials = base64.b64encode(f"{email}:{token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ---------- 조회 (표 확인 단계) ----------

    def get_table_info(self, page_id: str) -> dict:
        """'한국어' 컬럼이 있는 첫 번째 표를 찾아 구조와 내용을 반환.

        반환: {
            "page_title": str,
            "headers": [원본 헤더 문자열, ...],
            "langs": [표에 존재하는 지원 언어(정규화), 한국어 제외],
            "rows": [{정규화 언어명 또는 원본 헤더: 셀 텍스트}, ...],
        }
        표가 없으면 ValueError.
        """
        page = self._get_page(page_id)
        soup = BeautifulSoup(page["body"]["storage"]["value"], "lxml")
        table, headers, col_langs = self._find_translation_table(soup)
        if table is None:
            raise ValueError(f"'{KO_LANG}' 컬럼이 있는 표를 페이지 {page_id} 에서 찾지 못했습니다.")

        col_names = [col_langs[i] or headers[i] for i in range(len(headers))]
        rows = []
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if not cells:
                continue
            row = {}
            for i, name in enumerate(col_names):
                row[name] = cells[i].get_text(strip=True) if i < len(cells) else ""
            rows.append(row)

        return {
            "page_title": page["title"],
            "headers": headers,
            "langs": [l for l in col_langs if l and l != KO_LANG],
            "rows": rows,
        }

    # ---------- 쓰기 (동기화 실행 단계) ----------

    def sync_table(
        self,
        page_id: str,
        selected_langs: list[str],
        new_rows: list[tuple[str, str]],
        translations: dict[str, dict[str, str]],
    ) -> dict:
        """단일 GET→PUT 으로 컬럼 추가 + 신규 행 append + 기존 빈 셀 채움.

        selected_langs: 체크된 언어(정규화). 표에 없으면 컬럼을 추가한다.
        new_rows: [(한국어, 페이지 구분 라벨), ...]
        translations: {norm_key(한국어): {언어: 번역문}}
        PUT 409 시 재조회 후 2회 재시도 (500ms 백오프).
        반환: {"added_rows": n, "filled_cells": m, "added_columns": [...]}
        """
        unsupported = [l for l in selected_langs if l not in SUPPORTED_LANGS]
        if unsupported:
            raise ValueError(f"지원하지 않는 언어: {unsupported}")

        for attempt in range(3):
            try:
                return self._sync_once(page_id, selected_langs, new_rows, translations)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status == 409 and attempt < 2:
                    time.sleep(0.5)
                    continue
                raise

    def _sync_once(
        self,
        page_id: str,
        selected_langs: list[str],
        new_rows: list[tuple[str, str]],
        translations: dict[str, dict[str, str]],
    ) -> dict:
        page = self._get_page(page_id)
        soup = BeautifulSoup(page["body"]["storage"]["value"], "lxml")
        table, headers, col_langs = self._find_translation_table(soup)
        if table is None:
            raise ValueError(f"'{KO_LANG}' 컬럼이 있는 표를 페이지 {page_id} 에서 찾지 못했습니다.")

        header_row = table.find("tr")
        data_rows = table.find_all("tr")[1:]

        # 1) 없는 언어 컬럼 추가
        added_columns = [l for l in selected_langs if l not in col_langs]
        for lang in added_columns:
            th = soup.new_tag("th" if header_row.find("th") else "td")
            th.string = lang
            header_row.append(th)
            headers.append(lang)
            col_langs.append(lang)
            for tr in data_rows:
                if tr.find("td"):
                    td = soup.new_tag("td")
                    td.string = ""
                    tr.append(td)

        ko_index = col_langs.index(KO_LANG)
        lang_index = {l: i for i, l in enumerate(col_langs) if l and l != KO_LANG}

        # 2) 기존 행의 빈 셀 채움 (체크된 언어만, 내용 있는 셀은 보존)
        filled = 0
        for tr in data_rows:
            cells = tr.find_all("td")
            if len(cells) <= ko_index:
                continue
            key = norm_key(cells[ko_index].get_text(strip=True))
            t = translations.get(key)
            if not t:
                continue
            for lang in selected_langs:
                idx = lang_index[lang]
                value = t.get(lang, "")
                if not value or idx >= len(cells):
                    continue
                if cells[idx].get_text(strip=True):
                    continue
                cells[idx].clear()
                cells[idx].append(value)
                filled += 1

        # 3) 신규 행 append (번역 포함)
        tbody = table.find("tbody") or table
        label_index = next(
            (i for i, h in enumerate(headers) if h.strip() == LABEL_HEADER), None
        )
        for ko, label in new_rows:
            t = translations.get(norm_key(ko), {})
            tr = soup.new_tag("tr")
            for i in range(len(headers)):
                td = soup.new_tag("td")
                if i == ko_index:
                    td.string = ko
                elif label_index is not None and i == label_index:
                    td.string = label or ""
                elif col_langs[i] and col_langs[i] in selected_langs:
                    value = t.get(col_langs[i], "")
                    td.string = value
                    if value:
                        filled += 1
                else:
                    td.string = ""
                tr.append(td)
            tbody.append(tr)

        self._update_page(page, str(soup))
        return {
            "added_rows": len(new_rows),
            "filled_cells": filled,
            "added_columns": added_columns,
        }

    # ---------- 내부 ----------

    def _find_translation_table(
        self, soup: BeautifulSoup
    ) -> tuple[Tag | None, list[str], list[str | None]]:
        """반환: (표, 원본 헤더 리스트, 컬럼별 정규화 언어명 리스트[비언어 컬럼은 None])."""
        for table in soup.find_all("table"):
            first_row = table.find("tr")
            if not first_row:
                continue
            headers = [c.get_text(strip=True) for c in first_row.find_all(["th", "td"])]
            col_langs = [normalize_lang(h) for h in headers]
            if KO_LANG in col_langs:
                return table, headers, col_langs
        return None, [], []

    def _get_page(self, page_id: str) -> dict:
        r = requests.get(
            f"{self.base_url}/content/{page_id}",
            params={"expand": "body.storage,version"},
            headers=self.headers,
        )
        r.raise_for_status()
        return r.json()

    def _update_page(self, page: dict, updated_html: str):
        payload = {
            "version": {"number": page["version"]["number"] + 1},
            "title": page["title"],
            "type": "page",
            "body": {
                "storage": {
                    "value": updated_html,
                    "representation": "storage",
                }
            },
        }
        r = requests.put(
            f"{self.base_url}/content/{page['id']}",
            json=payload,
            headers=self.headers,
        )
        r.raise_for_status()
