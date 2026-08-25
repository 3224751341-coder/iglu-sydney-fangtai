#!/usr/bin/env python3
"""
Iglu 澳洲全城房态抓取 + 网页更新脚本（悉尼 / 墨尔本 / 布里斯班）
用法: python3 update_fangtai.py [--no-deploy]
输出: 更新 index.html → 自动部署到 Cloudflare Pages
"""

import json, re, sys, os, subprocess, urllib.request
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Config ──
# trigger CI re-scrape
AGENT_CODE = "A1336"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(PROJECT_DIR, ".agent_cookies.txt")
TEMPLATE_PATH = os.path.join(PROJECT_DIR, "template.html")
OUTPUT_PATH = os.path.join(PROJECT_DIR, "index.html")
CLOUDFLARE_PROJECT = "iglu-centralpark"
MAX_WORKERS = 12
REQUEST_TIMEOUT = 25

# ── 变化检测 & 推送 ──
# 快照：存到仓库目录 + 随部署上线（https://iglu-centralpark.pages.dev/data_snapshot.json），下次运行优先读线上
SNAPSHOT_PATH = os.path.join(PROJECT_DIR, "data_snapshot.json")
SNAPSHOT_URL = f"https://{CLOUDFLARE_PROJECT}.pages.dev/data_snapshot.json"
WECOM_WEBHOOK = os.environ.get("WECOM_WEBHOOK", "")

# ── Cities & Properties ──
# 城市 slug → {label, properties: {显示名: slug}, room_meta, property_rooms}
CITIES = {
    "sydney": {
        "label": "悉尼",
        "properties": {
            "Broadway": "broadway",
            "Central": "central",
            "Central Park": "central-park",
            "Chatswood": "chatswood",
            "Mascot": "mascot",
            "Mascot Duo": "mascot-duo",   # 2027年1月开业，官网尚未发布可预订房型页 → Coming Soon 占位
            "Redfern": "redfern",
            "Summer Hill": "summer-hill",
            "Waterloo": "waterloo",
        },
        "room_meta": {
            # Broadway
            "standard-studio-apartment-nras-br": ("Standard Studio NRAS", "Studio", "17m²", "Queen", "NRAS补贴"),
            "single-bedroom-6-share-apt-br": ("6 Share Apt", "Share", "~13m²", "King Single", "6人"),
            "single-bedroom-5-share-apt-br": ("5 Share Apt", "Share", "~13m²", "King Single", "5人"),
            "single-bedroom-4-share-apt-br": ("4 Share Apt", "Share", "~13m²", "King Single", "4人"),
            "standard-studio-apartment-br": ("Standard Studio", "Studio", "17m²", "Queen", ""),
            "superior-studio-apartment-br": ("Superior Studio", "Studio", "21m²", "Queen+沙发", ""),
            "premium-studio-apartment-br": ("Premium Studio", "Studio", "31m²", "Queen+客厅", ""),
            # Central
            "single-bedroom-share-bathroom-ce": ("Single Share Bath", "Share", "~12m²", "King Single", "Share Bath"),
            "single-bedroom-6-share-apt-ce": ("6 Share Apt", "Share", "~13m²", "King Single", "6人"),
            "single-bedroom-5-share-apt-ce": ("5 Share Apt", "Share", "~13m²", "King Single", "5人"),
            "standard-studio-apartment-ce": ("Standard Studio", "Studio", "17m²", "Queen", ""),
            # Central Park
            "standard-studio-apartment-cp": ("Standard Studio", "Studio", "17m²", "Queen", ""),
            "superior-studio-apartment": ("Superior Studio", "Studio", "21m²", "Queen+沙发", ""),
            "premium-studio-apartment-cp": ("Premium Studio", "Studio", "31m²", "Queen+客厅", ""),
            "single-bedroom-6-share-apt-cp": ("6 Share Apt", "Share", "~13m²", "King Single", "6人"),
            "single-bedroom-4-share-apt-cp": ("4 Share Apt", "Share", "~13m²", "King Single", "4人"),
            "single-bedroom-3-share-apt-cp": ("3 Share Apt", "Share", "~13m²", "King Single", "3人"),
            "premium-studio-nras-cp": ("Premium Studio NRAS", "Studio", "31m²", "Queen", "NRAS补贴"),
            # Chatswood
            "single-bedroom-6-share-apt-ch": ("6 Share Apt", "Share", "~13m²", "King Single", "6人"),
            "single-bedroom-5-share-apt-ch": ("5 Share Apt", "Share", "~13m²", "King Single", "5人"),
            "single-bedroom-4-share-apt-ch": ("4 Share Apt", "Share", "~13m²", "King Single", "4人"),
            "standard-studio-apartment-ch": ("Standard Studio", "Studio", "17m²", "Queen", ""),
            "superior-studio-apartment-ch": ("Superior Studio", "Studio", "21m²", "Queen+沙发", ""),
            "premium-studio-apartment-ch": ("Premium Studio", "Studio", "31m²", "Queen+客厅", ""),
            # Mascot
            "single-bedroom-6-share-apt-ma": ("6 Share Apt", "Share", "~13m²", "King Single", "6人"),
            "premium-single-bedroom-6-share-ma": ("Premium 6 Share", "Share", "~14m²", "King Single", "6人"),
            "standard-studio-apartment-ma": ("Standard Studio", "Studio", "17m²", "Queen", ""),
            "premium-studio-apartment-ma": ("Premium Studio", "Studio", "31m²", "Queen+客厅", ""),
            "standard-studio-apartment-queen": ("Standard Studio Queen", "Studio", "17m²", "Queen", ""),
            # Redfern
            "single-bed-6-share-apt-saex-sre": ("6 Share SAEX", "Share", "~13m²", "King Single", "6人 USYD"),
            "single-bedroom-6-share-apt-re": ("6 Share Apt", "Share", "~13m²", "King Single", "6人"),
            "single-bedroom-5-share-apt-re": ("5 Share Apt", "Share", "~13m²", "King Single", "5人"),
            "single-bedroom-4-share-apt-re": ("4 Share Apt", "Share", "~13m²", "King Single", "4人"),
            "single-studio-apartment-re": ("Single Studio", "Studio", "15m²", "Double", ""),
            "standard-studio-apartment-re": ("Standard Studio", "Studio", "17m²", "Queen", ""),
            "premium-studio-apartment-re": ("Premium Studio", "Studio", "31m²", "Queen+客厅", ""),
            "single-bedroom-6-share-nras": ("6 Share NRAS", "Share", "~13m²", "King Single", "6人 NRAS"),
            "single-studio-apartment-nras": ("Single Studio NRAS", "Studio", "15m²", "Double", "NRAS"),
            "standard-studio-apartment-nras": ("Standard Studio NRAS", "Studio", "17m²", "Queen", "NRAS"),
            # Summer Hill
            "standard-studio-apartment-sh": ("Standard Studio", "Studio", "17m²", "Queen", ""),
            "premium-studio-apartment-sh": ("Premium Studio", "Studio", "31m²", "Queen+客厅", ""),
            # Waterloo
            "single-bedroom-2-share-apt-wa": ("2 Share Apt", "Share", "~13m²", "King Single", "2人"),
            "standard-studio-apartment-wa": ("Standard Studio", "Studio", "17m²", "Queen", ""),
            "superior-studio-apartment-wa": ("Superior Studio", "Studio", "21m²", "Queen+沙发", ""),
            "premium-studio-apartment-wa": ("Premium Studio", "Studio", "31m²", "Queen+客厅", ""),
        },
        "property_rooms": {
            "broadway": [
                "standard-studio-apartment-nras-br", "single-bedroom-6-share-apt-br",
                "single-bedroom-5-share-apt-br", "single-bedroom-4-share-apt-br",
                "standard-studio-apartment-br", "superior-studio-apartment-br",
                "premium-studio-apartment-br",
            ],
            "central": [
                "single-bedroom-share-bathroom-ce", "single-bedroom-6-share-apt-ce",
                "single-bedroom-5-share-apt-ce", "standard-studio-apartment-ce",
            ],
            "central-park": [
                "standard-studio-apartment-cp", "superior-studio-apartment",
                "premium-studio-apartment-cp", "single-bedroom-6-share-apt-cp",
                "single-bedroom-4-share-apt-cp", "single-bedroom-3-share-apt-cp",
                "premium-studio-nras-cp",
            ],
            "chatswood": [
                "single-bedroom-6-share-apt-ch", "single-bedroom-5-share-apt-ch",
                "single-bedroom-4-share-apt-ch", "standard-studio-apartment-ch",
                "superior-studio-apartment-ch", "premium-studio-apartment-ch",
            ],
            "mascot": [
                "single-bedroom-6-share-apt-ma", "premium-single-bedroom-6-share-ma",
                "standard-studio-apartment-ma", "premium-studio-apartment-ma",
                "standard-studio-apartment-queen",
            ],
            "mascot-duo": [],   # Coming Soon（2027年1月开业），房型 slug 待官网公布后补
            "redfern": [
                "single-bed-6-share-apt-saex-sre", "single-bedroom-6-share-apt-re",
                "single-bedroom-5-share-apt-re", "single-bedroom-4-share-apt-re",
                "single-studio-apartment-re", "standard-studio-apartment-re",
                "premium-studio-apartment-re", "single-bedroom-6-share-nras",
                "single-studio-apartment-nras", "standard-studio-apartment-nras",
            ],
            "summer-hill": [
                "standard-studio-apartment-sh", "premium-studio-apartment-sh",
            ],
            "waterloo": [
                "single-bedroom-2-share-apt-wa", "standard-studio-apartment-wa",
                "superior-studio-apartment-wa", "premium-studio-apartment-wa",
            ],
        },
    },

    "melbourne": {
        "label": "墨尔本",
        "properties": {
            "Flagstaff Gardens": "flagstaff-gardens",
            "Flagstaff Station": "flagstaff-station",
            "Melbourne Central": "melbourne-central",
            "Melbourne City": "melbourne-city",
            "South Yarra": "south-yarra",
        },
        "room_meta": {
            # Flagstaff Gardens
            "premium-corner-studio-apartment-fg": ("Premium Corner Studio", "Studio", "?", "Double", ""),
            "premium-single-bedroom-2-share-fg": ("Premium 2 Share", "Share", "?", "King Single", "2人"),
            "premium-studio-apartment-fg": ("Premium Studio", "Studio", "?", "Double", ""),
            "single-bedroom-2-share-apt-fg": ("2 Share Apt", "Share", "?", "King Single", "2人"),
            "single-studio-apartment": ("Single Studio", "Studio", "?", "King Single", ""),
            "standard-studio-apartment-fg": ("Standard Studio", "Studio", "?", "Double", ""),
            # Flagstaff Station
            "premium-studio-apartment-cnr-fs": ("Premium Studio Corner", "Studio", "?", "Queen", ""),
            "premium-studio-apartment-fs": ("Premium Studio", "Studio", "?", "Queen", ""),
            "single-bedroom-2-share-apt-fs": ("2 Share Apt", "Share", "?", "King Single", "2人"),
            "standard-studio-apartment-fs": ("Standard Studio", "Studio", "?", "Queen", ""),
            # Melbourne Central
            "premium-studio-apartment-mce": ("Premium Studio", "Studio", "?", "Double", ""),
            "standard-studio-apartment-mce": ("Standard Studio", "Studio", "?", "Double", ""),
            # Melbourne City
            "premium-studio-apartment-mc": ("Premium Studio", "Studio", "?", "Double", ""),
            "standard-studio-apartment-mc": ("Standard Studio", "Studio", "?", "Double", ""),
            "single-bedroom-5-share-apt-mc": ("5 Share Apt", "Share", "?", "King Single", "5人"),
            "single-bedroom-6-share-apt-mc": ("6 Share Apt", "Share", "?", "King Single", "6人"),
            # South Yarra
            "premium-single-bedroom-5-share-apt-sy": ("Premium 5 Share", "Share", "?", "King Single", "5人"),
            "premium-single-bedroom-6-share-apt-sy": ("Premium 6 Share", "Share", "?", "King Single", "6人"),
            "premium-studio-apartment-sy": ("Premium Studio", "Studio", "?", "King Single", ""),
            "single-bedroom-5-share-apt-sy": ("5 Share Apt", "Share", "?", "King Single", "5人"),
            "single-bedroom-6-share-apt-sy": ("6 Share Apt", "Share", "?", "King Single", "6人"),
            "single-studio-apartment-sy": ("Single Studio", "Studio", "?", "King Single", ""),
            "standard-studio-apartment-sy": ("Standard Studio", "Studio", "?", "King Single", ""),
        },
        "property_rooms": {
            "flagstaff-gardens": [
                "premium-corner-studio-apartment-fg", "premium-single-bedroom-2-share-fg",
                "premium-studio-apartment-fg", "single-bedroom-2-share-apt-fg",
                "single-studio-apartment", "standard-studio-apartment-fg",
            ],
            "flagstaff-station": [
                "premium-studio-apartment-cnr-fs", "premium-studio-apartment-fs",
                "single-bedroom-2-share-apt-fs", "standard-studio-apartment-fs",
            ],
            "melbourne-central": [
                "premium-studio-apartment-mce", "standard-studio-apartment-mce",
            ],
            "melbourne-city": [
                "premium-studio-apartment-mc", "standard-studio-apartment-mc",
                "single-bedroom-5-share-apt-mc", "single-bedroom-6-share-apt-mc",
            ],
            "south-yarra": [
                "premium-single-bedroom-5-share-apt-sy", "premium-single-bedroom-6-share-apt-sy",
                "premium-studio-apartment-sy", "single-bedroom-5-share-apt-sy",
                "single-bedroom-6-share-apt-sy", "single-studio-apartment-sy",
                "standard-studio-apartment-sy",
            ],
        },
    },

    "brisbane": {
        "label": "布里斯班",
        "properties": {
            "Brisbane City": "brisbane-city",
            "Kelvin Grove": "kelvin-grove",
        },
        "room_meta": {
            # Brisbane City
            "premium-studio-apartment-bc": ("Premium Studio", "Studio", "?", "Double", ""),
            "standard-studio-apartment-bc": ("Standard Studio", "Studio", "?", "Double", ""),
            "single-bedroom-5-share-apt-bc": ("5 Share Apt", "Share", "?", "King Single", "5人"),
            "single-bedroom-6-share-apt-bc": ("6 Share Apt", "Share", "?", "King Single", "6人"),
            "student-room-shared-bathroom-bc": ("Single Share Bath", "Share", "?", "King Single", "Share Bath"),
            # Kelvin Grove
            "1-bedroom-apartment-kg": ("1 Bedroom Apt", "Apt", "?", "King Single", ""),
            "single-bedroom-2-share-apt-kg": ("2 Share Apt", "Share", "?", "King Single", "2人"),
            "single-bedroom-3-share-apt-kg": ("3 Share Apt", "Share", "?", "King Single", "3人"),
            "single-bedroom-5-share-apt-kg": ("5 Share Apt", "Share", "?", "King Single", "5人"),
            "single-bedroom-6-share-apt-kg": ("6 Share Apt", "Share", "?", "King Single", "6人"),
        },
        "property_rooms": {
            "brisbane-city": [
                "premium-studio-apartment-bc", "standard-studio-apartment-bc",
                "single-bedroom-5-share-apt-bc", "single-bedroom-6-share-apt-bc",
                "student-room-shared-bathroom-bc",
            ],
            "kelvin-grove": [
                "1-bedroom-apartment-kg", "single-bedroom-2-share-apt-kg",
                "single-bedroom-3-share-apt-kg", "single-bedroom-5-share-apt-kg",
                "single-bedroom-6-share-apt-kg",
            ],
        },
    },
}

# 即将开业、暂无真实房型数据的楼（官网未发布可预订房型页）。
# 这些楼只显示在导航里并标注"即将"，不参与抓取，避免误抓旧楼数据。
COMING_SOON = {"mascot-duo"}

# ── Room type display order (sub-tabs inside a property) ──
TYPE_ORDER = ["Studio", "Apt", "Share"]
TYPE_TAB_LABELS = {"Studio": "🏠 Studio", "Apt": "🛏️ 1居室", "Share": "👥 合租"}

# U18 rooms - separated for clarity（悉尼保留，用于未来扩展；不参与常规展示）
U18_ROOMS = {
    "sce-6-bedroom-share-bathroom-u18-female": ("U18 6 Share Bath Female", "Central"),
    "sce-6-bedroom-share-bathroom-u18-male": ("U18 6 Share Bath Male", "Central"),
    "sce-6-bedroom-u18-female": ("U18 6 Share Female", "Central"),
    "sce-6-bedroom-u18-male": ("U18 6 Share Male", "Central"),
    "sce-5-bedroom-u18-female": ("U18 5 Share Female", "Central"),
    "sce-5-bedroom-u18-male": ("U18 5 Share Male", "Central"),
    "sce-standard-studio-u18": ("U18 Standard Studio", "Central"),
    "sce-2-bedroom-studio-u18-female": ("U18 2 Bed Studio Female", "Central"),
    "sce-2-bedroom-studio-u18-male": ("U18 2 Bed Studio Male", "Central"),
    "sre-6-bedroom-u18-female": ("U18 6 Share Female", "Redfern"),
    "sre-6-bedroom-u18-male": ("U18 6 Share Male", "Redfern"),
    "sre-4-bedroom-u18-male": ("U18 4 Share Male", "Redfern"),
    "sre-4-bedroom-u18-female": ("U18 4 Share Female", "Redfern"),
    "u18-standard-studio": ("U18 Standard Studio", "Redfern"),
    "sre-premium-studio-u18": ("U18 Premium Studio", "Redfern"),
}


def login_agent_portal() -> bool:
    """Log into Iglu Agent Portal. Currently disabled - Iglu site uses AJAX login
    which doesn't work with simple POST. Falls back to public scraping."""
    print("  ℹ️  Agent Portal login not available, using public page data")
    return False


def fetch_page(url: str, use_agent: bool = False) -> str:
    """Fetch a page using curl. If use_agent=True, use agent cookies."""
    cmd = [
        "curl", "-sL",
        "--compressed",
        "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: en-AU,en;q=0.9",
        "--connect-timeout", "15",
        "--max-time", str(REQUEST_TIMEOUT),
    ]
    if use_agent and os.path.exists(COOKIE_FILE):
        cmd += ["-b", COOKIE_FILE]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=REQUEST_TIMEOUT + 5)
    if result.returncode != 0:
        raise Exception(f"curl failed: {result.stderr[:200]}")
    # Check for Cloudflare challenge
    if "cf-browser-verify" in result.stdout.lower() or "just a moment" in result.stdout.lower():
        raise Exception("Cloudflare challenge detected")
    if "403 Forbidden" in result.stdout[:200]:
        raise Exception("403 Forbidden")
    # 404 页面（WordPress <title>Page not found</title>）——页面不存在，标记失败而非当有效数据处理
    if re.search(r'<title>\s*page\s+not\s+found', result.stdout, re.IGNORECASE):
        raise Exception("Page not found (404)")
    return result.stdout


def extract_prices(html: str) -> dict:
    """Extract price points from a room page."""
    prices = {}

    # Clean HTML tags for regex matching
    text = re.sub(r'<[^>]+>', ' ', html)

    # "From $XXX/wk" — hero price
    from_m = re.search(r'From\s+\$([\d,]+)\s*/?\s*wk', text, re.IGNORECASE)
    if from_m:
        prices['From'] = int(from_m.group(1).replace(',', ''))

    # "22 Weeks ($865/wk)" or "22 Weeks $865/wk" or "22 Weeks **($865/wk)**"
    w22_m = re.search(r'22\s*Weeks?\s*(?:\(|\(?\*?\*?)?\$([\d,]+)', text, re.IGNORECASE)
    if w22_m:
        prices['22周'] = int(w22_m.group(1).replace(',', ''))

    # "44 Weeks ($XXX/wk)" — only available in Sydney Semester 1
    w44_m = re.search(r'44\s*Weeks?\s*(?:\(|\(?\*?\*?)?\$([\d,]+)', text, re.IGNORECASE)
    if w44_m:
        prices['44周'] = int(w44_m.group(1).replace(',', ''))

    # "Short Stay ($600/wk)"
    ss_m = re.search(r'Short\s+Stay\s*(?:\(|\(?\*?\*?)?\$([\d,]+)', text, re.IGNORECASE)
    if ss_m:
        prices['短租'] = int(ss_m.group(1).replace(',', ''))

    # "12 Months ($XXX/wk)" or "12 Months **($XXX/wk)**"
    m12_m = re.search(r'12\s*Months?\s*(?:\(|\(?\*?\*?)?\$([\d,]+)', text, re.IGNORECASE)
    if m12_m:
        prices['12月'] = int(m12_m.group(1).replace(',', ''))

    # "24 Months ($XXX/wk)"
    m24_m = re.search(r'24\s*Months?\s*(?:\(|\(?\*?\*?)?\$([\d,]+)', text, re.IGNORECASE)
    if m24_m:
        prices['24月'] = int(m24_m.group(1).replace(',', ''))

    # If we only have "From", use it as default for 短租
    if 'From' in prices and not prices:
        pass  # Keep 'From' as the only indicator

    return prices


def extract_availability(html: str, date_data: dict = None) -> tuple:
    """Extract availability status and count.
    Uses visible indicators + context from dates to avoid false waitlist."""
    # "X LEFT AT THIS PRICE" — visible, most reliable
    m = re.search(r'(\d+)\s*LEFT\s*AT\s*THIS\s*PRICE', html, re.IGNORECASE)
    if m:
        count = int(m.group(1))
        return ('available' if count >= 3 else 'limited', count, m.group(0))

    # Sold out — explicit
    if re.search(r'sold\s*out', html, re.IGNORECASE):
        return ('soldout', None, '')

    # Wait list? Only if NO dates and NO flexible start (i.e. waitlist is the ONLY option)
    has_waitlist = bool(re.search(r'wait\s*list', html, re.IGNORECASE))
    if has_waitlist:
        if date_data:
            has_dates = len(date_data.get('dates', [])) > 0
            has_flexible = date_data.get('flexible', False)
            if not has_dates and not has_flexible:
                return ('waitlist', None, '')
        else:
            # Without date context, check if page has dates/flexible elsewhere
            has_any_dates = bool(re.search(
                r'(?:Flexible\s+Start|(\d{1,2})\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4}))',
                html, re.IGNORECASE
            ))
            if not has_any_dates:
                return ('waitlist', None, '')

    # 无库存数字/sold out/waitlist 标记时：若解析到可订日期或灵活起租（长租/短租/flexible）→ 视为有房；
    # 完全无任何信息 → unknown（可能是 404/异常页面，避免假"有房"）
    if date_data and (date_data.get('dates') or date_data.get('shortstay_dates') or date_data.get('flexible')):
        return ('available', None, '')
    return ('unknown', None, '')


def extract_dates(html: str) -> dict:
    """Extract available start dates and Flexible Start indicator.
    Returns {'dates': [...], 'flexible': bool}"""
    from html.parser import HTMLParser

    dates = []
    month_map = {m: i for i, m in enumerate([
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ], 1)}

    # Check for Flexible Start option：
    # 真正的灵活起租 = id="availNowBtn" 按钮。官网 JS（iglu.js）中该按钮的
    # data-22w / data-44w / data-6m 是「合同结束日」（显示为 "Contract ends <date>"），
    # 不是起租日；灵活起租的最早可入住日 = 日历起点 available-picker-start-date。
    # 仅页面说明文本有 "Flexible Start" 但无按钮（如 Broadway 6B prebook）不算灵活起租。
    def _parse_ddmmyy(s):
        m = re.match(r'\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$', s)
        if m:
            day, mon, yy = int(m.group(1)), int(m.group(2)), m.group(3)
            year = 2000 + int(yy) if len(yy) == 2 else int(yy)
            if 1 <= mon <= 12 and 1 <= day <= 31:
                return (year, mon, day)
        return None

    # 禁用日期（buffer days）：官网 available-buffer-days 字段，格式 "YYYY-MM-DD,YYYY-MM-DD"。
    # 日历 minDate（picker-start-date）只是最早可浏览日，具体日期还受此禁用列表约束：
    # 实测 Redfern 6B buffer=2026-08-26 → 最早可入住 8/27；Brisbane City 6B buffer=26,27 → 8/28；
    # Summer Hill buffer=26,27,28 → 8/29；Central Park buffer 空 → 8/26。
    buffer_dates = set()
    bm = re.search(
        r'available-buffer-days[^>]*?value\s*=\s*["\']([^"\']*)["\']'
        r'|value\s*=\s*["\']([^"\']*)["\'][^>]*?available-buffer-days',
        html
    )
    if bm:
        buf_val = bm.group(1) if bm.group(1) is not None else bm.group(2)
        if buf_val:
            for part in buf_val.split(','):
                part = part.strip()
                if re.match(r'^\d{4}-\d{2}-\d{2}$', part):
                    buffer_dates.add(part)

    # 周末规则（iglu.js available_now_datepicker beforeShowDay）：#allow-weekends 的值
    # 非空且 != '1' 时周末不可选（jQuery.datepicker.noWeekends）。实测各楼目前均为 '1'，
    # 但字段存在，一旦 Iglu 改值而这里不处理，起租日会虚报到周末。
    awm = re.search(
        r'id=["\']allow-weekends["\'][^>]*?value\s*=\s*["\']([^"\']*)["\']'
        r'|value\s*=\s*["\']([^"\']*)["\'][^>]*?id=["\']allow-weekends["\']',
        html
    )
    allow_weekends = '1'
    if awm:
        allow_weekends = (awm.group(1) if awm.group(1) is not None else awm.group(2)) or '1'
    weekends_blocked = allow_weekends != '1'

    def _earliest_available(start, max_lookahead=180):
        """从 start 起逐日找第一个可选日期：跳过 buffer 禁用日；周末受 allow-weekends 控制。
        对齐 iglu.js beforeShowDay 规则（buffer 优先于周末判断，两者都需跳过）。"""
        if not start:
            return None
        from datetime import date as _date, timedelta as _td
        d = _date(start[0], start[1], start[2])
        for _ in range(max_lookahead):
            if d.strftime('%Y-%m-%d') in buffer_dates:
                d += _td(days=1)
                continue
            if weekends_blocked and d.weekday() >= 5:
                d += _td(days=1)
                continue
            return (d.year, d.month, d.day)
        return start

    flexible = False
    contract_end = None
    flexible_start = None
    flexible_end = None
    btn_tag_m = re.search(r'<button[^>]*id=["\']availNowBtn["\'][^>]*>', html)
    if btn_tag_m:
        # 按钮租期类（ltermSS/lterm22/...）决定它在哪些租期下可见（iglu.js showHideStartDates：
        # 选中租期 X 时，无 ltermX 类的按钮所在 li 被隐藏）。按钮只带 ltermSS ⟺ 该 Flexible Start
        # 仅短租可选（如 Broadway 4B/5B、Chatswood 全部 Studio、South Yarra 等），
        # 长租灵活起租不存在——实测差分核对 2026-08-25，此前一律置 flexible=True 属误报。
        _cls_m = re.search(r'class="([^"]*)"', btn_tag_m.group(0))
        _btn_lterms = set(re.findall(r'lterm(\w+)', _cls_m.group(1))) if _cls_m else set()
        if _btn_lterms & {'6', '12', '24', '22', '44'}:
            flexible = True
        # 合同结束日 = data-22w / data-44w / data-6m（取最早且未过期的）
        from datetime import datetime as _dt_now
        _today_c = (_dt_now.now().year, _dt_now.now().month, _dt_now.now().day)
        seg = html[max(0, btn_tag_m.start() - 300):btn_tag_m.end() + 300]
        end_candidates = []
        for key in ('data-6m', 'data-22w', 'data-44w'):
            dm = re.search(re.escape(key) + r'=["\']([\d/]{4,10})["\']', seg)
            if dm:
                parsed = _parse_ddmmyy(dm.group(1))
                if parsed and parsed >= _today_c:
                    end_candidates.append(parsed)
        if end_candidates:
            contract_end = min(end_candidates)
        if flexible:
            # 灵活起租最早可入住日 = 日历起点（available-picker-start-date，格式 2026,8,26）；
            # 字段为空时官网 JS 用 "+1D"（明天）作 minDate
            fs_m = re.search(
                r'available-picker-start-date[^>]*?value\s*=\s*["\'](\d{4}),(\d{1,2}),(\d{1,2})["\']',
                html
            )
            if fs_m:
                flexible_start = (int(fs_m.group(1)), int(fs_m.group(2)), int(fs_m.group(3)))
                flexible_start = _earliest_available(flexible_start)
            else:
                from datetime import date as _d0, timedelta as _t0
                _tm = _d0.today() + _t0(days=1)
                flexible_start = _earliest_available((_tm.year, _tm.month, _tm.day))
            # 灵活起租最晚可入住日 = 日历终点（available-picker-date，格式 2026,9,30）
            fe_m = re.search(
                r'id=["\']available-picker-date["\'][^>]*?value\s*=\s*["\'](\d{4}),(\d{1,2}),(\d{1,2})["\']',
                html
            )
            if fe_m:
                flexible_end = (int(fe_m.group(1)), int(fe_m.group(2)), int(fe_m.group(3)))
    else:
        # 兜底：无按钮时仍检测文本（不精确，仅作标记）
        flexible = bool(re.search(r'Flexible\s+Start', html, re.IGNORECASE))

    # Strategy 1: Find dates inside clickable tags
    clickable_pattern = re.finditer(
        r'<(?:a|button|option|label)[^>]*?>\s*(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s*</(?:a|button|option|label)>',
        html, re.IGNORECASE
    )
    for m in clickable_pattern:
        day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = month_map.get(month_name)
        if month:
            dates.append((year, month, day))

    # Strategy 2: Dates in booking section (fallback)
    if not dates:
        booking_section = re.search(
            r'(?:start-date|move-in|contract-start|date-select|when would you like)',
            html, re.IGNORECASE
        )
        if booking_section:
            section_start = max(0, booking_section.start() - 500)
            section_end = min(len(html), booking_section.end() + 3000)
            section_html = html[section_start:section_end]
            section_no_examples = re.sub(r'e\.g\..*?(?=<)', '', section_html, flags=re.IGNORECASE)
            date_matches = re.finditer(
                r'(?:>|\s)(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
                section_no_examples
            )
            for m in date_matches:
                day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
                month = month_map.get(month_name)
                if month:
                    dates.append((year, month, day))

    # Deduplicate and sort (按完整年月日去重，保留同月内的多个日期)
    seen = set()
    unique = []
    for d in dates:
        key = f"{d[2]:04d}-{d[1]:02d}-{d[0]:02d}"
        if key not in seen:
            seen.add(key)
            unique.append(d)
    unique.sort()

    # Short Stay 短租：判据 = move-in-dates 区域存在带 ltermSS 类的按钮。
    # 官网 iglu.js triggerLterms()：某租期选项显示 ⟺ #move-in-dates li .btn-rev 中
    # 存在 class 含 lterm<term>（ltermSS/lterm22/lterm44/lterm12/lterm6）的按钮。
    # 旧判据「页面存在 id=mnthSS radio」不成立：Mascot 6B 的 mnthSS input/label 一直在
    # HTML 里（label 带 display:none），但按钮无 ltermSS → JS 不放开 → 实际无短租，
    # 曾误报「短租 8/28 起」（浏览器实测 2026-08-25：仅 12M/22W/44W + 固定 9/7 起）。
    # 短租最早可入住日 = 日历起点（available-shortstay-picker-start-date），缺失时回退 picker-date。
    shortstay_dates = []
    md_ul = re.search(r'<ul[^>]*id=["\']move-in-dates["\'][^>]*>(.*?)</ul>', html, re.S)
    if md_ul:
        has_ss_option = re.search(r'class="[^"]*\bltermSS\b', md_ul.group(1)) is not None
    else:
        # 无 move-in-dates 区块的页面退回旧判据
        has_ss_option = re.search(r'id=["\']mnthSS["\']', html) is not None
    if has_ss_option:
        ss_start_m = re.search(
            r"available-shortstay-picker-start-date[^>]*?value\s*=\s*['\"](\d{4}),(\d{1,2}),(\d{1,2})",
            html
        )
        if ss_start_m:
            # 短租：最早可订 = 日历起点（ss picker-start-date），跳过 buffer 禁用日/周末
            _ss = (int(ss_start_m.group(1)), int(ss_start_m.group(2)), int(ss_start_m.group(3)))
            shortstay_dates.append(_earliest_available(_ss))
        else:
            # 起点缺失时官网 JS 同样用 "+1D"（明天）作 minDate
            from datetime import date as _d1, timedelta as _t1
            _tm = _d1.today() + _t1(days=1)
            shortstay_dates.append(_earliest_available((_tm.year, _tm.month, _tm.day)))

    # 过滤已过期日期（页面可能残留过去年份的旧数据，如墨尔本某楼短租 2025,2,17）
    from datetime import datetime as _dt
    _today = (_dt.now().year, _dt.now().month, _dt.now().day)
    unique = [d for d in unique if d >= _today]
    shortstay_dates = [d for d in shortstay_dates if d >= _today]
    if contract_end and contract_end < _today:
        contract_end = None
    if flexible_start and flexible_start < _today:
        flexible_start = None
    # 灵活起租窗口已关闭（maxDate 过期或早于 minDate，日历零可选日）→ 整体不算长租灵活。
    # 实测 Redfern SAEX 6B：picker-start=2026,8,26 而 picker-date=2026,7,27（已过期），
    # 官网日历无可选日期，此前仍显示「长租灵活 8/27 起」属误报（差分核对 2026-08-25）。
    if flexible_end and (flexible_end < _today or (flexible_start and flexible_end < flexible_start)):
        flexible = False
        flexible_start = None
        flexible_end = None
    if flexible_end and flexible_end < _today:
        flexible_end = None

    return {
        'dates': unique,
        'flexible': flexible,
        'flexible_start': flexible_start,
        'flexible_end': flexible_end,
        'contract_end': contract_end,
        'shortstay_dates': shortstay_dates,
    }


def extract_features(html: str) -> dict:
    """Extract room features from the page HTML."""
    features = {}

    # Clean HTML tags for text matching
    text = re.sub(r'<[^>]+>', ' ', html)

    # Area: look for patterns like "Approx. 17m²", "19.5m²", "Approx. 13.4m²"
    area_m = re.search(r'(?:Approx\.?\s*)?(\d+\.?\d*)\s*m²', text, re.IGNORECASE)
    if area_m:
        area_val = float(area_m.group(1))
        if area_val == int(area_val):
            features['area'] = f"{int(area_val)}m²"
        else:
            features['area'] = f"{area_val}m²"

    # Bed type - check in order of specificity
    if re.search(r'king\s*single', text, re.IGNORECASE):
        features['bed'] = 'King Single'
    elif re.search(r'queen\s*bed', text, re.IGNORECASE):
        features['bed'] = 'Queen'
    elif re.search(r'double\s*bed', text, re.IGNORECASE):
        features['bed'] = 'Double'
    elif re.search(r'king\s*bed', text, re.IGNORECASE):
        features['bed'] = 'King'

    return features


def format_price(prices: dict, key: str) -> str:
    """Format a price value for display."""
    val = prices.get(key)
    if val is None:
        return "—"
    return f"${val:,}"


# 手动精准起租日期覆盖表：配置后该房型优先显示此处日期（用于官网未展示具体日期、
# 但 Agent Portal 可见的情况）。键 = 页面房型显示名（如 "Premium Studio"）；
# 同名房型（不同楼栋）会同时生效，如需只改某一栋请把键写成 "楼栋slug/房型slug"。
DATE_OVERRIDES = {
    # "Premium Studio": "2026年8月25日",
}


def format_dates(date_data: dict) -> str:
    """Format dates for display. Keeps year for precision. Includes Flexible Start indicator."""
    dates = date_data.get('dates', []) if isinstance(date_data, dict) else date_data
    flexible = date_data.get('flexible', False) if isinstance(date_data, dict) else False

    if not dates:
        return "灵活自选"

    from collections import defaultdict
    by_ym = defaultdict(list)
    for y, m, d in dates:
        by_ym[(y, m)].append(d)

    parts = []
    for (y, m), days in sorted(by_ym.items()):
        days.sort()
        ranges = []
        start = end = days[0]
        for d in days[1:]:
            if d == end + 1:
                end = d
            else:
                ranges.append((start, end))
                start = end = d
        ranges.append((start, end))

        day_strs = []
        for s, e in ranges:
            if s == e:
                day_strs.append(f"{s}日")
            else:
                day_strs.append(f"{s}-{e}日")

        if len(day_strs) == 1:
            parts.append(f"{y}年{m}月" + day_strs[0])
        else:
            parts.append(f"{y}年{m}月" + "、".join(day_strs))

    date_str = "、".join(parts)

    if flexible and dates:
        return f"灵活自选 + {date_str}"
    return date_str


def format_start_label(avail_status: str, date_data: dict) -> str:
    """精准起租日期：区分今年可起租 / 今年已无房只有明年 / 等位无房。
    Flexible Start（灵活起租）：最早可入住日 = 日历起点 flexible_start；
    data-22w/data-44w 是合同结束日（Contract ends），单独标注，不作为起租日。"""
    from collections import defaultdict
    from datetime import datetime
    if not isinstance(date_data, dict):
        date_data = {}
    dates = date_data.get('dates', [])
    flexible = date_data.get('flexible', False)
    ss_dates = date_data.get('shortstay_dates', [])
    flexible_start = date_data.get('flexible_start')
    flexible_end = date_data.get('flexible_end')
    contract_end = date_data.get('contract_end')

    this_year = datetime.now().year
    this_dates = sorted(d for d in dates if d[0] == this_year)
    future_dates = sorted(d for d in dates if d[0] > this_year)
    ss_this = sorted(d for d in ss_dates if d[0] == this_year)
    fs_this = bool(flexible_start and flexible_start[0] == this_year)

    def short(ds):
        by_m = defaultdict(list)
        for y, m, d in ds:
            by_m[m].append(d)
        parts = []
        for m in sorted(by_m):
            days = sorted(by_m[m])
            segs = []
            start = end = days[0]
            for d in days[1:]:
                if d == end + 1:
                    end = d
                else:
                    segs.append((start, end))
                    start = end = d
            segs.append((start, end))
            seg_txt = []
            for s, e in segs:
                seg_txt.append(f"{s}日" if s == e else f"{s}-{e}日")
            parts.append(f"{m}月" + "、".join(seg_txt))
        return "、".join(parts)

    def full(ds):
        return format_dates({'dates': ds, 'flexible': False})

    def flex_text():
        """灵活起租日期区间：'2026年8月26日~9月30日'（跨年带年份）"""
        if not flexible_start:
            return None
        s = f"{flexible_start[0]}年{flexible_start[1]}月{flexible_start[2]}日"
        if (flexible_end and flexible_end > flexible_start
                and flexible_end[1] != flexible_start[1]):
            if flexible_end[0] == flexible_start[0]:
                s += f"~{flexible_end[1]}月{flexible_end[2]}日"
            else:
                s += f"~{flexible_end[0]}年{flexible_end[1]}月{flexible_end[2]}日"
        return s

    def flex_full():
        """灵活起租完整文案（含合同结束日）：'2026年8月26日~9月30日 起（合同至 2026年12月1日）'"""
        ft = flex_text()
        if not ft:
            return None
        if contract_end:
            return f"{ft} 起（合同至 {contract_end[0]}年{contract_end[1]}月{contract_end[2]}日）"
        return f"{ft} 起"

    # 今年可订判定：长租固定今年日期 或 短租今年可订 或 灵活起租今年可入住
    if this_dates or ss_this or fs_this:
        parts = []
        if ss_this:
            parts.append('短租 ' + short(ss_this) + ' 起')
        if this_dates:
            parts.append('固定起租 ' + short(this_dates) + ' 起')
        if flexible and flexible_start:
            parts.append('长租灵活 ' + flex_full())
        if future_dates:
            if this_dates or (flexible and flexible_start):
                parts.append('长租亦可 ' + full(future_dates))
            else:
                parts.append('长租 ' + full(future_dates))
        return '今年可订：' + '；'.join(parts)
    if future_dates:
        return '今年已无房：' + full(future_dates)
    if flexible:
        if flexible_start:
            return '今年已无房：长租灵活 ' + flex_full()
        return '灵活自选'
    if ss_dates:
        return '今年可订：短租 ' + full(ss_dates) + ' 起'
    if avail_status == 'waitlist':
        return '今年无房（等位）'
    return '待定'


def scrape_room(city: str, property_slug: str, room_slug: str, room_meta: dict) -> dict:
    """Scrape a single room page and return structured data."""
    url = f"https://iglu.com.au/rooms/{city}/{property_slug}/{room_slug}/"
    try:
        # Try agent view first for better availability data
        html = fetch_page(url, use_agent=True)
    except Exception as e:
        try:
            html = fetch_page(url, use_agent=False)
        except Exception as e2:
            return {"error": str(e2), "url": url, "slug": room_slug}

    prices = extract_prices(html)
    date_data = extract_dates(html)
    avail_status, avail_count, avail_text = extract_availability(html, date_data)
    features = extract_features(html)

    # Use ROOM_META as fallback for name/type/note, but prefer scraped area/bed
    meta = room_meta.get(room_slug, (room_slug.replace('-', ' ').title(), "Unknown", "?", "?", ""))
    area = features.get('area') or meta[2]
    bed = features.get('bed') or meta[3]

    return {
        "slug": room_slug,
        "url": url,
        "name": meta[0],
        "type": meta[1],
        "area": area,
        "bed": bed,
        "note": meta[4] if len(meta) > 4 else "",
        "prices": prices,
        "avail_status": avail_status,
        "avail_count": avail_count,
        "avail_text": avail_text,
        "date_data": date_data,
        "date_str": DATE_OVERRIDES.get(meta[0], format_start_label(avail_status, date_data)),
    }


def scrape_property(city: str, name: str, slug: str, room_meta: dict, property_rooms: dict) -> dict:
    """Scrape all rooms for a property."""
    print(f"  📍 {city} · {name} ({slug})")

    room_slugs = property_rooms.get(slug, [])

    print(f"     {len(room_slugs)} room types to scrape")

    rooms = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scrape_room, city, slug, rs, room_meta): rs for rs in room_slugs}
        for future in as_completed(futures):
            result = future.result()
            if "error" not in result:
                rooms.append(result)
                print(f"     ✅ {result['name']}: {result.get('prices', {}).get('From', 'N/A')}")
            else:
                print(f"     ❌ {futures[future]}: {result['error']}")

    # Sort: Studio/Apt first, then Share (按 TYPE_ORDER 排序，同类按名称)
    type_rank = {t: i for i, t in enumerate(TYPE_ORDER)}
    rooms.sort(key=lambda r: (type_rank.get(r['type'], 99), r['name']))
    return {"name": name, "slug": slug, "rooms": rooms}


def avail_info(status: str, count) -> tuple:
    """Return (row_class, status_html) for availability display."""
    if status == 'available':
        label = f"{count}间" if count else "有房"
        return ('row-ok', f'<span class="tag tag-ok">{label}</span>')
    elif status == 'limited':
        label = f"仅剩{count}间" if count else "紧张"
        return ('row-warn', f'<span class="tag tag-warn">{label}</span>')
    elif status == 'waitlist':
        return ('row-bad', '<span class="tag tag-bad">等位</span>')
    elif status == 'soldout':
        return ('row-off', '<span class="tag tag-off">售罄</span>')
    elif status == 'unknown':
        return ('row-off', '<span class="tag tag-off">未知</span>')
    else:
        return ('row-off', '<span class="tag tag-off">未知</span>')


def build_date_cell(room: dict) -> str:
    """起租日期单元格：醒目徽标（今年可订 / 今年已无房 / 等位无房 / 灵活自选）+ 日期细节。
    今年可订 = 有今年日期（长租/短租/灵活起租最早可入住）。"""
    from datetime import datetime
    date_data = room.get('date_data', {})
    avail = room['avail_status']
    dates = date_data.get('dates', []) if isinstance(date_data, dict) else []
    flexible = date_data.get('flexible', False) if isinstance(date_data, dict) else False
    ss_dates = date_data.get('shortstay_dates', []) if isinstance(date_data, dict) else []
    flexible_start = date_data.get('flexible_start') if isinstance(date_data, dict) else None
    flexible_end = date_data.get('flexible_end') if isinstance(date_data, dict) else None
    contract_end = date_data.get('contract_end') if isinstance(date_data, dict) else None
    this_year = datetime.now().year

    if avail == 'soldout':
        return '<span class="tag tag-off tag-mini">已售罄</span>'
    if avail == 'waitlist':
        return '<span class="tag tag-bad tag-mini">等位无房</span>'
    if avail == 'unknown':
        return '<span class="tag tag-off tag-mini">未知</span>'
    def _fmt(ds):
        return format_dates({'dates': ds, 'flexible': False})

    this_dates = [d for d in dates if d[0] == this_year]
    future_dates = [d for d in dates if d[0] > this_year]
    ss_this = [d for d in ss_dates if d[0] == this_year]
    fs_this = bool(flexible_start and flexible_start[0] == this_year)

    def _flex_text():
        """灵活起租日期区间：'2026年8月26日~9月30日'（跨年带年份）"""
        if not flexible_start:
            return None
        s = f"{flexible_start[0]}年{flexible_start[1]}月{flexible_start[2]}日"
        if (flexible_end and flexible_end > flexible_start
                and flexible_end[1] != flexible_start[1]):
            if flexible_end[0] == flexible_start[0]:
                s += f"~{flexible_end[1]}月{flexible_end[2]}日"
            else:
                s += f"~{flexible_end[0]}年{flexible_end[1]}月{flexible_end[2]}日"
        return s

    def _flex_full():
        """灵活起租完整文案（含合同结束日）：'2026年8月26日~9月30日 起（合同至 2026年12月1日）'"""
        ft = _flex_text()
        if not ft:
            return None
        if contract_end:
            return f"{ft} 起（合同至 {contract_end[0]}年{contract_end[1]}月{contract_end[2]}日）"
        return f"{ft} 起"

    # 今年可订（长租今年日期 或 短租今年可订 或 灵活起租今年可入住）
    if this_dates or ss_this or fs_this:
        parts = []
        if ss_this:
            parts.append(f'短租 {_fmt(ss_this)} 起')
        if this_dates:
            parts.append(f'固定起租 {_fmt(this_dates)} 起')
        if flexible and flexible_start:
            parts.append(f'长租灵活 {_flex_full()}')
        if future_dates:
            if this_dates or (flexible and flexible_start):
                parts.append(f'长租亦可 {_fmt(future_dates)}')
            else:
                parts.append(f'长租 {_fmt(future_dates)}')
        return f'<span class="tag tag-ok tag-mini">今年可订</span> <span class="date-detail">{"；".join(parts)}</span>'
    if future_dates:
        return f'<span class="tag tag-off tag-mini">今年无房</span> <span class="date-detail">{_fmt(future_dates)} 起</span>'
    if flexible:
        if flexible_start:
            return f'<span class="tag tag-off tag-mini">今年无房</span> <span class="date-detail">长租灵活 {_flex_full()}</span>'
        return '<span class="tag tag-ok tag-mini">今年可订</span> <span class="date-detail">灵活自选</span>'
    if ss_dates:
        return f'<span class="tag tag-ok tag-mini">今年可订</span> <span class="date-detail">短租 {_fmt(ss_dates)} 起</span>'
    return '<span class="tag tag-off tag-mini">待定</span>'


def build_room_row(room: dict) -> str:
    """Build a single table row (统一渲染 Studio / Share，不再分表)。"""
    p = room['prices']
    row_cls, status_html = avail_info(room["avail_status"], room["avail_count"])
    note = room.get("note", "")
    note_html = f'<span class="room-note">{note}</span>' if note else ''
    return (
        f'<tr class="{row_cls}">'
        f'<td><span class="room-name">{room["name"]}</span>{note_html}</td>'
        f'<td>{room["area"]}</td>'
        f'<td>{room["bed"]}</td>'
        f'<td><span class="price">{format_price(p, "12月")}</span></td>'
        f'<td><span class="price">{format_price(p, "44周")}</span></td>'
        f'<td><span class="price">{format_price(p, "22周")}</span></td>'
        f'<td><span class="price">{format_price(p, "短租")}</span></td>'
        f'<td>{status_html}</td>'
        f'<td>{build_date_cell(room)}</td>'
        f'</tr>'
    )


def room_sort_key(room: dict):
    """按「有房先后」排序：可订优先 → 起租日期早优先 → 名称。
    有房顺序 = available > limited > waitlist > soldout；
    日期顺序 = 今年可订(含灵活) > 有明年日期 > 无日期。"""
    from datetime import datetime
    avail_rank = {'available': 0, 'limited': 1, 'waitlist': 2, 'soldout': 3}.get(room['avail_status'], 4)
    date_data = room.get('date_data', {}) or {}
    dates = date_data.get('dates', []) if isinstance(date_data, dict) else []
    flexible = date_data.get('flexible', False) if isinstance(date_data, dict) else False
    ss_dates = date_data.get('shortstay_dates', []) if isinstance(date_data, dict) else []
    this_year = datetime.now().year
    ss_this = any(d[0] == this_year for d in ss_dates)
    if flexible or any(d[0] == this_year for d in dates) or ss_this:
        date_rank = 0
    elif dates or ss_dates:
        date_rank = 1
    else:
        date_rank = 2
    return (avail_rank, date_rank, room['name'])


def build_prop_panel(prop: dict, is_first: bool) -> str:
    """Build a single property panel：所有房型一次性展示（不分类），按有房先后排序。"""
    rooms = sorted(prop['rooms'], key=room_sort_key)
    thead = '<th>房型</th><th>面积</th><th>床型</th><th>12/24月</th><th>44周</th><th>22周</th><th>短租</th><th>库存</th><th>起租日期</th>'

    coming_soon_html = ""
    if not rooms:
        if prop["slug"] in COMING_SOON:
            coming_soon_html = (
                '<div class="coming-soon">'
                '<div class="cs-badge">🚧 即将开业</div>'
                '<p class="cs-title">Iglu Mascot Duo</p>'
                '<p class="cs-text">预计 <b>2027 年 1 月</b> 开业，官网目前为招租登记阶段，'
                '尚未公布可预订房型与价格。<br>房型上线后本页将自动同步真实房态。</p>'
                '</div>'
            )
        else:
            coming_soon_html = '<div class="coming-soon"><p class="cs-text">暂无房型数据</p></div>'

    return f'''<div class="prop-panel{" active" if is_first else ""}" id="prop-{prop['slug']}">
<div class="table-wrap"><table>
<thead><tr>{thead}</tr></thead>
<tbody>{"".join(build_room_row(r) for r in rooms)}</tbody>
</table></div>{coming_soon_html}
</div>'''


def build_city_block(city_slug: str, city_data: dict) -> str:
    """Build one city block: its property nav + all property panels."""
    props = city_data['properties']

    nav_buttons = []
    room_results = city_data.get("room_results", {})
    for i, (name, slug) in enumerate(props.items()):
        active = ' active' if i == 0 else ''
        badge = "即将" if slug in COMING_SOON else str(len(room_results.get(slug, [])))
        nav_buttons.append(
            f'<button class="prop-btn{active}" id="prop-btn-{slug}" '
            f'onclick="switchProp(\'{city_slug}\',\'{slug}\')">{name}<span class="count">{badge}</span></button>'
        )

    panels = []
    for i, (name, slug) in enumerate(props.items()):
        prop_data = {"name": name, "slug": slug, "rooms": city_data.get("room_results", {}).get(slug, [])}
        panels.append(build_prop_panel(prop_data, is_first=(i == 0)))

    return f'''<div class="city-block" data-city="{city_slug}">
<nav class="prop-nav fade-in" style="animation-delay:80ms" id="prop-nav-{city_slug}">{"".join(nav_buttons)}</nav>
{"".join(panels)}
</div>'''


def build_html(all_cities: dict) -> str:
    """Build the complete HTML page from template and data."""
    with open(TEMPLATE_PATH, 'r') as f:
        template = f.read()

    # Beijing time (UTC+8)
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    update_time = now.strftime("%Y年%m月%d日 %H:%M")
    update_badge = now.strftime("%m/%d %H:%M 更新")

    # City summary: 悉尼 9 所 · 墨尔本 5 所 · 布里斯班 2 所
    summary_parts = []
    for city_slug, city_data in all_cities.items():
        n = len(city_data['properties'])
        summary_parts.append(f"{city_data['label']} {n} 所")
    city_summary = "📍 " + " · ".join(summary_parts) + " Iglu 公寓"

    # City blocks (each with its own nav + panels)
    city_blocks = [build_city_block(city_slug, city_data) for city_slug, city_data in all_cities.items()]

    # Replace placeholders
    html = template
    html = html.replace("{{UPDATE_TIME}}", update_time)
    html = html.replace("{{UPDATE_BADGE}}", update_badge)
    html = html.replace("{{CITY_SUMMARY}}", city_summary)
    html = html.replace("{{CITY_BLOCKS}}", "\n".join(city_blocks))

    return html


# ── 变化检测 & 企微推送 ──

def build_snapshot(all_cities: dict) -> dict:
    """把抓取结果压成可对比的快照: key=city/prop/room_slug → {prices, avail, count, date}"""
    snap = {}
    for city, city_data in all_cities.items():
        for prop_slug, rooms in city_data["room_results"].items():
            for r in rooms:
                key = f"{city}/{prop_slug}/{r.get('slug','')}"
                snap[key] = {
                    "prices": r.get("prices", {}),
                    "avail": r.get("avail_status", ""),
                    "count": r.get("avail_count", ""),
                    "date": r.get("date_str", ""),
                }
    return snap


def load_snapshot() -> dict:
    """读上次快照：优先本地（仓库 checkout 自带），线上兜底"""
    # 1) 本地
    if os.path.exists(SNAPSHOT_PATH):
        try:
            with open(SNAPSHOT_PATH, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            pass
    # 2) 线上
    try:
        req = urllib.request.Request(SNAPSHOT_URL, headers={"User-Agent": "iglu-fangtai-bot"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data:
                return data
    except Exception:
        pass
    return {}


def save_snapshot(snap: dict):
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)


def diff_snapshot(old: dict, new: dict):
    """对比两次快照，返回变化列表 [(key, field, old_val, new_val), ...]"""
    changes = []
    for key, cur in new.items():
        prev = old.get(key)
        if prev is None:
            continue  # 首次抓取/新增房型不打扰
        for field in ("prices", "avail", "count", "date"):
            if prev.get(field) != cur.get(field):
                changes.append((key, field, prev.get(field), cur.get(field)))
    return changes


def format_changes(changes: list, all_cities: dict) -> str:
    """变化列表 → 企微 markdown 消息"""
    # city/prop → 显示名
    prop_label = {}
    for city, city_data in all_cities.items():
        for name, slug in city_data["properties"].items():
            prop_label[f"{city}/{slug}"] = name
    # room slug → 房型显示名
    room_label = {}
    for city, city_data in all_cities.items():
        for prop_slug, rooms in city_data["room_results"].items():
            for r in rooms:
                room_label[f"{city}/{prop_slug}/{r.get('slug','')}"] = r.get("name", r.get("slug",""))

    groups = {}
    for key, field, oldv, newv in changes:
        groups.setdefault(key, []).append((field, oldv, newv))

    lines = []
    for key, items in groups.items():
        city, prop_slug, room_slug = key.split("/", 2)
        name = room_label.get(key, room_slug)
        pname = prop_label.get(f"{city}/{prop_slug}", prop_slug)
        lines.append(f"**{pname} · {name}**")
        for field, oldv, newv in items:
            if field == "prices":
                # 价格 dict 变短显示
                def fmt_price(p):
                    if not p or not isinstance(p, dict):
                        return "—"
                    vals = [str(v) for v in p.values() if v]
                    return "$" + "/".join(vals) if vals else "—"
                lines.append(f"> 价格: {fmt_price(oldv)} → {fmt_price(newv)}")
            elif field == "avail":
                lines.append(f"> 库存: {oldv or '?'} → {newv or '?'}")
            elif field == "count":
                lines.append(f"> 余量: {oldv or '-'} → {newv or '-'}")
            elif field == "date":
                lines.append(f"> 起租: {oldv or '—'} → {newv or '—'}")
        lines.append("")

    # 控制消息长度（企微 markdown 上限约 4096 字符）
    text = "\n".join(lines).strip()
    if len(text) > 3500:
        text = text[:3500] + "\n... (更多变化请查看页面)"
    return text


def notify_wecom(text: str):
    """推送到企业微信群机器人 webhook"""
    if not WECOM_WEBHOOK:
        print("  ℹ️  未配置 WECOM_WEBHOOK，跳过推送（更新照常）")
        return
    payload = {"msgtype": "markdown", "markdown": {"content": text}}
    try:
        req = urllib.request.Request(
            WECOM_WEBHOOK,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            print(f"  📨 企微推送: {body[:120]}")
    except Exception as e:
        print(f"  ❌ 企微推送失败: {e}")


def deploy():
    """Deploy to Cloudflare Pages."""
    print("\n🚀 Deploying to Cloudflare Pages...")
    result = subprocess.run(
        ["npx", "wrangler", "pages", "deploy", ".", "--project-name", CLOUDFLARE_PROJECT, "--commit-dirty=true"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode == 0:
        # Extract deployment URL
        for line in result.stdout.split('\n'):
            if 'pages.dev' in line:
                print(f"   ✅ Deployed: {line.strip()}")
        print(f"   🔗 https://{CLOUDFLARE_PROJECT}.pages.dev/")
    else:
        print(f"   ❌ Deploy failed: {result.stderr[:300]}")


def main():
    no_deploy = "--no-deploy" in sys.argv
    print("=" * 50)
    print(f"🔄 Iglu 澳洲房态更新 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # Try Agent Portal login for more accurate inventory
    agent_ok = login_agent_portal()
    if not agent_ok:
        print("  ℹ️  Will use public page data only")

    all_cities = {}
    total_props = 0
    total_rooms = 0

    for city_slug, city_cfg in CITIES.items():
        print(f"\n🏙️  {city_slug.upper()} ({city_cfg['label']})")
        room_results = {}
        for prop_name, prop_slug in city_cfg["properties"].items():
            prop_data = scrape_property(city_slug, prop_name, prop_slug,
                                        city_cfg["room_meta"], city_cfg["property_rooms"])
            room_results[prop_slug] = prop_data["rooms"]
            total_props += 1
            total_rooms += len(prop_data["rooms"])
        all_cities[city_slug] = {
            "label": city_cfg["label"],
            "properties": city_cfg["properties"],
            "room_results": room_results,
        }

    print(f"\n📊 Total: {total_props} properties, {total_rooms} room types")

    # Build HTML
    print("\n📝 Generating HTML...")
    html = build_html(all_cities)

    with open(OUTPUT_PATH, 'w') as f:
        f.write(html)
    print(f"   ✅ Saved to {OUTPUT_PATH}")

    # ── 变化检测：有变化才部署 + 推送；无变化静默跳过 ──
    force = "--force" in sys.argv
    new_snap = build_snapshot(all_cities)
    old_snap = load_snapshot()
    changes = diff_snapshot(old_snap, new_snap) if old_snap else []
    changed_count = len(set(c[0] for c in changes))

    if force or (old_snap and changes):
        print(f"\n📢 检测到变化: {changed_count} 个房型 ({len(changes)} 项字段变动)")
        if no_deploy:
            print("  ⏭️  --no-deploy 模式：不部署，仅保存快照")
        else:
            save_snapshot(new_snap)   # 先存快照，随部署一起上传
            deploy()
            if not force and changes:
                msg = format_changes(changes, all_cities)
                notify_wecom(
                    f"**📢 Iglu 房态变化** ({datetime.now().strftime('%m-%d %H:%M')})\n\n{msg}\n\n"
                    f"[查看实时房态](https://{CLOUDFLARE_PROJECT}.pages.dev/)"
                )
    elif not old_snap:
        print("\n🆕 首次运行：保存快照并部署（不推送）")
        if no_deploy:
            print("  ⏭️  --no-deploy 模式：不部署")
        else:
            save_snapshot(new_snap)   # 先存快照，随部署一起上传
            deploy()
    else:
        print("\n✅ 无变化，跳过部署（避免无意义更新）")
        save_snapshot(new_snap)

    print(f"\n✅ Done! {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
