import json
import logging

import anthropic

from glossary import GLOSSARY, RULES

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
CHUNK_SIZE = 20
MAX_EXISTING_ROWS = 500

# CJK 키("일본어")는 모델이 한자 혼용으로 손상시키는 사례가 있어 ASCII 코드로 주고받는다
_LANG_CODES = {
    "영어": "en",
    "일본어": "ja",
    "중국어(간체)": "zh-cn",
    "중국어(번체)": "zh-tw",
}

_POLICY = """\
너는 이 프로젝트의 번역 어시스턴트다. 한국어 UI 텍스트를 요청된 언어로 번역한다.

== 우선순위 (위에서부터 강함) ==
1. 표기 규칙 (RULES 섹션)
2. 결제 도메인 용어집 (GLOSSARY 섹션) — 원문에 정확히 등장하면 지정 표기 사용
3. 이 표의 기존 번역 — 동일/유사 용어의 스타일·표기 재사용
4. 아래 디폴트 번역 정책

== 디폴트 번역 정책 ==
- 메뉴/카테고리/일반 용어 (예: 회사소개, 채용, 비전) → 일반적 직역
- 마케팅 카피/슬로건 (긴 문장·단락) → 자연스러운 의역
- 회사명/브랜드명 (예: 이롬넷, 페이버스) → 영어는 공식 표기, 일본어·중국어는 음역
- 업계 약어 (예: PG = Payment Gateway) → 원문 보존
- 주소·전화·이메일·사업자번호 → 번역 스킵 (빈 문자열)
- 더미/placeholder 텍스트 → 번역 스킵 (빈 문자열)
- 이미 영어인 항목 (예: Contact Us) → 영어는 원문 유지, 일본어·중국어만 번역
"""


def suggest_batch(
    existing_rows: list[dict],
    items: list[dict],
    target_langs: list[str],
) -> list[dict[str, str]]:
    """한국어 항목들을 target_langs 로 번역.

    existing_rows: get_table_info()["rows"] — few-shot 재료 (시스템 프롬프트에 캐시)
    items: [{"페이지 구분": "홈", "한국어": "독서 노트"}, ...]
    target_langs: 체크된 언어(정규화)만
    반환: items 와 같은 순서의 [{언어: 번역문}, ...] — 파싱 실패 항목은 빈 문자열.
    """
    if not items or not target_langs:
        return [{} for _ in items]

    client = anthropic.Anthropic()
    system = _build_system(existing_rows)

    results: list[dict[str, str]] = []
    for start in range(0, len(items), CHUNK_SIZE):
        chunk = items[start : start + CHUNK_SIZE]
        results.extend(_translate_chunk(client, system, chunk, target_langs))
    return results


def _build_system(existing_rows: list[dict]) -> list[dict]:
    sample = existing_rows[-MAX_EXISTING_ROWS:]
    table_json = json.dumps(sample, ensure_ascii=False, sort_keys=True)
    sections = [_POLICY, _format_glossary(), f"== 이 표의 기존 번역 ==\n{table_json}"]
    text = "\n".join(s for s in sections if s)
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _format_glossary() -> str:
    parts: list[str] = []
    if RULES:
        parts.append("== 표기 규칙 (RULES — 최우선) ==")
        parts.extend(f"- {rule}" for rule in RULES)
    if GLOSSARY:
        if parts:
            parts.append("")
        parts.append("== 결제 도메인 용어집 (GLOSSARY — 정확 일치 시 지정 표기 사용) ==")
        for ko, trans in GLOSSARY.items():
            trans_str = " / ".join(f"{code}={val}" for code, val in trans.items())
            parts.append(f"- {ko} → {trans_str}")
    return "\n".join(parts)


def _translate_chunk(
    client: anthropic.Anthropic,
    system: list[dict],
    chunk: list[dict],
    target_langs: list[str],
) -> list[dict[str, str]]:
    codes = {lang: _LANG_CODES[lang] for lang in target_langs}
    user_prompt = (
        "다음 한국어 항목들을 아래 언어로 번역해줘.\n"
        f"언어: {json.dumps(codes, ensure_ascii=False)}\n"
        f"항목: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        "translations 배열의 길이와 순서는 입력 항목과 동일해야 한다. "
        '번역 스킵 대상은 빈 문자열 "" 로 채운다.'
    )
    schema = {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {code: {"type": "string"} for code in codes.values()},
                    "required": list(codes.values()),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["translations"],
        "additionalProperties": False,
    }
    empty = [{lang: "" for lang in target_langs} for _ in chunk]

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APIError:
        logger.exception("Anthropic API 호출 실패 (chunk %d건)", len(chunk))
        return empty

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)["translations"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.error("번역 응답 파싱 실패 — 빈 값으로 대체:\n%s", text[:500])
        return empty

    out = []
    for i in range(len(chunk)):
        item = parsed[i] if i < len(parsed) and isinstance(parsed[i], dict) else {}
        out.append(
            {lang: str(item.get(code, "")).strip() for lang, code in codes.items()}
        )
    return out
