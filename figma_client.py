import requests

from confluence_client import norm_key

TRANS_PREFIX = "Trans"
_CONTAINER_TYPES = ("FRAME", "GROUP", "COMPONENT", "COMPONENT_SET", "INSTANCE", "SECTION")


class FigmaClient:
    BASE_URL = "https://api.figma.com/v1"

    def __init__(self, token: str):
        self.headers = {"X-Figma-Token": token}

    def get_terms(self, file_key: str) -> list[tuple[str, str]]:
        """파일 전체 페이지에서 'Trans*' 프레임 안의 텍스트를 수집.

        반환: [(텍스트, 페이지 구분 라벨), ...] — 한국어 키 기준 중복 제거.
        라벨은 프레임 이름에서 prefix 를 뗀 부분 (예: "Trans홈" → "홈").
        """
        r = requests.get(f"{self.BASE_URL}/files/{file_key}", headers=self.headers)
        r.raise_for_status()

        document = r.json()["document"]
        raw: list[tuple[str, str]] = []
        for page in document.get("children", []):
            self._collect_texts(page, raw, current_label=None)

        return self._deduplicate(raw)

    def _collect_texts(
        self, node: dict, out: list[tuple[str, str]], current_label: str | None
    ):
        name = node.get("name", "")
        node_type = node.get("type", "")

        next_label = current_label
        if node_type in _CONTAINER_TYPES and name.startswith(TRANS_PREFIX):
            stripped = name[len(TRANS_PREFIX):].strip()
            next_label = stripped or name

        if next_label is not None and node_type == "TEXT":
            chars = node.get("characters", "").strip()
            if chars:
                out.append((chars, next_label))

        for child in node.get("children", []):
            self._collect_texts(child, out, next_label)

    @staticmethod
    def _deduplicate(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """norm_key(한국어) 기준 첫 발견 유지."""
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for text, label in items:
            stripped = text.strip()
            key = norm_key(stripped)
            if key and key not in seen:
                seen.add(key)
                result.append((stripped, label))
        return result
