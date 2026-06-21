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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# ── 모니터링 대상 ─────────────────────────────────────────────────────────────
# 자소설닷컴에서 "보험" 키워드 신규 공고 감지

TARGETS = [
    {
        "name": "[자소설닷컴] 보험사 공고",
        "url": "https://jasoseol.com/recruit?keyword=%EB%B3%B4%ED%97%98&employment_type=1",
        "conditions": [{"type": "new_post_with_keyword", "keyword": "보험"}],
        "link": "https://jasoseol.com/recruit?keyword=%EB%B3%B4%ED%97%98",
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
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text

def extract_insurance_jobs(html, keyword="보험"):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    insurance_lines = [l for l in lines if keyword in l and len(l) < 100]
    return insurance_lines

def count_insurance_jobs(html, keyword="보험"):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return text.count(keyword)

def get_new_items(current_jobs, prev_jobs):
    prev_set = set(prev_jobs)
    return [j for j in current_jobs if j not in prev_set]

# ── 텔레그램 발송 ─────────────────────────────────────────────────────────────

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠ TELEGRAM_TOKEN 또는 TELEGRAM_CHAT_ID 없음")
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
    print(f"✅ 텔레그램 전송 완료")

# ── 조건 체크 ─────────────────────────────────────────────────────────────────

def check_target(target, snapshots):
    name = target["name"]
    url = target["url"]
    link = target.get("link", url)
    conditions = target["conditions"]
    key = hashlib.md5((name + url).encode()).hexdigest()[:10]

    print(f"\n🔍 {name} 확인 중...")

    try:
        html = fetch_page(url)
    except Exception as e:
        print(f"  ❌ 접근 실패: {e}")
        return

    prev = snapshots.get(key, {})

    for cond in conditions:
        ctype = cond.get("type")
        keyword = cond.get("keyword", "보험")

        if ctype == "new_post_with_keyword":
            current_count = count_insurance_jobs(html, keyword)
            prev_count = prev.get("count")

            current_jobs = extract_insurance_jobs(html, keyword)[:20]
            prev_jobs = prev.get("jobs", [])

            print(f"  '{keyword}' 키워드 현재:{current_count}회 / 이전:{prev_count}회")

            new_items = get_new_items(current_jobs, prev_jobs) if prev_jobs else []

            if prev_count is not None and current_count > prev_count:
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                new_list = "\n".join(f"• {j}" for j in new_items[:5]) if new_items else "• 신규 공고 확인 필요"

                msg = (
                    f"🚨 <b>[보험사 채용공고 알람]</b>\n\n"
                    f"📌 <b>{name}</b>\n"
                    f"⏰ {now}\n\n"
                    f"📋 신규 보험사 공고 감지!\n"
                    f"(이전 {prev_count}건 → 현재 {current_count}건)\n\n"
                    f"{new_list}\n\n"
                    f"🔗 {link}"
                )
                send_telegram(msg)
            else:
                print(f"  ✅ 변동 없음")

            snapshots.setdefault(key, {})["count"] = current_count
            snapshots.setdefault(key, {})["jobs"] = current_jobs

# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print(f"보험사 채용공고 모니터링 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    snapshots = load_snapshots()

    for target in TARGETS:
        check_target(target, snapshots)

    save_snapshots(snapshots)
    print("\n✅ 전체 완료")

if __name__ == "__main__":
    main()
