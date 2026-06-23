import base64

import requests
from bs4 import BeautifulSoup, Tag

HEADERS_2COL = ["페이지 구분", "한국어", "영어"]
HEADERS_5COL = ["페이지 구분", "한국어", "영어", "일본어", "중국어(간체)", "중국어(번체)"]
KO_COL_INDEX = 1  # 한국어 컬럼 위치 (페이지 구분 다음)


def _headers_for(table_type: str) -> list[str]:
    return HEADERS_5COL if table_type == "5col" else HEADERS_2COL


class ConfluenceClient:
    def __init__(self, domain: str, email: str, token: str):
        self.base_url = f"https://{domain}.atlassian.net/wiki/rest/api"
        credentials = base64.b64encode(f"{email}:{token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_terms(self, page_id: str, table_type: str) -> list[str]:
        """한국어 컬럼만 추출 — 중복 비교용."""
        page = self._get_page(page_id)
        html = page["body"]["storage"]["value"]
        soup = BeautifulSoup(html, "lxml")

        table = self._find_translation_table(soup, table_type)
        if not table:
            return []

        terms: list[str] = []
        for row in table.find_all("tr")[1:]:  # skip header
            cells = row.find_all("td")
            if len(cells) > KO_COL_INDEX:
                text = cells[KO_COL_INDEX].get_text(strip=True)
                if text:
                    terms.append(text)
        return terms

    def add_terms(
        self,
        page_id: str,
        new_terms: list[tuple[str, str]],
        table_type: str,
    ):
        """new_terms: [(한국어, 페이지 구분 라벨), ...]"""
        page = self._get_page(page_id)
        html = page["body"]["storage"]["value"]
        soup = BeautifulSoup(html, "lxml")

        table = self._find_translation_table(soup, table_type)
        if not table:
            table = self._create_table(soup, table_type)
            soup.append(table)

        tbody = table.find("tbody") or table
        col_count = len(_headers_for(table_type))

        for term, label in new_terms:
            row = soup.new_tag("tr")

            td_label = soup.new_tag("td")
            td_label.string = label or ""
            row.append(td_label)

            td_ko = soup.new_tag("td")
            td_ko.string = term
            row.append(td_ko)

            for _ in range(col_count - 2):
                empty = soup.new_tag("td")
                empty.string = ""
                row.append(empty)
            tbody.append(row)

        self._update_page(page, str(soup))

    def update_translations(
        self,
        page_id: str,
        table_type: str,
        translations: dict[str, list[str]],
    ) -> int:
        """한국어 컬럼 매칭으로 행을 찾아 영어 이후 언어 셀을 채운다.

        translations: {"한국어": ["영어", "일본어", "중국어(간체)", "중국어(번체)"]}
        2col이면 리스트의 첫 항목(영어)만 사용. 빈 문자열은 셀을 비워둔다.
        페이지 구분 컬럼은 건드리지 않는다. 반환값은 업데이트된 행 수.
        """
        page = self._get_page(page_id)
        html = page["body"]["storage"]["value"]
        soup = BeautifulSoup(html, "lxml")

        table = self._find_translation_table(soup, table_type)
        if not table:
            raise ValueError(f"Translation table ({table_type}) not found on page {page_id}")

        col_count = len(_headers_for(table_type))
        fill_count = col_count - (KO_COL_INDEX + 1)  # 페이지 구분 + 한국어 제외

        key_map = {k.strip().lower(): v for k, v in translations.items()}

        updated = 0
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) <= KO_COL_INDEX:
                continue
            key = cells[KO_COL_INDEX].get_text(strip=True).lower()
            if key not in key_map:
                continue

            values = list(key_map[key])[:fill_count]
            while len(values) < fill_count:
                values.append("")

            for i, val in enumerate(values, start=KO_COL_INDEX + 1):
                if i < len(cells):
                    cells[i].clear()
                    cells[i].append(val)
                else:
                    new_td = soup.new_tag("td")
                    new_td.append(val)
                    row.append(new_td)
            updated += 1

        self._update_page(page, str(soup))
        return updated

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

    def _find_translation_table(self, soup: BeautifulSoup, table_type: str) -> Tag | None:
        expected_headers = _headers_for(table_type)
        for table in soup.find_all("table"):
            first_row = table.find("tr")
            if not first_row:
                continue
            headers = [th.get_text(strip=True) for th in first_row.find_all(["th", "td"])]
            if headers[: len(expected_headers)] == expected_headers:
                return table
        return None

    def _create_table(self, soup: BeautifulSoup, table_type: str) -> Tag:
        headers = _headers_for(table_type)
        table = soup.new_tag("table")
        tbody = soup.new_tag("tbody")
        header_row = soup.new_tag("tr")
        for h in headers:
            th = soup.new_tag("th")
            th.string = h
            header_row.append(th)
        tbody.append(header_row)
        table.append(tbody)
        return table
