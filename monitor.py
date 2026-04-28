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

# ── 모니터링 대상 목록 ──────────────────────────────────────────────────────
# 아래 TARGETS 리스트에 원하는 사이트와 조건을 추가하세요.
# conditions 종류:
#   {"type": "keyword_appear",    "keyword": "채용"}   → 키워드가 등장하면 알람
#   {"type": "keyword_disappear", "keyword": "마감"}   → 키워드가 사라지면 알람
#   {"type": "content_change"}                         → 페이지 내용이 바뀌면 알람
#   {"type": "new_post"}                               → 목록 항목 수가 늘어나면 알람

TARGETS = [
    {
        "name": "삼성생명 채용",
        "url": "https://www.samsunglife.com/recruit/",
        "conditions": [
            {"type": "keyword_appear", "keyword": "공개채용"},
            {"type": "new_post"},
        ],
    },
    # 추가 예시 (주석 해제 후 사용)
    # {
    #     "name": "DB손해보험 채용",
    #     "url": "https://recruit.idongbu.com/",
    #     "conditions": [
    #         {"type": "keyword_appear", "keyword": "채용"},
    #         {"type": "content_change"},
    #     ],
    # },
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
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SiteWatcher/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.text

def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True).lower()

def count_items(html):
    soup = BeautifulSoup(html, "html.parser")
    return len(soup.find_all(["li", "tr", "article"]))

def content_hash(html):
    return hashlib.md5(html[:5000].encode()).hexdigest()

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
    print(f"✅ 텔레그램 전송 완료: {message[:60]}")

# ── 조건 체크 ─────────────────────────────────────────────────────────────────

def check_target(target, snapshots):
    name = target["name"]
    url = target["url"]
    conditions = target["conditions"]
    key = hashlib.md5(url.encode()).hexdigest()[:8]

    print(f"\n🔍 [{name}] 확인 중... {url}")

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
            kw = cond.get("keyword", "").lower()
            if kw and kw in text:
                triggered.append(f'🔑 키워드 <b>"{cond["keyword"]}"</b> 발견')

        elif ctype == "keyword_disappear":
            kw = cond.get("keyword", "").lower()
            prev_had = prev.get(f"kw_{kw}", False)
            now_has = kw in text
            if prev_had and not now_has:
                triggered.append(f'🔕 키워드 <b>"{cond["keyword"]}"</b> 사라짐')
            snapshots.setdefault(key, {})[f"kw_{kw}"] = now_has

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
                triggered.append(f"📋 새 게시물 감지 ({prev_count}개 → {count}개)")
            snapshots.setdefault(key, {})["count"] = count

    if triggered:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = (
            f"🚨 <b>[SITE WATCHER 알람]</b>\n\n"
            f"📌 <b>{name}</b>\n"
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
    print(f"SITE WATCHER 실행 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    snapshots = load_snapshots()

    for target in TARGETS:
        check_target(target, snapshots)

    save_snapshots(snapshots)
    print("\n✅ 스냅샷 저장 완료")

if __name__ == "__main__":
    main()
