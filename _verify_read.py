import json
import os
import re
import sys

import requests
from dotenv import load_dotenv

from confluence_client import ConfluenceClient
from figma_client import FigmaClient

load_dotenv()

FIGMA_FILE_KEY = "V6MvaBvFEqdzFBrfJHZCFJ"
CONFLUENCE_DOMAIN = "linapersonal"
TINY_URL = "https://linapersonal.atlassian.net/wiki/x/DQDwD"

# 1) Confluence 단축 URL → page_id
cc = ConfluenceClient(
    CONFLUENCE_DOMAIN, os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_TOKEN"]
)
r = requests.get(TINY_URL, headers=cc.headers, allow_redirects=True)
m = re.search(r"/pages/(\d+)", r.url)
if not m:
    sys.exit(f"page_id 추출 실패: 최종 URL = {r.url}")
page_id = m.group(1)
print(f"[Confluence] page_id = {page_id}")

# 2) 표 확인
info = cc.get_table_info(page_id)
print(f"[Confluence] 페이지 제목: {info['page_title']}")
print(f"[Confluence] 원본 헤더: {info['headers']}")
print(f"[Confluence] 감지된 언어 컬럼: {info['langs']}")
print(f"[Confluence] 기존 행 수: {len(info['rows'])}")
for row in info["rows"][:5]:
    print("   ", json.dumps(row, ensure_ascii=False))

# 3) Figma 텍스트 수집
fc = FigmaClient(os.environ["FIGMA_TOKEN"])
terms = fc.get_terms(FIGMA_FILE_KEY)
print(f"\n[Figma] 수집된 용어 수 (중복 제거 후): {len(terms)}")
for text, label in terms[:20]:
    print(f"    ({label}) {text}")

# 4) 차집합 (신규 용어)
existing = {row.get("한국어", "").strip().lower() for row in info["rows"]}
new_terms = [(t, l) for t, l in terms if t.strip().lower() not in existing]
print(f"\n[차집합] 신규 용어 수: {len(new_terms)}")
for text, label in new_terms[:20]:
    print(f"    ({label}) {text}")
