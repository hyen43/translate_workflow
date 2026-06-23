"""CLI 진입점 — sqlite 에 등록된 모든 페어를 순회하며 동기화."""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

import db
from confluence_client import ConfluenceClient
from figma_client import FigmaClient

load_dotenv()


def validate_env() -> tuple[str, str, str]:
    figma_token = os.getenv("FIGMA_TOKEN")
    confluence_email = os.getenv("CONFLUENCE_EMAIL")
    confluence_token = os.getenv("CONFLUENCE_TOKEN")

    missing = [
        name
        for name, val in [
            ("FIGMA_TOKEN", figma_token),
            ("CONFLUENCE_EMAIL", confluence_email),
            ("CONFLUENCE_TOKEN", confluence_token),
        ]
        if not val
    ]
    if missing:
        print(f"[Error] Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    return figma_token, confluence_email, confluence_token


def run_pair(pair: dict, figma_token: str, email: str, token: str) -> dict:
    """단일 페어 실행. 결과 dict 반환."""
    figma = FigmaClient(figma_token)
    confluence = ConfluenceClient(domain=pair["confluence_domain"], email=email, token=token)

    try:
        figma_terms = figma.get_terms(
            file_key=pair["file_key"],
            page_name=pair["page_name"],
            filter_config={"type": pair["filter_type"], "values": pair["filter_values"]},
        )
    except Exception as e:
        return {"error": f"Figma 추출 실패: {e}"}

    try:
        existing_terms = confluence.get_terms(
            page_id=pair["page_id"], table_type=pair["table_type"]
        )
    except Exception as e:
        return {"error": f"Confluence 조회 실패: {e}"}

    existing_set = {t.strip().lower() for t in existing_terms}
    new_terms = [(text, label) for text, label in figma_terms if text.strip().lower() not in existing_set]

    if not new_terms:
        return {
            "figma_count": len(figma_terms),
            "existing_count": len(existing_terms),
            "added": 0,
            "added_terms": [],
        }

    try:
        confluence.add_terms(
            page_id=pair["page_id"],
            new_terms=new_terms,
            table_type=pair["table_type"],
        )
    except Exception as e:
        return {"error": f"Confluence 업데이트 실패: {e}"}

    return {
        "figma_count": len(figma_terms),
        "existing_count": len(existing_terms),
        "added": len(new_terms),
        "added_terms": new_terms,
    }


def main():
    figma_token, email, token = validate_env()

    db.init_db()
    pairs = db.list_pairs()

    if not pairs:
        print("등록된 페어가 없습니다.")
        print("  → `streamlit run app.py` 로 웹 UI를 열고 페어를 등록하세요.")
        return

    print(f"총 {len(pairs)}개 페어 실행 시작\n")
    results = []
    for i, pair in enumerate(pairs, 1):
        print(f"[{i}/{len(pairs)}] {pair['name']}")
        r = run_pair(pair, figma_token, email, token)
        results.append((pair, r))

        if "error" in r:
            db.update_last_sync(pair["id"], f"ERROR: {r['error']}", 0)
            print(f"  ❌ {r['error']}\n")
            continue

        db.update_last_sync(pair["id"], "OK", r["added"])
        print(
            f"  Figma {r['figma_count']}개 / Confluence 기존 {r['existing_count']}개"
            f" → 신규 {r['added']}개"
        )
        if r["added"]:
            preview = [
                f"[{label}] {text}" if label else text
                for text, label in r["added_terms"][:5]
            ]
            ellipsis = "..." if r["added"] > 5 else ""
            print(f"    추가: {preview}{ellipsis}")
        print()

    print("=" * 50)
    total_added = sum(r.get("added", 0) for _, r in results)
    failed = [(p, r) for p, r in results if "error" in r]
    print(f"완료: {len(pairs)}개 페어, 신규 총 {total_added}개 추가, 실패 {len(failed)}개")

    pairs_with_new = [(p, r) for p, r in results if r.get("added", 0) > 0]
    if pairs_with_new:
        print("\n📝 다음 단계 — Claude에게 다국어 번역을 요청하세요:")
        for p, r in pairs_with_new:
            print(f"  - '{p['name']}' (page_id: {p['page_id']}, {p['table_type']}): {r['added']}개 신규")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
