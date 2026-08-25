#!/usr/bin/env python3
"""
Iglu 起租日期差分核对器（Playwright）
================================
原理：用无头浏览器打开官网房型页，驱动官网自己的 iglu.js 渲染出真实日历，
读取「第一个可选日期」，与 update_fangtai.py 的 Python 解析结果逐一对比。
两边输入是同一份 HTML —— 差异只能来自解析规则偏差，即脚本 bug。

用法: python verify_calendar.py [--sample N] [--city sydney] [--no-alert]
输出: 核对报告；有差异时退出码 1 并推送企业微信告警（配置了 WECOM_WEBHOOK 时）
CI: .github/workflows/verify.yml 每日跑一次全量
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))

# 复用 update_fangtai.py 的 CITIES 清单与 extract_dates 解析器
_spec = importlib.util.spec_from_file_location("uf", os.path.join(PROJ_DIR, "update_fangtai.py"))
uf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uf)

BASE = "https://iglu.com.au/rooms"
TERMS = ["SS", "22", "44", "12", "24", "6"]  # radio id 后缀：mnthSS / mnth22 / ...

# 浏览器内执行的 JS 片段 ----------------------------------------------------

JS_CLICK_RADIO = """(term) => {
    const r = document.getElementById('mnth' + term);
    if (!r) return false;
    r.click();
    return true;
}"""

JS_FLEX_STATE = """() => {
    const btn = jQuery('#availNowBtn');
    if (!btn.length) return {visible: false};
    return {visible: btn.closest('li').is(':visible')};
}"""

JS_OPEN_CALENDAR = """() => {
    jQuery('#availNowBtn').removeClass('selected').click();
    return true;
}"""

JS_FIRST_SELECTABLE = """() => {
    const dp = jQuery('#iglu-datepicker');
    // 当前视图无可选日时向后翻页（minDate 可能远于当前月，如 2027-01），
    // next 按钮 disabled 即到 maxDate 边界
    for (let i = 0; i < 24; i++) {
        const tds = dp.find('td[data-handler="selectDay"]');
        if (tds.length) {
            const td = tds.first();
            const d = parseInt(td.find('a').first().text(), 10);
            if (d > 0) return { y: td.data('year'), m: td.data('month') + 1, d: d };
        }
        const next = dp.find('a.ui-datepicker-next').first();
        if (!next.length || next.hasClass('ui-state-disabled')) return null;
        next.click();
    }
    return null;
}"""

JS_VISIBLE_FIXED = """() => {
    const out = [];
    jQuery('#move-in-dates a[data-id]').filter(':visible').each(function () {
        out.push(jQuery(this).attr('data-id'));
    });
    return out;
}"""


def ui_probe_room(page, url):
    """驱动官网 UI，返回 {flex_first, ss_first, fixed[]}（均为 (y,m,d) 或 None）"""
    out = {"flex_first": None, "ss_first": None, "fixed": []}
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    if "just a moment" in page.title().lower():
        raise RuntimeError("Cloudflare challenge")
    try:
        page.wait_for_selector("#move-in-dates, #rtermsUL", timeout=8000)
    except Exception:
        # 无预订面板（等位/售罄页）——官网无任何起租入口，返回空结果与解析器对比：
        # 若解析器在这种页面还报出日期，即为真实 bug
        return out
    page.wait_for_timeout(800)  # 等 triggerLterms() 跑完

    for term in TERMS:
        if not page.evaluate(JS_CLICK_RADIO, term):
            continue
        page.wait_for_timeout(300)
        # 该租期下可见的固定起租日（无论 Flexible Start 是否显示都要收集）
        for did in page.evaluate(JS_VISIBLE_FIXED):
            m = re.match(r"(\d{2})/(\d{2})/(\d{4})", did)
            if m:
                out["fixed"].append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
        # 该租期下 Flexible Start 是否显示
        if not page.evaluate(JS_FLEX_STATE)["visible"]:
            continue
        page.evaluate(JS_OPEN_CALENDAR)
        page.wait_for_timeout(400)
        first = page.evaluate(JS_FIRST_SELECTABLE)
        if term == "SS":
            out["ss_first"] = (first["y"], first["m"], first["d"]) if first else None
        elif out["flex_first"] is None or (first and first["y"] and (first["y"], first["m"], first["d"]) < out["flex_first"]):
            if first:
                out["flex_first"] = (first["y"], first["m"], first["d"])
    out["fixed"] = sorted(set(out["fixed"]))
    return out


def parser_probe(html):
    d = uf.extract_dates(html)
    return {
        "flex_first": d.get("flexible_start"),
        "ss_first": (d.get("shortstay_dates") or [None])[0],
        "fixed": d.get("dates") or [],
        "flexible": d.get("flexible"),
    }


def fmt(t):
    return f"{t[0]}-{t[1]:02d}-{t[2]:02d}" if t else "无"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="只核对前 N 个房型（0=全部）")
    ap.add_argument("--city", default="", help="只核对指定城市 slug")
    ap.add_argument("--no-alert", action="store_true")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    jobs = []
    for city_slug, cd in uf.CITIES.items():
        if args.city and city_slug != args.city:
            continue
        for prop, rooms in cd["property_rooms"].items():
            for room in rooms:
                jobs.append((city_slug, prop, room, cd["label"]))
    if args.sample:
        jobs = jobs[: args.sample]

    print(f"核对 {len(jobs)} 个房型 — {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 72)

    rows, mismatches = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-AU",
        )
        page = ctx.new_page()
        for i, (city, prop, room, label) in enumerate(jobs, 1):
            url = f"{BASE}/{city}/{prop}/{room}/"
            name = f"{label}/{prop}/{room}"
            try:
                ui = ui_probe_room(page, url)
                raw_html = page.content()
                # 解析器输入必须是与 UI 交互前的初始 DOM：重新加载取干净版本
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(500)
                raw_html = page.content()
                pa = parser_probe(raw_html)
            except Exception as e:
                rows.append((name, "SKIP", str(e)[:80]))
                continue

            diffs = []
            if (ui["flex_first"] or None) != (pa["flex_first"] or None):
                diffs.append(f"长租灵活: 官网日历={fmt(ui['flex_first'])} 脚本={fmt(pa['flex_first'])}")
            if (ui["ss_first"] or None) != (pa["ss_first"] or None):
                diffs.append(f"短租: 官网日历={fmt(ui['ss_first'])} 脚本={fmt(pa['ss_first'])}")
            ui_fixed = {tuple(x) for x in ui["fixed"]}
            pa_fixed = {tuple(x) for x in pa["fixed"]}
            if ui_fixed != pa_fixed:
                only_ui = ui_fixed - pa_fixed
                only_pa = pa_fixed - ui_fixed
                diffs.append(f"固定日期: 官网={sorted(ui_fixed)} 脚本={sorted(pa_fixed)}")
            if diffs:
                mismatches.append((name, diffs))
                rows.append((name, "MISMATCH", "; ".join(diffs)))
            else:
                rows.append((name, "OK", f"长租{fmt(ui['flex_first'])} 短租{fmt(ui['ss_first'])} 固定{len(ui_fixed)}个"))
            if i % 10 == 0:
                print(f"  进度 {i}/{len(jobs)}，已发现差异 {len(mismatches)}")

        browser.close()

    print("=" * 72)
    for name, status, detail in rows:
        mark = {"OK": "✅", "MISMATCH": "❌", "SKIP": "⏭️ "}[status]
        print(f"{mark} [{status:8s}] {name}: {detail}")

    n_ok = sum(1 for r in rows if r[1] == "OK")
    n_skip = sum(1 for r in rows if r[1] == "SKIP")
    print("=" * 72)
    print(f"结果: 一致 {n_ok} | 差异 {len(mismatches)} | 跳过 {n_skip} / 共 {len(rows)}")

    if mismatches and not args.no_alert:
        webhook = os.environ.get("WECOM_WEBHOOK", "")
        if webhook:
            lines = "\n".join(f"• {n}: {'; '.join(d)}" for n, d in mismatches[:15])
            uf.notify_wecom(
                f"⚠️ Iglu 起租日期核对发现 {len(mismatches)} 个差异 ({datetime.now():%m-%d %H:%M})\n\n{lines}\n\n"
                f"请检查 update_fangtai.py 解析规则与官网 iglu.js 的偏差"
            )

    report = {"time": datetime.now().isoformat(), "total": len(rows),
              "ok": n_ok, "mismatch": len(mismatches), "skip": n_skip,
              "rows": [{"room": n, "status": s, "detail": d} for n, s, d in rows]}
    try:
        report_path = os.path.join(PROJ_DIR, "verify_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except OSError:
        report_path = "/tmp/verify_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"报告已存 {report_path}")

    sys.exit(1 if mismatches else 0)


if __name__ == "__main__":
    main()
