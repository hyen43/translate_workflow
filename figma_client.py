import requests


class FigmaClient:
    BASE_URL = "https://api.figma.com/v1"

    def __init__(self, token: str):
        self.headers = {"X-Figma-Token": token}

    def get_terms(
        self, file_key: str, page_name: str, filter_config: dict
    ) -> list[tuple[str, str]]:
        """반환: [(텍스트, 페이지 구분 라벨), ...] — 한국어 키 기준 중복 제거.

        라벨 의미:
        - frame_prefix: 매칭된 프레임 이름에서 prefix 제거한 부분 (예: "Trans홈" → "홈")
        - frame_name:   일치한 프레임 이름 그대로
        - layer_prefix: 가장 가까운 조상 프레임 이름 (있으면)
        """
        r = requests.get(f"{self.BASE_URL}/files/{file_key}", headers=self.headers)
        r.raise_for_status()

        document = r.json()["document"]
        page = self._find_page(document, page_name)

        raw: list[tuple[str, str]] = []
        self._collect_texts(page, raw, filter_config, current_label=None, parent_frame=None)

        return self._deduplicate(raw)

    def _find_page(self, document: dict, page_name: str) -> dict:
        for child in document.get("children", []):
            if child["name"] == page_name:
                return child
        available = [c["name"] for c in document.get("children", [])]
        raise ValueError(f"Page '{page_name}' not found. Available: {available}")

    def _collect_texts(
        self,
        node: dict,
        out: list[tuple[str, str]],
        filter_config: dict,
        current_label: str | None,
        parent_frame: str | None,
    ):
        name = node.get("name", "")
        node_type = node.get("type", "")
        filter_type = filter_config.get("type", "frame_name")
        filter_values = filter_config.get("values", [])
        if isinstance(filter_values, str):
            filter_values = [filter_values]

        next_label = current_label

        if filter_type == "frame_name":
            if name in filter_values:
                next_label = name

        elif filter_type == "frame_prefix":
            if node_type in ("FRAME", "GROUP", "COMPONENT", "INSTANCE", "SECTION"):
                for prefix in filter_values:
                    if name.startswith(prefix):
                        stripped = name[len(prefix):].strip()
                        next_label = stripped or name
                        break

        elif filter_type == "layer_prefix":
            if node_type == "TEXT":
                for prefix in filter_values:
                    if name.startswith(prefix):
                        chars = node.get("characters", "").strip()
                        if chars:
                            out.append((chars, parent_frame or ""))
                        return

        if next_label is not None and node_type == "TEXT":
            chars = node.get("characters", "").strip()
            if chars:
                out.append((chars, next_label))

        next_parent_frame = (
            name if node_type in ("FRAME", "COMPONENT", "INSTANCE", "SECTION") else parent_frame
        )
        for child in node.get("children", []):
            self._collect_texts(child, out, filter_config, next_label, next_parent_frame)

    @staticmethod
    def _deduplicate(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """한국어 strip().lower() 키 기준 첫 발견 유지."""
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for text, label in items:
            stripped = text.strip()
            key = stripped.lower()
            if key and key not in seen:
                seen.add(key)
                result.append((stripped, label))
        return result
