#!/usr/bin/env python3
"""
Iglu Sydney 全公寓房态抓取 + 网页更新脚本
用法: python3 update_fangtai.py
输出: 更新 index.html → 自动部署到 Cloudflare Pages
"""

import json, re, sys, os, subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Config ──
AGENT_CODE = "A1336"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(PROJECT_DIR, "template.html")
OUTPUT_PATH = os.path.join(PROJECT_DIR, "index.html")
CLOUDFLARE_PROJECT = "iglu-centralpark"
MAX_WORKERS = 10
REQUEST_TIMEOUT = 25

# ── Sydney Properties ──
PROPERTIES = {
    "Broadway": "broadway",
    "Central": "central",
    "Central Park": "central-park",
    "Chatswood": "chatswood",
    "Mascot": "mascot",
    "Redfern": "redfern",
    "Summer Hill": "summer-hill",
    "Waterloo": "waterloo",
}

# ── Room metadata (manually curated to avoid scraping noise) ──
ROOM_META = {
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
}

# U18 rooms - separated for clarity
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


def fetch_page(url: str) -> str:
    """Fetch a page using curl (better TLS fingerprint)."""
    cmd = [
        "curl", "-sL",
        "--compressed",
        "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: en-AU,en;q=0.9",
        "--connect-timeout", "15",
        "--max-time", str(REQUEST_TIMEOUT),
        url
    ]
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

    # "Short Stay ($600/wk)"
    ss_m = re.search(r'Short\s+Stay\s*(?:\(|\(?\*?\*?)?\$([\d,]+)', text, re.IGNORECASE)
    if ss_m:
        prices['短租'] = int(ss_m.group(1).replace(',', ''))

    # "12 Months...$XXX" or "12-month...$XXX"  (less common, only some rooms show this)
    m12_m = re.search(r'12[\s-]*Months?[^$]*\$([\d,]+)', text, re.IGNORECASE)
    if m12_m:
        prices['12月'] = int(m12_m.group(1).replace(',', ''))

    # "24 Months...$XXX"
    m24_m = re.search(r'24[\s-]*Months?[^$]*\$([\d,]+)', text, re.IGNORECASE)
    if m24_m:
        prices['24月'] = int(m24_m.group(1).replace(',', ''))

    # If we only have "From", use it as default for 短租
    if 'From' in prices and not prices:
        pass  # Keep 'From' as the only indicator

    return prices


def extract_availability(html: str) -> tuple:
    """Extract availability status and count. Returns (status, count, text)."""
    # Check for specific patterns
    patterns = [
        (r'(\d+)\s*LEFT\s*AT\s*THIS\s*PRICE', 'available'),
        (r'(\d+)\s*left\s*at\s*this\s*price', 'available'),
        (r'Hurry!?\s*Only\s*(\d+)\s*spots?\s*left', 'limited'),
        (r'Only\s*(\d+)\s*spots?\s*left', 'limited'),
        (r'(\d+)\s*spots?\s*left', 'limited'),
        (r'sold\s*out', 'soldout'),
        (r'currently\s*sold\s*out', 'soldout'),
        (r'wait\s*list', 'waitlist'),
        (r'waitlist', 'waitlist'),
        (r'join\s*the\s*wait\s*list', 'waitlist'),
    ]

    for pattern, status in patterns:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            count = int(m.group(1)) if m.lastindex and m.group(1).isdigit() else None
            return (status, count, m.group(0))

    return ('unknown', None, '')


def extract_dates(html: str) -> list:
    """Extract available start dates from a room page.
    Only extracts dates that appear as clickable buttons/links (not example text)."""
    from html.parser import HTMLParser

    dates = []
    month_map = {m: i for i, m in enumerate([
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ], 1)}

    # Strategy 1: Find dates inside <a> or <button> tags (real clickable options)
    # Look for patterns like: <a ...>12 June 2026</a> or <button ...>Flexible Start</button>
    clickable_pattern = re.finditer(
        r'<(?:a|button|option|label)[^>]*?>\s*(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s*</(?:a|button|option|label)>',
        html, re.IGNORECASE
    )
    for m in clickable_pattern:
        day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = month_map.get(month_name)
        if month:
            dates.append((year, month, day))

    # Strategy 2: Look for dates near "date" class containers (booking form)
    if not dates:
        # Find the booking section and extract dates only from that area
        booking_section = re.search(
            r'(?:start-date|move-in|contract-start|date-select|when would you like)',
            html, re.IGNORECASE
        )
        if booking_section:
            # Search only within 2000 chars after the booking section marker
            section_start = max(0, booking_section.start() - 500)
            section_end = min(len(html), booking_section.end() + 3000)
            section_html = html[section_start:section_end]

            # Exclude example text ("e.g.", "for example")
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

    # Deduplicate and sort
    seen = set()
    unique = []
    for d in dates:
        key = f"{d[2]:02d}-{d[1]:02d}"
        if key not in seen:
            seen.add(key)
            unique.append(d)
    unique.sort()
    return unique


def extract_features(html: str) -> dict:
    """Extract room features from the page."""
    features = {}
    # Area
    area_m = re.search(r'(\d+)\s*m²', html)
    if area_m:
        features['area'] = f"{area_m.group(1)}m²"

    # Bed type
    if re.search(r'queen\s*bed', html, re.IGNORECASE):
        features['bed'] = 'Queen'
    elif re.search(r'king\s*single', html, re.IGNORECASE):
        features['bed'] = 'King Single'
    elif re.search(r'double\s*bed', html, re.IGNORECASE):
        features['bed'] = 'Double'

    return features


def format_price(prices: dict, key: str) -> str:
    """Format a price value for display."""
    val = prices.get(key)
    if val is None:
        return "—"
    return f"${val:,}"


def format_dates(dates: list) -> str:
    """Format dates for display. Return compact string."""
    if not dates:
        return "灵活自选"

    # Group by month
    from collections import defaultdict
    by_month = defaultdict(list)
    for y, m, d in dates:
        by_month[f"{m}月"].append(d)

    parts = []
    for month, days in by_month.items():
        # Compact: "6.12-15" for consecutive days
        days.sort()
        ranges = []
        start = days[0]
        end = days[0]
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
                day_strs.append(str(s))
            else:
                day_strs.append(f"{s}-{e}")
        parts.append(f"{month}{'.'.join(day_strs)}")

    return ', '.join(parts)


def scrape_room(property_slug: str, room_slug: str) -> dict:
    """Scrape a single room page and return structured data."""
    url = f"https://iglu.com.au/rooms/sydney/{property_slug}/{room_slug}/"
    try:
        html = fetch_page(url)
    except Exception as e:
        return {"error": str(e), "url": url, "slug": room_slug}

    prices = extract_prices(html)
    avail_status, avail_count, avail_text = extract_availability(html)
    dates = extract_dates(html)

    meta = ROOM_META.get(room_slug, (room_slug.replace('-', ' ').title(), "Unknown", "?", "?", ""))

    return {
        "slug": room_slug,
        "url": url,
        "name": meta[0],
        "type": meta[1],  # Studio or Share
        "area": meta[2],
        "bed": meta[3],
        "note": meta[4] if len(meta) > 4 else "",
        "prices": prices,
        "avail_status": avail_status,
        "avail_count": avail_count,
        "avail_text": avail_text,
        "dates": dates,
        "date_str": format_dates(dates),
    }


# Explicit mapping of property slug → room slugs
PROPERTY_ROOM_MAP = {
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
}


def scrape_property(name: str, slug: str) -> dict:
    """Scrape all rooms for a property."""
    print(f"  📍 {name} ({slug})")

    room_slugs = PROPERTY_ROOM_MAP.get(slug, [])

    print(f"     {len(room_slugs)} room types to scrape")

    rooms = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scrape_room, slug, rs): rs for rs in room_slugs}
        for future in as_completed(futures):
            result = future.result()
            if "error" not in result:
                rooms.append(result)
                print(f"     ✅ {result['name']}: {result.get('prices', {}).get('From', 'N/A')}")
            else:
                print(f"     ❌ {futures[future]}: {result['error']}")

    # Sort: Studio first, then Share
    rooms.sort(key=lambda r: (0 if r['type'] == 'Studio' else 1, r['name']))
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


def build_studio_row(room: dict) -> str:
    """Build a single studio table row."""
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
        f'<td><span class="price">{format_price(p, "22周")}</span></td>'
        f'<td><span class="price">{format_price(p, "短租")}</span></td>'
        f'<td>{status_html}</td>'
        f'<td>{room["date_str"]}</td>'
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
        f'<td><span class="price">{format_price(p, "22周")}</span></td>'
        f'<td><span class="price">{format_price(p, "短租")}</span></td>'
        f'<td>{room["note"]}</td>'
        f'<td>{status_html}</td>'
        f'<td>{room["date_str"]}</td>'
        f'</tr>'
    )


def build_property_section(prop: dict) -> str:
    """Build HTML section for a single property."""
    studio_rows = []
    share_rows = []
    for room in prop['rooms']:
        if room['type'] == 'Studio':
            studio_rows.append(build_studio_row(room))
        else:
            share_rows.append(build_share_row(room))

    sections = []
    if studio_rows:
        sections.append(f'''<div class="table-wrap fade-in" style="margin-bottom:24px">
<h3 style="padding:16px 20px 0;font-size:0.85rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em">🏠 Studio</h3>
<table><thead><tr><th>房型</th><th>面积</th><th>床型</th><th>12/24月</th><th>22周</th><th>短租</th><th>库存</th><th>起租日期</th></tr></thead>
<tbody>{"".join(studio_rows)}</tbody></table></div>''')

    if share_rows:
        sections.append(f'''<div class="table-wrap fade-in" style="margin-bottom:24px">
<h3 style="padding:16px 20px 0;font-size:0.85rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em">👥 合租单间</h3>
<table><thead><tr><th>房型</th><th>卧室面积</th><th>床型</th><th>22周</th><th>短租</th><th>合租人数</th><th>库存</th><th>起租日期</th></tr></thead>
<tbody>{"".join(share_rows)}</tbody></table></div>''')

    if not sections:
        sections.append('<p style="color:var(--text-muted);padding:20px">暂无房型数据</p>')

    return "\n".join(sections)


def build_prop_panel(prop: dict, is_first: bool) -> str:
    """Build a single property panel with Studio/Share sub-tabs."""
    studio_rows = []
    share_rows = []
    for room in prop['rooms']:
        if room['type'] == 'Studio':
            studio_rows.append(build_studio_row(room))
        else:
            share_rows.append(build_share_row(room))

    studio_html = ""
    share_html = ""
    sub_tabs_html = ""
    active_class = " active" if is_first else ""

    if studio_rows:
        sub_tabs_html += f'<button class="sub-tab active" data-type="studio" onclick="switchSub(\'{prop["slug"]}\',\'studio\')">🏠 Studio</button>'
        studio_html = f'''<div class="sub-panel active" data-type="studio">
<div class="table-wrap"><table>
<thead><tr><th>房型</th><th>面积</th><th>床型</th><th>12/24月</th><th>22周</th><th>短租</th><th>库存</th><th>起租日期</th></tr></thead>
<tbody>{"".join(studio_rows)}</tbody>
</table></div></div>'''
    if share_rows:
        sub_tabs_html += f'<button class="sub-tab{" active" if not studio_rows else ""}" data-type="share" onclick="switchSub(\'{prop["slug"]}\',\'share\')">👥 合租</button>'
        share_html = f'''<div class="sub-panel{" active" if not studio_rows else ""}" data-type="share">
<div class="table-wrap"><table>
<thead><tr><th>房型</th><th>卧室面积</th><th>床型</th><th>22周</th><th>短租</th><th>合租人数</th><th>库存</th><th>起租日期</th></tr></thead>
<tbody>{"".join(share_rows)}</tbody>
</table></div></div>'''

    return f'''<div class="prop-panel{active_class}" id="prop-{prop['slug']}">
<div class="sub-tabs">{sub_tabs_html}</div>
{studio_html}{share_html}
</div>'''


def build_html(all_properties: list) -> str:
    """Build the complete HTML page from template and data."""
    with open(TEMPLATE_PATH, 'r') as f:
        template = f.read()

    now = datetime.now()
    update_time = now.strftime("%Y年%m月%d日 %H:%M")
    update_badge = now.strftime("%m/%d %H:%M 更新")

    # Build property nav buttons
    nav_buttons = []
    for i, prop in enumerate(all_properties):
        room_count = len(prop['rooms'])
        active = ' active' if i == 0 else ''
        nav_buttons.append(
            f'<button class="prop-btn{active}" id="prop-btn-{prop["slug"]}" '
            f'onclick="switchProp(\'{prop["slug"]}\')">{prop["name"]}<span style="font-size:0.7rem;opacity:0.6;margin-left:4px">{room_count}</span></button>'
        )

    # Build property panels
    panels = []
    for i, prop in enumerate(all_properties):
        panels.append(build_prop_panel(prop, is_first=(i == 0)))

    # Replace placeholders
    html = template
    html = html.replace("{{UPDATE_TIME}}", update_time)
    html = html.replace("{{UPDATE_BADGE}}", update_badge)
    html = html.replace("{{PROP_NAV}}", "\n".join(nav_buttons))
    html = html.replace("{{PROP_PANELS}}", "\n".join(panels))

    return html


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
    print("=" * 50)
    print(f"🔄 Iglu Sydney 房态更新 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    all_properties = []
    total_rooms = 0

    for prop_name, prop_slug in PROPERTIES.items():
        prop_data = scrape_property(prop_name, prop_slug)
        all_properties.append(prop_data)
        total_rooms += len(prop_data['rooms'])

    print(f"\n📊 Total: {len(all_properties)} properties, {total_rooms} room types")

    # Build HTML
    print("\n📝 Generating HTML...")
    html = build_html(all_properties)

    with open(OUTPUT_PATH, 'w') as f:
        f.write(html)
    print(f"   ✅ Saved to {OUTPUT_PATH}")

    # Deploy
    deploy()

    print(f"\n✅ Done! {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
