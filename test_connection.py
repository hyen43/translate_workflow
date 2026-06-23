import base64
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

figma_token = os.getenv("FIGMA_TOKEN")
confluence_email = os.getenv("CONFLUENCE_EMAIL")
confluence_token = os.getenv("CONFLUENCE_TOKEN")

try:
    with open("config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    confluence_domain = cfg.get("confluence_domain")
    jobs = cfg.get("jobs", [])
except Exception as e:
    print(f"config.json 읽기 실패: {e}")
    sys.exit(1)

print("=" * 50)

# Figma
print("[Figma]")
try:
    r = requests.get(
        "https://api.figma.com/v1/me",
        headers={"X-Figma-Token": figma_token},
        timeout=10,
    )
    if r.status_code == 200:
        j = r.json()
        print(f"  연결 성공: {j.get('name', '')} ({j.get('email', '')})")
    elif r.status_code == 403:
        print("  토큰 유효 (파일 읽기 권한 확인됨)")
    elif r.status_code == 401:
        print("  연결 실패: 토큰이 유효하지 않아요. Figma에서 토큰을 다시 발급해 주세요.")
    else:
        print(f"  연결 실패: {r.status_code} - {r.text}")
except Exception as e:
    print(f"  오류: {e}")

print()

# Confluence
print("[Confluence]")
if not confluence_domain or confluence_domain == "your-domain":
    print("  도메인 미설정. config.json 의 confluence_domain 을 입력해 주세요.")
    sys.exit(1)
if not jobs:
    print("  jobs 가 비어있어요. config.json 에 최소 1개 등록 후 다시 시도해 주세요.")
    sys.exit(1)

credentials = base64.b64encode(f"{confluence_email}:{confluence_token}".encode()).decode()
auth_headers = {"Authorization": f"Basic {credentials}", "Accept": "application/json"}

fail = 0
for job in jobs:
    name = job.get("name", "(unnamed)")
    page_id = job["confluence"]["page_id"]
    url = f"https://{confluence_domain}.atlassian.net/wiki/rest/api/content/{page_id}?expand=version"
    try:
        r = requests.get(url, headers=auth_headers, timeout=10)
        if r.status_code == 200:
            title = r.json().get("title", "")
            print(f"  ✅ '{name}' → '{title}' (page {page_id})")
        else:
            fail += 1
            print(f"  ❌ '{name}' (page {page_id}) {r.status_code}: {r.text[:200]}")
    except Exception as e:
        fail += 1
        print(f"  ❌ '{name}' (page {page_id}) 오류: {e}")

print()
if fail == 0:
    print(f"모든 {len(jobs)}개 페이지 접근 OK. sync.py 실행 가능합니다.")
else:
    print(f"{fail}/{len(jobs)}개 페이지 접근 실패. 토큰·페이지ID·권한 확인 필요.")
    print()
    print("[해결 방법]")
    print("  - id.atlassian.com → Security → API tokens 에서 토큰 재발급 ('Create API token' Classic)")
    print("  - 시크릿 창에서 본인 계정으로 로그인된 상태로 발급했는지 확인")
    sys.exit(1)

print("=" * 50)
