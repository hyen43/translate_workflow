"""결제 도메인 용어집 — translator.py 시스템 프롬프트에 주입되어 번역 톤을 강제한다.

편집 가이드
-----------
1. GLOSSARY : 한국어 원문 → {언어코드: 지정 번역} 매핑
   - 원문에 정확히 이 표현이 나오면 지정된 표기를 그대로 사용하도록 모델에 지시된다
   - 언어 코드는 4개(en / ja / zh-cn / zh-tw). 없는 언어는 생략 가능
   - 예: "가맹점": {"en": "merchant", "ja": "加盟店", "zh-cn": "商户", "zh-tw": "商戶"}

2. RULES : 표기 규칙(한 줄씩) — 용어 1:1 매핑으로 표현하기 어려운 정책
   - 예: "브랜드명 '페이버스'는 영어로 'Fabus'로 표기한다"
   - 예: "'매입'은 정산 문맥에서는 'settlement', 카드 승인 문맥에서는 'capture'로 구분한다"

우선순위: RULES > GLOSSARY > 대상 Confluence 표의 기존 번역 > 디폴트 정책.
용어집은 시스템 프롬프트에 캐시되므로 자주 바꾸면 캐시가 무효화된다.
"""

# "번역 표"(Confluence 217055245) 기존 번역에서 학습한 확정 표기 (2026-07-21)
GLOSSARY: dict[str, dict[str, str]] = {
    # 회사·브랜드
    "이롬넷": {"en": "Eromnet", "ja": "Eromnet", "zh-cn": "Eromnet", "zh-tw": "Eromnet"},
    "주식회사 이롬넷": {
        "en": "Eromnet Co., Ltd.",
        "ja": "Eromnet株式会社",
        "zh-cn": "Eromnet股份有限公司",
        "zh-tw": "Eromnet股份有限公司",
    },
    "페이버스": {"en": "PayVerse", "ja": "PayVerse", "zh-cn": "PayVerse", "zh-tw": "PayVerse"},
    # 결제 도메인
    "글로벌 PG": {"en": "Global PG", "ja": "グローバルPG", "zh-cn": "全球PG", "zh-tw": "全球PG"},
    "핀테크": {"en": "fintech", "ja": "フィンテック", "zh-cn": "金融科技", "zh-tw": "金融科技"},
    "결제": {"en": "payment", "ja": "決済", "zh-cn": "支付", "zh-tw": "支付"},
    "거래": {"en": "transaction", "ja": "取引", "zh-cn": "交易", "zh-tw": "交易"},
    "이상거래 탐지": {
        "en": "fraud detection",
        "ja": "不正取引検知",
        "zh-cn": "欺诈检测",
        "zh-tw": "欺詐檢測",
    },
    "사용자 인증": {
        "en": "user authentication",
        "ja": "ユーザー認証",
        "zh-cn": "用户认证",
        "zh-tw": "用戶認證",
    },
    "생체 보안": {
        "en": "biometric security",
        "ja": "生体セキュリティ",
        "zh-cn": "生物识别安全",
        "zh-tw": "生物識別安全",
    },
    "파트너사": {"en": "partner", "ja": "パートナー企業", "zh-cn": "合作伙伴", "zh-tw": "合作夥伴"},
    "인프라": {"en": "infrastructure", "ja": "インフラ", "zh-cn": "基础设施", "zh-tw": "基礎設施"},
    # UI·메뉴 고정 표기
    "문의하기": {"en": "Contact Us", "ja": "お問い合わせ", "zh-cn": "联系我们", "zh-tw": "聯絡我們"},
    "이용약관": {"en": "Terms of Service", "ja": "利用規約", "zh-cn": "用户协议", "zh-tw": "使用條款"},
    "공지사항": {"en": "Notices", "ja": "お知らせ", "zh-cn": "公告", "zh-tw": "公告"},
    "보도자료": {"en": "Press Releases", "ja": "プレスリリース", "zh-cn": "新闻稿", "zh-tw": "新聞稿"},
    "채용": {"en": "Careers", "ja": "採用情報", "zh-cn": "招聘", "zh-tw": "招聘"},
    "블로그": {"en": "Blog", "ja": "ブログ", "zh-cn": "博客", "zh-tw": "部落格"},
}

RULES: list[str] = [
    "회사명 '이롬넷'은 모든 언어에서 라틴 표기 'Eromnet'을 사용한다. 음역(イロムネット, 伊罗姆网, 伊羅姆網)은 사용하지 않는다.",
    "브랜드 '페이버스'는 모든 언어에서 'PayVerse'로 표기한다. 기존 표의 'Faverse' 표기는 사용하지 않는다.",
    "'PG', 'C.I' 등 업계 약어·이니셜은 모든 언어에서 원문 그대로 유지한다.",
    "중국어(번체)는 대만 표기 관행을 따른다: 連結(연결), 部落格(블로그), 營運(운영), 透過(~을 통해) 등 간체와 어휘가 다른 경우 대만식 어휘를 쓴다.",
    "원문에 포함된 ↗ 등 기호와 특수문자는 번역문에도 그대로 보존한다.",
]
