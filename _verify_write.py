import logging
import os
import re
import sys

import requests
from dotenv import load_dotenv

import translator
from confluence_client import ConfluenceClient, norm_key
from figma_client import FigmaClient

logging.basicConfig(level=logging.INFO)
load_dotenv()

FIGMA_FILE_KEY = "V6MvaBvFEqdzFBrfJHZCFJ"
CONFLUENCE_DOMAIN = "linapersonal"
TINY_URL = "https://linapersonal.atlassian.net/wiki/x/DQDwD"
SELECTED_LANGS = ["영어", "일본어", "중국어(간체)", "중국어(번체)"]

cc = ConfluenceClient(
    CONFLUENCE_DOMAIN, os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_TOKEN"]
)
r = requests.get(TINY_URL, headers=cc.headers, allow_redirects=True)
page_id = re.search(r"/pages/(\d+)", r.url).group(1)

# 1) 표 확인
info = cc.get_table_info(page_id)
print(f"[1/4] 표 확인: {info['page_title']} — 기존 {len(info['rows'])}행, 언어 {info['langs']}")

# 2) Figma 수집 + 차집합
fc = FigmaClient(os.environ["FIGMA_TOKEN"])
terms = fc.get_terms(FIGMA_FILE_KEY)
existing_ko = {norm_key(row.get("한국어", "")) for row in info["rows"]}
new_rows = [(t, l) for t, l in terms if norm_key(t) not in existing_ko]
print(f"[2/4] Figma {len(terms)}개 수집 → 신규 {len(new_rows)}개")

# 3) 번역 대상 = 신규 전부 + 기존 행 중 체크 언어 빈 셀이 있는 행
items = [{"페이지 구분": label, "한국어": ko} for ko, label in new_rows]
for row in info["rows"]:
    ko = row.get("한국어", "").strip()
    if not ko:
        continue
    if any(not row.get(lang, "").strip() for lang in SELECTED_LANGS):
        items.append({"페이지 구분": row.get("페이지 구분", ""), "한국어": ko})

print(f"[3/4] 번역 요청: {len(items)}건 × {len(SELECTED_LANGS)}개 언어 (Haiku 호출 중...)")
results = translator.suggest_batch(info["rows"], items, SELECTED_LANGS)

translations = {norm_key(item["한국어"]): res for item, res in zip(items, results)}
sample = list(translations.items())[:5]
for ko_key, t in sample:
    print(f"    {ko_key!r} → {t}")

# 4) 동기화 실행 (단일 PUT)
summary = cc.sync_table(page_id, SELECTED_LANGS, new_rows, translations)
print(f"[4/4] 완료: {summary}")

sys.exit(0)
