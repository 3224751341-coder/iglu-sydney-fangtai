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

    # No visible inventory number → assume available
    return ('available', None, '')


def extract_dates(html: str) -> dict:
    """Extract available start dates and Flexible Start indicator.
    Returns {'dates': [...], 'flexible': bool}"""
    from html.parser import HTMLParser

    dates = []
    month_map = {m: i for i, m in enumerate([
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ], 1)}

    # Check for Flexible Start option (clickable element, not just example text)
    flexible = bool(re.search(
        r'<(?:a|button|option|label|span)[^>]*?>\s*Flexible\s*Start\s*</(?:a|button|option|label|span)>',
        html, re.IGNORECASE
    ))
    # Also check for "Flexible Start" near booking UI
    if not flexible:
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
    return {'dates': unique, 'flexible': flexible}


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
    Flexible Start（灵活自选）优先：可随时起租（含今年），即使只列出明年具体日期。"""
    from collections import defaultdict
    from datetime import datetime
    dates = date_data.get('dates', []) if isinstance(date_data, dict) else []
    flexible = date_data.get('flexible', False) if isinstance(date_data, dict) else False
    if not dates:
        if avail_status == 'waitlist':
            return '今年无房（等位）'
        return '灵活自选'

    this_year = datetime.now().year
    this_dates = sorted(d for d in dates if d[0] == this_year)
    future_dates = sorted(d for d in dates if d[0] > this_year)

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

    # 灵活自选：可随时起租（含今年），即使只列出明年的具体日期
    if flexible and not this_dates:
        return '灵活自选'

    if this_dates:
        if flexible:
            label = '灵活自选（' + short(this_dates) + ' 起）'
        else:
            label = '今年起租：' + short(this_dates)
        if future_dates:
            label += '（亦可' + full(future_dates) + '）'
        return label
    return '今年已无房：' + full(future_dates)


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
    else:
        return ('row-off', '<span class="tag tag-off">未知</span>')


def build_date_cell(room: dict) -> str:
    """起租日期单元格：醒目徽标（今年可订 / 今年已无房 / 等位无房 / 灵活自选）+ 日期细节。
    今年可订 = 有今年日期 或 Flexible Start（灵活起租，可今年入住）。"""
    from datetime import datetime
    date_data = room.get('date_data', {})
    avail = room['avail_status']
    dates = date_data.get('dates', []) if isinstance(date_data, dict) else []
    flexible = date_data.get('flexible', False) if isinstance(date_data, dict) else False
    this_year = datetime.now().year

    if avail == 'soldout':
        return '<span class="tag tag-off tag-mini">已售罄</span>'
    if avail == 'waitlist':
        return '<span class="tag tag-bad tag-mini">等位无房</span>'
    if not dates:
        if flexible:
            return '<span class="tag tag-ok tag-mini">今年可订</span> <span class="date-detail">灵活起租</span>'
        return '<span class="tag tag-ok tag-mini">灵活自选</span>'

    this_dates = [d for d in dates if d[0] == this_year]
    future_dates = [d for d in dates if d[0] > this_year]

    if this_dates or flexible:
        if this_dates:
            detail = format_dates({'dates': this_dates, 'flexible': False})
            if future_dates:
                detail += '（亦可' + format_dates({'dates': future_dates, 'flexible': False}) + '）'
        else:
            detail = '灵活起租'
        return f'<span class="tag tag-ok tag-mini">今年可订</span> <span class="date-detail">{detail}</span>'
    else:
        detail = format_dates({'dates': future_dates, 'flexible': False})
        return f'<span class="tag tag-off tag-mini">今年已无房</span> <span class="date-detail">{detail}</span>'


def build_studio_row(room: dict) -> str:
    """Build a single studio/apt table row."""
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


def build_share_row(room: dict) -> str:
    """Build a single share table row."""
    p = room['prices']
    row_cls, status_html = avail_info(room["avail_status"], room["avail_count"])
    return (
        f'<tr class="{row_cls}">'
        f'<td><span class="room-name">{room["name"]}</span></td>'
        f'<td>{room["area"]}</td>'
        f'<td>{room["bed"]}</td>'
        f'<td><span class="price">{format_price(p, "12月")}</span></td>'
        f'<td><span class="price">{format_price(p, "44周")}</span></td>'
        f'<td><span class="price">{format_price(p, "22周")}</span></td>'
        f'<td><span class="price">{format_price(p, "短租")}</span></td>'
        f'<td>{room["note"]}</td>'
        f'<td>{status_html}</td>'
        f'<td>{build_date_cell(room)}</td>'
        f'</tr>'
    )


def build_prop_panel(prop: dict, is_first: bool) -> str:
    """Build a single property panel with sub-tabs (Studio / 1居室 / 合租)."""
    # Group rooms by type, in TYPE_ORDER
    groups = {t: [] for t in TYPE_ORDER}
    for room in prop['rooms']:
        t = room['type'] if room['type'] in groups else 'Share'
        groups[t].append(room)

    sub_tabs_html = ""
    panels_html = []
    first_rendered = True

    for t in TYPE_ORDER:
        rows = groups[t]
        if not rows:
            continue
        if t == 'Share':
            row_builder = build_share_row
            thead = '<th>房型</th><th>卧室面积</th><th>床型</th><th>12/24月</th><th>44周</th><th>22周</th><th>短租</th><th>合租人数</th><th>库存</th><th>起租日期</th>'
        else:
            row_builder = build_studio_row
            thead = '<th>房型</th><th>面积</th><th>床型</th><th>12/24月</th><th>44周</th><th>22周</th><th>短租</th><th>库存</th><th>起租日期</th>'

        active_cls = ' active' if first_rendered else ''
        sub_tabs_html += f'<button class="sub-tab{active_cls}" data-type="{t}" onclick="switchSub(\'{prop["slug"]}\',\'{t}\')">{TYPE_TAB_LABELS.get(t, t)}</button>'
        panels_html.append(f'''<div class="sub-panel{active_cls}" data-type="{t}">
<div class="table-wrap"><table>
<thead><tr>{thead}</tr></thead>
<tbody>{"".join(row_builder(r) for r in rows)}</tbody>
</table></div></div>''')
        first_rendered = False

    coming_soon_html = ""
    if not groups['Studio'] and not groups['Apt'] and not groups['Share']:
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
<div class="sub-tabs">{sub_tabs_html}</div>
{"".join(panels_html)}{coming_soon_html}
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
