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
# 사람인/잡코리아/자소설닷컴 에서 "보험" 키워드 정규직 공고 검색결과 모니터링
# 회사명에 "보험"이 포함된 회사의 신규 공고 감지

TARGETS = [

    # ══ 사람인 — 보험 키워드 정규직 검색결과 ══
    {
        "name": "[사람인] 보험사 정규직 공고",
        "url": "https://www.saramin.co.kr/zf_user/jobs/list/job-category?cat_kewd=2247&loc_mcd=101000%2C102000&edu_min=7&job_type=1&search_optional_item=n&search_done=y&panel_count=y&preview=1&isAjaxRequest=0&page_count=50&sort=RL&type=job&is_param=1&isSearchResultEmpty=1&isSectionHome=0&searchParamCount=2",
        "conditions": [{"type": "new_post_with_keyword", "keyword": "보험"}],
        "link": "https://www.saramin.co.kr/zf_user/jobs/list/job-category?cat_kewd=2247&job_type=1",
    },

    # ══ 사람인 — 보험 키워드 직접 검색 (정규직) ══
    {
        "name": "[사람인] 보험 정규직 검색",
        "url": "https://www.saramin.co.kr/zf_user/jobs/list/job-category?search_keywords=%EB%B3%B4%ED%97%98&job_type=1&search_done=y&recruitPage=1&recruitSort=relation&recruitPageCount=40",
        "conditions": [{"type": "new_post_with_keyword", "keyword": "보험"}],
        "link": "https://www.saramin.co.kr/zf_user/jobs/list/job-category?search_keywords=%EB%B3%B4%ED%97%98&job_type=1",
    },

    # ══ 잡코리아 — 보험업종 정규직 검색결과 ══
    {
        "name": "[잡코리아] 보험사 정규직 공고",
        "url": "https://www.jobkorea.co.kr/Search/?stext=%EB%B3%B4%ED%97%98&tabType=recruit&EmpType=1&OrderBy=1",
        "conditions": [{"type": "new_post_with_keyword", "keyword": "보험"}],
        "link": "https://www.jobkorea.co.kr/Search/?stext=%EB%B3%B4%ED%97%98&tabType=recruit&EmpType=1",
    },

    # ══ 자소설닷컴 — 보험 키워드 공고 ══
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
    """
    HTML에서 회사명에 '보험'이 포함된 공고 목록 추출
    공고 제목 + 회사명 텍스트 블록을 파싱해서 보험사 공고만 필터링
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # "보험"이 포함된 줄 주변 공고 감지
    insurance_lines = [l for l in lines if keyword in l and len(l) < 100]
    return insurance_lines

def count_insurance_jobs(html, keyword="보험"):
    """회사명에 '보험' 포함된 공고 수 추정"""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    # "보험" 키워드 등장 횟수로 공고 수 추정
    return text.count(keyword)

def get_new_items(current_jobs, prev_jobs):
    """이전에 없던 새 공고 항목 추출"""
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
            # 현재 보험 키워드 등장 횟수
            current_count = count_insurance_jobs(html, keyword)
            prev_count = prev.get("count")

            # 현재 공고 샘플 텍스트 (상위 20개 보험 관련 라인)
            current_jobs = extract_insurance_jobs(html, keyword)[:20]
            prev_jobs = prev.get("jobs", [])

            print(f"  '{keyword}' 키워드 현재:{current_count}회 / 이전:{prev_count}회")

            new_items = get_new_items(current_jobs, prev_jobs) if prev_jobs else []

            if prev_count is not None and current_count > prev_count:
                now = datetime.now().strftime("%Y-%m-%d %H:%M")

                # 새 공고 목록 (최대 5개 표시)
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

            # 스냅샷 업데이트
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
