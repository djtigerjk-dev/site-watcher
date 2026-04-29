import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ── 설정 ─────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SNAPSHOT_FILE = "snapshots.json"

# ── 모니터링 대상 목록 ────────────────────────────────────────────────────────
TARGETS = [

    # ══ 기준A : 그룹 통합 채용사이트 (회사명 키워드 조건) ══

    {
        "name": "삼성생명",
        "url": "https://www.samsungcareers.com/hr/",
        "conditions": [
            {"type": "keyword_appear", "keyword": "삼성생명"},
        ],
    },
    {
        "name": "삼성화재",
        "url": "https://www.samsungcareers.com/hr/",
        "conditions": [
            {"type": "keyword_appear", "keyword": "삼성화재"},
        ],
    },
    {
        "name": "한화손해보험",
        "url": "https://www.hanwhain.com/portal/apply/recruit",
        "conditions": [
            {"type": "keyword_appear", "keyword": "한화손해보험"},
        ],
    },
    {
        "name": "한화생명",
        "url": "https://www.hanwhain.com/portal/apply/recruit",
        "conditions": [
            {"type": "keyword_appear", "keyword": "한화생명"},
        ],
    },

    # ══ 기준B : 자사 단독 채용사이트 (새 공고 등록 시 전부 알람) ══

    {
        "name": "신한라이프",
        "url": "https://shinhan-life.recruiter.co.kr/career/job",
        "conditions": [
            {"type": "new_post"},
            {"type": "content_change"},
        ],
    },
    {
        "name": "현대해상",
        "url": "https://hi.recruiter.co.kr/career/recruit",
        "conditions": [
            {"type": "new_post"},
            {"type": "content_change"},
        ],
    },
    {
        "name": "KB손해보험",
        "url": "https://kbinsure.recruiter.co.kr/app/jobnotice/list",
        "conditions": [
            {"type": "new_post"},
            {"type": "content_change"},
        ],
    },
]

# ── 유틸 ──────────────────────────────────────────────────────────────────────

def load_snapshots():
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_snapshots(data):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fetch_page(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text

def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True).lower()

def count_items(html):
    soup = BeautifulSoup(html, "html.parser")
    # recruiter.co.kr 계열은 <li> 기반 목록 구조
    return len(soup.find_all(["li", "tr", "article"]))

def content_hash(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return hashlib.md5(text[:8000].encode()).hexdigest()

# ── 텔레그램 발송 ─────────────────────────────────────────────────────────────

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠ TELEGRAM_TOKEN 또는 TELEGRAM_CHAT_ID 환경변수 없음")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    print(f"✅ 텔레그램 전송: {message[:60]}")

# ── 조건 체크 ─────────────────────────────────────────────────────────────────

def check_target(target, snapshots):
    name = target["name"]
    url = target["url"]
    conditions = target["conditions"]
    key = hashlib.md5((name + url).encode()).hexdigest()[:10]

    print(f"\n🔍 [{name}] 확인 중...")

    try:
        html = fetch_page(url)
    except Exception as e:
        print(f"  ❌ 접근 실패: {e}")
        return

    text = extract_text(html)
    prev = snapshots.get(key, {})
    triggered = []

    for cond in conditions:
        ctype = cond.get("type")

        if ctype == "keyword_appear":
            kw = cond.get("keyword", "")
            if kw.lower() in text:
                triggered.append(f'🔑 키워드 <b>"{kw}"</b> 공고 발견!')

        elif ctype == "content_change":
            h = content_hash(html)
            prev_hash = prev.get("hash")
            if prev_hash and prev_hash != h:
                triggered.append("📝 페이지 내용이 변경되었습니다")
            snapshots.setdefault(key, {})["hash"] = h

        elif ctype == "new_post":
            count = count_items(html)
            prev_count = prev.get("count")
            if prev_count is not None and count > prev_count:
                triggered.append(f"📋 새 공고 감지! ({prev_count}개 → {count}개)")
            snapshots.setdefault(key, {})["count"] = count

    if triggered:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = (
            f"🚨 <b>[채용공고 알람]</b>\n\n"
            f"🏢 <b>{name}</b>\n"
            f"🔗 {url}\n"
            f"⏰ {now}\n\n"
            + "\n".join(triggered)
        )
        send_telegram(msg)
    else:
        print(f"  ✅ 조건 미충족 — 이상 없음")

# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print(f"채용공고 모니터링 실행 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    snapshots = load_snapshots()

    for target in TARGETS:
        check_target(target, snapshots)

    save_snapshots(snapshots)
    print("\n✅ 완료")

if __name__ == "__main__":
    main()
