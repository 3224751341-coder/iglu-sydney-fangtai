// -*- coding: utf-8 -*-
// Iglu 澳洲房态抓取器 —— 从 GitHub Actions（update_fangtai.py）搬进应用容器。
// 页面本身是静态渲染的，正则解析逻辑与原 Python 版一一对应；但这个平台的出口代理 IP
// 信誉不够，纯 Node fetch 会被 Cloudflare 拦下 JS 挑战，改用 Playwright 真实浏览器加载
// 页面（不用像 Accolade 那样点弹窗，只是加载+取 HTML），解析部分完全复用不变。
// 容器内每 30 分钟跑一次（见 server.mjs），抓取结果渲染进 template.html，写入 DATA_DIR。
import { chromium } from "playwright";
import { readFile, writeFile, rename, mkdir } from "node:fs/promises";
import path from "node:path";

const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
const REQUEST_TIMEOUT_MS = 25000;
// 之前 fetch 版本用 6 并发没问题；换成 Playwright 后同一时刻多个页面一起首次撞上
// Cloudflare 挑战，观感更像爬虫。调低并发，降低被判定为批量抓取的概率。
const MAX_WORKERS = 3;
const WECOM_WEBHOOK = process.env.WECOM_WEBHOOK || "";

const DATA ={"CITIES": {"sydney": {"label": "悉尼", "properties": {"Broadway": "broadway", "Central": "central", "Central Park": "central-park", "Chatswood": "chatswood", "Mascot": "mascot", "Mascot Duo": "mascot-duo", "Redfern": "redfern", "Summer Hill": "summer-hill", "Waterloo": "waterloo"}, "room_meta": {"standard-studio-apartment-nras-br": ["Standard Studio NRAS", "Studio", "17m²", "Queen", "NRAS补贴"], "single-bedroom-6-share-apt-br": ["6 Share Apt", "Share", "~13m²", "King Single", "6人"], "single-bedroom-5-share-apt-br": ["5 Share Apt", "Share", "~13m²", "King Single", "5人"], "single-bedroom-4-share-apt-br": ["4 Share Apt", "Share", "~13m²", "King Single", "4人"], "standard-studio-apartment-br": ["Standard Studio", "Studio", "17m²", "Queen", ""], "superior-studio-apartment-br": ["Superior Studio", "Studio", "21m²", "Queen+沙发", ""], "premium-studio-apartment-br": ["Premium Studio", "Studio", "31m²", "Queen+客厅", ""], "single-bedroom-share-bathroom-ce": ["Single Share Bath", "Share", "~12m²", "King Single", "Share Bath"], "single-bedroom-6-share-apt-ce": ["6 Share Apt", "Share", "~13m²", "King Single", "6人"], "single-bedroom-5-share-apt-ce": ["5 Share Apt", "Share", "~13m²", "King Single", "5人"], "standard-studio-apartment-ce": ["Standard Studio", "Studio", "17m²", "Queen", ""], "standard-studio-apartment-cp": ["Standard Studio", "Studio", "17m²", "Queen", ""], "superior-studio-apartment": ["Superior Studio", "Studio", "21m²", "Queen+沙发", ""], "premium-studio-apartment-cp": ["Premium Studio", "Studio", "31m²", "Queen+客厅", ""], "single-bedroom-6-share-apt-cp": ["6 Share Apt", "Share", "~13m²", "King Single", "6人"], "single-bedroom-4-share-apt-cp": ["4 Share Apt", "Share", "~13m²", "King Single", "4人"], "single-bedroom-3-share-apt-cp": ["3 Share Apt", "Share", "~13m²", "King Single", "3人"], "premium-studio-nras-cp": ["Premium Studio NRAS", "Studio", "31m²", "Queen", "NRAS补贴"], "single-bedroom-6-share-apt-ch": ["6 Share Apt", "Share", "~13m²", "King Single", "6人"], "single-bedroom-5-share-apt-ch": ["5 Share Apt", "Share", "~13m²", "King Single", "5人"], "single-bedroom-4-share-apt-ch": ["4 Share Apt", "Share", "~13m²", "King Single", "4人"], "standard-studio-apartment-ch": ["Standard Studio", "Studio", "17m²", "Queen", ""], "superior-studio-apartment-ch": ["Superior Studio", "Studio", "21m²", "Queen+沙发", ""], "premium-studio-apartment-ch": ["Premium Studio", "Studio", "31m²", "Queen+客厅", ""], "single-bedroom-6-share-apt-ma": ["6 Share Apt", "Share", "~13m²", "King Single", "6人"], "premium-single-bedroom-6-share-ma": ["Premium 6 Share", "Share", "~14m²", "King Single", "6人"], "standard-studio-apartment-ma": ["Standard Studio", "Studio", "17m²", "Queen", ""], "premium-studio-apartment-ma": ["Premium Studio", "Studio", "31m²", "Queen+客厅", ""], "standard-studio-apartment-queen": ["Standard Studio Queen", "Studio", "17m²", "Queen", ""], "single-bed-6-share-apt-saex-sre": ["6 Share SAEX", "Share", "~13m²", "King Single", "6人 USYD"], "single-bedroom-6-share-apt-re": ["6 Share Apt", "Share", "~13m²", "King Single", "6人"], "single-bedroom-5-share-apt-re": ["5 Share Apt", "Share", "~13m²", "King Single", "5人"], "single-bedroom-4-share-apt-re": ["4 Share Apt", "Share", "~13m²", "King Single", "4人"], "single-studio-apartment-re": ["Single Studio", "Studio", "15m²", "Double", ""], "standard-studio-apartment-re": ["Standard Studio", "Studio", "17m²", "Queen", ""], "premium-studio-apartment-re": ["Premium Studio", "Studio", "31m²", "Queen+客厅", ""], "single-bedroom-6-share-nras": ["6 Share NRAS", "Share", "~13m²", "King Single", "6人 NRAS"], "single-studio-apartment-nras": ["Single Studio NRAS", "Studio", "15m²", "Double", "NRAS"], "standard-studio-apartment-nras": ["Standard Studio NRAS", "Studio", "17m²", "Queen", "NRAS"], "standard-studio-apartment-sh": ["Standard Studio", "Studio", "17m²", "Queen", ""], "premium-studio-apartment-sh": ["Premium Studio", "Studio", "31m²", "Queen+客厅", ""], "single-bedroom-2-share-apt-wa": ["2 Share Apt", "Share", "~13m²", "King Single", "2人"], "standard-studio-apartment-wa": ["Standard Studio", "Studio", "17m²", "Queen", ""], "superior-studio-apartment-wa": ["Superior Studio", "Studio", "21m²", "Queen+沙发", ""], "premium-studio-apartment-wa": ["Premium Studio", "Studio", "31m²", "Queen+客厅", ""]}, "property_rooms": {"broadway": ["standard-studio-apartment-nras-br", "single-bedroom-6-share-apt-br", "single-bedroom-5-share-apt-br", "single-bedroom-4-share-apt-br", "standard-studio-apartment-br", "superior-studio-apartment-br", "premium-studio-apartment-br"], "central": ["single-bedroom-share-bathroom-ce", "single-bedroom-6-share-apt-ce", "single-bedroom-5-share-apt-ce", "standard-studio-apartment-ce"], "central-park": ["standard-studio-apartment-cp", "superior-studio-apartment", "premium-studio-apartment-cp", "single-bedroom-6-share-apt-cp", "single-bedroom-4-share-apt-cp", "single-bedroom-3-share-apt-cp", "premium-studio-nras-cp"], "chatswood": ["single-bedroom-6-share-apt-ch", "single-bedroom-5-share-apt-ch", "single-bedroom-4-share-apt-ch", "standard-studio-apartment-ch", "superior-studio-apartment-ch", "premium-studio-apartment-ch"], "mascot": ["single-bedroom-6-share-apt-ma", "premium-single-bedroom-6-share-ma", "standard-studio-apartment-ma", "premium-studio-apartment-ma", "standard-studio-apartment-queen"], "mascot-duo": [], "redfern": ["single-bed-6-share-apt-saex-sre", "single-bedroom-6-share-apt-re", "single-bedroom-5-share-apt-re", "single-bedroom-4-share-apt-re", "single-studio-apartment-re", "standard-studio-apartment-re", "premium-studio-apartment-re", "single-bedroom-6-share-nras", "single-studio-apartment-nras", "standard-studio-apartment-nras"], "summer-hill": ["standard-studio-apartment-sh", "premium-studio-apartment-sh"], "waterloo": ["single-bedroom-2-share-apt-wa", "standard-studio-apartment-wa", "superior-studio-apartment-wa", "premium-studio-apartment-wa"]}}, "melbourne": {"label": "墨尔本", "properties": {"Flagstaff Gardens": "flagstaff-gardens", "Flagstaff Station": "flagstaff-station", "Melbourne Central": "melbourne-central", "Melbourne City": "melbourne-city", "South Yarra": "south-yarra"}, "room_meta": {"premium-corner-studio-apartment-fg": ["Premium Corner Studio", "Studio", "?", "Double", ""], "premium-single-bedroom-2-share-fg": ["Premium 2 Share", "Share", "?", "King Single", "2人"], "premium-studio-apartment-fg": ["Premium Studio", "Studio", "?", "Double", ""], "single-bedroom-2-share-apt-fg": ["2 Share Apt", "Share", "?", "King Single", "2人"], "single-studio-apartment": ["Single Studio", "Studio", "?", "King Single", ""], "standard-studio-apartment-fg": ["Standard Studio", "Studio", "?", "Double", ""], "premium-studio-apartment-cnr-fs": ["Premium Studio Corner", "Studio", "?", "Queen", ""], "premium-studio-apartment-fs": ["Premium Studio", "Studio", "?", "Queen", ""], "single-bedroom-2-share-apt-fs": ["2 Share Apt", "Share", "?", "King Single", "2人"], "standard-studio-apartment-fs": ["Standard Studio", "Studio", "?", "Queen", ""], "premium-studio-apartment-mce": ["Premium Studio", "Studio", "?", "Double", ""], "standard-studio-apartment-mce": ["Standard Studio", "Studio", "?", "Double", ""], "premium-studio-apartment-mc": ["Premium Studio", "Studio", "?", "Double", ""], "standard-studio-apartment-mc": ["Standard Studio", "Studio", "?", "Double", ""], "single-bedroom-5-share-apt-mc": ["5 Share Apt", "Share", "?", "King Single", "5人"], "single-bedroom-6-share-apt-mc": ["6 Share Apt", "Share", "?", "King Single", "6人"], "premium-single-bedroom-5-share-apt-sy": ["Premium 5 Share", "Share", "?", "King Single", "5人"], "premium-single-bedroom-6-share-apt-sy": ["Premium 6 Share", "Share", "?", "King Single", "6人"], "premium-studio-apartment-sy": ["Premium Studio", "Studio", "?", "King Single", ""], "single-bedroom-5-share-apt-sy": ["5 Share Apt", "Share", "?", "King Single", "5人"], "single-bedroom-6-share-apt-sy": ["6 Share Apt", "Share", "?", "King Single", "6人"], "single-studio-apartment-sy": ["Single Studio", "Studio", "?", "King Single", ""], "standard-studio-apartment-sy": ["Standard Studio", "Studio", "?", "King Single", ""]}, "property_rooms": {"flagstaff-gardens": ["premium-corner-studio-apartment-fg", "premium-single-bedroom-2-share-fg", "premium-studio-apartment-fg", "single-bedroom-2-share-apt-fg", "single-studio-apartment", "standard-studio-apartment-fg"], "flagstaff-station": ["premium-studio-apartment-cnr-fs", "premium-studio-apartment-fs", "single-bedroom-2-share-apt-fs", "standard-studio-apartment-fs"], "melbourne-central": ["premium-studio-apartment-mce", "standard-studio-apartment-mce"], "melbourne-city": ["premium-studio-apartment-mc", "standard-studio-apartment-mc", "single-bedroom-5-share-apt-mc", "single-bedroom-6-share-apt-mc"], "south-yarra": ["premium-single-bedroom-5-share-apt-sy", "premium-single-bedroom-6-share-apt-sy", "premium-studio-apartment-sy", "single-bedroom-5-share-apt-sy", "single-bedroom-6-share-apt-sy", "single-studio-apartment-sy", "standard-studio-apartment-sy"]}}, "brisbane": {"label": "布里斯班", "properties": {"Brisbane City": "brisbane-city", "Kelvin Grove": "kelvin-grove"}, "room_meta": {"premium-studio-apartment-bc": ["Premium Studio", "Studio", "?", "Double", ""], "standard-studio-apartment-bc": ["Standard Studio", "Studio", "?", "Double", ""], "single-bedroom-5-share-apt-bc": ["5 Share Apt", "Share", "?", "King Single", "5人"], "single-bedroom-6-share-apt-bc": ["6 Share Apt", "Share", "?", "King Single", "6人"], "student-room-shared-bathroom-bc": ["Single Share Bath", "Share", "?", "King Single", "Share Bath"], "1-bedroom-apartment-kg": ["1 Bedroom Apt", "Apt", "?", "King Single", ""], "single-bedroom-2-share-apt-kg": ["2 Share Apt", "Share", "?", "King Single", "2人"], "single-bedroom-3-share-apt-kg": ["3 Share Apt", "Share", "?", "King Single", "3人"], "single-bedroom-5-share-apt-kg": ["5 Share Apt", "Share", "?", "King Single", "5人"], "single-bedroom-6-share-apt-kg": ["6 Share Apt", "Share", "?", "King Single", "6人"]}, "property_rooms": {"brisbane-city": ["premium-studio-apartment-bc", "standard-studio-apartment-bc", "single-bedroom-5-share-apt-bc", "single-bedroom-6-share-apt-bc", "student-room-shared-bathroom-bc"], "kelvin-grove": ["1-bedroom-apartment-kg", "single-bedroom-2-share-apt-kg", "single-bedroom-3-share-apt-kg", "single-bedroom-5-share-apt-kg", "single-bedroom-6-share-apt-kg"]}}}, "COMING_SOON": ["mascot-duo"], "TYPE_ORDER": ["Studio", "Apt", "Share"], "TYPE_TAB_LABELS": {"Studio": "🏠 Studio", "Apt": "🛏️ 1居室", "Share": "👥 合租"}, "DATE_OVERRIDES": {}}
;

const { CITIES, COMING_SOON: COMING_SOON_LIST, TYPE_ORDER, DATE_OVERRIDES } = DATA;
const COMING_SOON = new Set(COMING_SOON_LIST);

const MONTH_MAP = {
  January: 1, February: 2, March: 3, April: 4, May: 5, June: 6,
  July: 7, August: 8, September: 9, October: 10, November: 11, December: 12,
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function bjNow() {
  return new Date(Date.now() + 8 * 3600 * 1000);
}

function bjTimeStr() {
  const n = bjNow();
  return `${pad(n.getUTCMonth() + 1)}-${pad(n.getUTCDate())} ${pad(n.getUTCHours())}:${pad(n.getUTCMinutes())}`;
}

// [year, month, day] 三元组 → 可比较数字
function dnum(d) {
  return d ? d[0] * 10000 + d[1] * 100 + d[2] : null;
}

function parseDdMmYy(s) {
  const m = s.match(/^\s*(\d{1,2})\/(\d{1,2})\/(\d{2,4})\s*$/);
  if (!m) return null;
  const day = parseInt(m[1], 10);
  const mon = parseInt(m[2], 10);
  const yy = m[3];
  const year = yy.length === 2 ? 2000 + parseInt(yy, 10) : parseInt(yy, 10);
  if (mon >= 1 && mon <= 12 && day >= 1 && day <= 31) return [year, mon, day];
  return null;
}

// ── 页面抓取（原用 curl_cffi 伪装 Chrome TLS 指纹绕过 Cloudflare；实测这个平台的
// 出口代理 IP 信誉不够，纯 Node fetch 直接被 Cloudflare 拦下 JS 验证，只有真实浏览器能过。
// 改用 Playwright：一次抓取周期共用一个 browser context，同一批页面共享 Cookie，
// 第一个页面过了 Cloudflare 之后，后面的页面基本免验证，比每页各开一个 context 快很多）──
let browser = null;
let sharedContext = null;

async function openBrowser() {
  const proxyUrl = process.env.HTTPS_PROXY || process.env.https_proxy;
  const launchOptions = { headless: true, args: ["--no-sandbox", "--disable-dev-shm-usage"] };
  if (!process.env.USE_BUNDLED_CHROMIUM) launchOptions.channel = "chrome";
  if (proxyUrl) launchOptions.proxy = { server: proxyUrl };
  browser = await chromium.launch(launchOptions);
  sharedContext = await browser.newContext({ userAgent: UA, locale: "en-AU" });
}

async function closeBrowser() {
  try { await sharedContext?.close(); } catch { /* best-effort cleanup */ }
  try { await browser?.close(); } catch { /* best-effort cleanup */ }
  browser = null;
  sharedContext = null;
}

// Cloudflare 有时不是纯 JS 计算挑战，而是要求勾选 Turnstile 复选框（iframe 来自
// challenges.cloudflare.com）——被动等待过不去，得真的找到并点一下（移植自 Accolade
// 那边验证过有效的同一套逻辑）。
async function clickCf(page) {
  for (let i = 0; i < 15; i++) {
    try {
      for (const fr of page.frames()) {
        if ((fr.url() || "").includes("challenges.cloudflare.com")) {
          const cb = fr.locator("input[type=checkbox]");
          if (await cb.count()) { await cb.first().check({ timeout: 3000 }); console.log("  [cf] clicked checkbox"); return; }
        }
      }
    } catch { /* frame may detach mid-check */ }
    try {
      const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 200));
      if (!/just a moment|verify you are human|checking your browser/i.test(bodyText)) return; // 已经是正常页面
    } catch { /* page navigating */ }
    await sleep(2000);
  }
}

async function fetchPage(url, retries = 3) {
  let lastErr;
  for (let attempt = 0; attempt < retries; attempt++) {
    const page = await sharedContext.newPage();
    try {
      const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: REQUEST_TIMEOUT_MS });
      try { await page.waitForLoadState("networkidle", { timeout: 8000 }); } catch { /* SPA keeps background polling */ }
      let html = await page.content();
      if (/cf-browser-verify|just a moment/i.test(html)) {
        await clickCf(page);
        html = await page.content();
      }
      if (/just a moment|verify you are human|checking your browser/i.test(html)) {
        // 部署环境没法看容器日志，把实际拦截页的状态码/标题/正文片段都记下来，
        // 方便隔着网关判断到底是交互式验证框、纯 403 block 页、还是别的什么拦截方式。
        const status = resp?.status();
        const title = await page.title().catch(() => "");
        const snippet = html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 200);
        throw new Error(`Cloudflare challenge detected (status=${status}, title="${title}", body="${snippet}")`);
      }
      if (/<title>\s*page\s+not\s+found/i.test(html)) {
        throw new Error("Page not found (404)");
      }
      return html;
    } catch (e) {
      lastErr = e;
      const msg = String(e?.message || e);
      if (msg.includes("Page not found")) throw e;
      if (attempt < retries - 1) { await sleep(3000 * (attempt + 1)); continue; }
      throw e;
    } finally {
      await page.close().catch(() => {});
    }
  }
  throw lastErr;
}

function extractPrices(html) {
  const prices = {};
  const text = html.replace(/<[^>]+>/g, " ");
  let m;
  if ((m = text.match(/From\s+\$([\d,]+)\s*\/?\s*wk/i))) prices.From = parseInt(m[1].replace(/,/g, ""), 10);
  if ((m = text.match(/22\s*Weeks?\s*(?:\(|\(?\*?\*?)?\$([\d,]+)/i))) prices["22周"] = parseInt(m[1].replace(/,/g, ""), 10);
  if ((m = text.match(/44\s*Weeks?\s*(?:\(|\(?\*?\*?)?\$([\d,]+)/i))) prices["44周"] = parseInt(m[1].replace(/,/g, ""), 10);
  if ((m = text.match(/Short\s+Stay\s*(?:\(|\(?\*?\*?)?\$([\d,]+)/i))) prices["短租"] = parseInt(m[1].replace(/,/g, ""), 10);
  if ((m = text.match(/12\s*Months?\s*(?:\(|\(?\*?\*?)?\$([\d,]+)/i))) prices["12月"] = parseInt(m[1].replace(/,/g, ""), 10);
  if ((m = text.match(/24\s*Months?\s*(?:\(|\(?\*?\*?)?\$([\d,]+)/i))) prices["24月"] = parseInt(m[1].replace(/,/g, ""), 10);
  return prices;
}

function extractAvailability(html, dateData) {
  let m = html.match(/(\d+)\s*LEFT\s*AT\s*THIS\s*PRICE/i);
  if (m) {
    const count = parseInt(m[1], 10);
    return [count >= 3 ? "available" : "limited", count, m[0]];
  }
  if (/sold\s*out/i.test(html)) return ["soldout", null, ""];
  const hasWaitlist = /wait\s*list/i.test(html);
  if (hasWaitlist) {
    if (dateData) {
      const hasDates = (dateData.dates || []).length > 0;
      const hasFlexible = !!dateData.flexible;
      if (!hasDates && !hasFlexible) return ["waitlist", null, ""];
    } else {
      const hasAnyDates = /(?:Flexible\s+Start|(\d{1,2})\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4}))/i.test(html);
      if (!hasAnyDates) return ["waitlist", null, ""];
    }
  }
  if (dateData && ((dateData.dates || []).length || (dateData.shortstay_dates || []).length || dateData.flexible)) {
    return ["available", null, ""];
  }
  return ["unknown", null, ""];
}

function extractDates(html) {
  const dates = [];

  const bufferDates = new Set();
  let bm = html.match(/available-buffer-days[^>]*?value\s*=\s*["']([^"']*)["']|value\s*=\s*["']([^"']*)["'][^>]*?available-buffer-days/);
  if (bm) {
    const bufVal = bm[1] !== undefined ? bm[1] : bm[2];
    if (bufVal) {
      for (const part of bufVal.split(",")) {
        const p = part.trim();
        if (/^\d{4}-\d{2}-\d{2}$/.test(p)) bufferDates.add(p);
      }
    }
  }

  let awm = html.match(/id=["']allow-weekends["'][^>]*?value\s*=\s*["']([^"']*)["']|value\s*=\s*["']([^"']*)["'][^>]*?id=["']allow-weekends["']/);
  let allowWeekends = "1";
  if (awm) allowWeekends = (awm[1] !== undefined ? awm[1] : awm[2]) || "1";
  const weekendsBlocked = allowWeekends !== "1";

  function earliestAvailable(start, maxLookahead = 180) {
    if (!start) return null;
    let d = new Date(Date.UTC(start[0], start[1] - 1, start[2]));
    for (let i = 0; i < maxLookahead; i++) {
      const key = d.toISOString().slice(0, 10);
      if (bufferDates.has(key)) { d.setUTCDate(d.getUTCDate() + 1); continue; }
      const dow = d.getUTCDay();
      if (weekendsBlocked && (dow === 0 || dow === 6)) { d.setUTCDate(d.getUTCDate() + 1); continue; }
      return [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()];
    }
    return start;
  }

  let flexible = false, contractEnd = null, flexibleStart = null, flexibleEnd = null;
  const btnTagM = html.match(/<button[^>]*id=["']availNowBtn["'][^>]*>/);
  if (btnTagM) {
    const clsM = btnTagM[0].match(/class="([^"]*)"/);
    const btnLterms = new Set();
    if (clsM) {
      const re = /lterm(\w+)/g;
      let mm;
      while ((mm = re.exec(clsM[1]))) btnLterms.add(mm[1]);
    }
    if (["6", "12", "24", "22", "44"].some((k) => btnLterms.has(k))) flexible = true;
    const now0 = new Date();
    const todayC = [now0.getFullYear(), now0.getMonth() + 1, now0.getDate()];
    const idx = btnTagM.index;
    const seg = html.slice(Math.max(0, idx - 300), idx + btnTagM[0].length + 300);
    const endCandidates = [];
    for (const key of ["data-6m", "data-22w", "data-44w"]) {
      const dm = seg.match(new RegExp(key.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&") + '=["\']([\\d/]{4,10})["\']'));
      if (dm) {
        const parsed = parseDdMmYy(dm[1]);
        if (parsed && dnum(parsed) >= dnum(todayC)) endCandidates.push(parsed);
      }
    }
    if (endCandidates.length) contractEnd = endCandidates.reduce((a, b) => (dnum(a) <= dnum(b) ? a : b));
    if (flexible) {
      const fsM = html.match(/available-picker-start-date[^>]*?value\s*=\s*["'](\d{4}),(\d{1,2}),(\d{1,2})["']/);
      if (fsM) {
        flexibleStart = earliestAvailable([parseInt(fsM[1], 10), parseInt(fsM[2], 10), parseInt(fsM[3], 10)]);
      } else {
        const tm = new Date(); tm.setDate(tm.getDate() + 1);
        flexibleStart = earliestAvailable([tm.getFullYear(), tm.getMonth() + 1, tm.getDate()]);
      }
      const feM = html.match(/id=["']available-picker-date["'][^>]*?value\s*=\s*["'](\d{4}),(\d{1,2}),(\d{1,2})["']/);
      if (feM) flexibleEnd = [parseInt(feM[1], 10), parseInt(feM[2], 10), parseInt(feM[3], 10)];
    }
  } else {
    flexible = /Flexible\s+Start/i.test(html);
  }

  const clickableRe = /<(?:a|button|option|label)[^>]*?>\s*(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s*<\/(?:a|button|option|label)>/gi;
  let cm;
  while ((cm = clickableRe.exec(html))) {
    const month = MONTH_MAP[cm[2]];
    if (month) dates.push([parseInt(cm[3], 10), month, parseInt(cm[1], 10)]);
  }
  if (!dates.length) {
    const bs = html.match(/(?:start-date|move-in|contract-start|date-select|when would you like)/i);
    if (bs) {
      const start = Math.max(0, bs.index - 500);
      const end = Math.min(html.length, bs.index + bs[0].length + 3000);
      let sectionHtml = html.slice(start, end);
      sectionHtml = sectionHtml.replace(/e\.g\..*?(?=<)/gi, "");
      const dateRe = /(?:>|\s)(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})/g;
      let dm2;
      while ((dm2 = dateRe.exec(sectionHtml))) {
        const month = MONTH_MAP[dm2[2]];
        if (month) dates.push([parseInt(dm2[3], 10), month, parseInt(dm2[1], 10)]);
      }
    }
  }

  const seen = new Set();
  const unique = [];
  for (const d of dates) {
    const key = `${d[0]}-${d[1]}-${d[2]}`;
    if (!seen.has(key)) { seen.add(key); unique.push(d); }
  }
  unique.sort((a, b) => dnum(a) - dnum(b));

  let shortstayDates = [];
  const mdUl = html.match(/<ul[^>]*id=["']move-in-dates["'][^>]*>([\s\S]*?)<\/ul>/);
  let hasSsOption;
  if (mdUl) hasSsOption = /class="[^"]*\bltermSS\b/.test(mdUl[1]);
  else hasSsOption = /id=["']mnthSS["']/.test(html);
  if (hasSsOption) {
    const ssStartM = html.match(/available-shortstay-picker-start-date[^>]*?value\s*=\s*['"](\d{4}),(\d{1,2}),(\d{1,2})/);
    if (ssStartM) {
      shortstayDates.push(earliestAvailable([parseInt(ssStartM[1], 10), parseInt(ssStartM[2], 10), parseInt(ssStartM[3], 10)]));
    } else {
      const tm = new Date(); tm.setDate(tm.getDate() + 1);
      shortstayDates.push(earliestAvailable([tm.getFullYear(), tm.getMonth() + 1, tm.getDate()]));
    }
  }

  const now = new Date();
  const todayN = dnum([now.getFullYear(), now.getMonth() + 1, now.getDate()]);
  const uniqueFiltered = unique.filter((d) => dnum(d) >= todayN);
  shortstayDates = shortstayDates.filter((d) => dnum(d) >= todayN);
  if (contractEnd && dnum(contractEnd) < todayN) contractEnd = null;
  if (flexibleStart && dnum(flexibleStart) < todayN) flexibleStart = null;
  if (flexibleEnd && (dnum(flexibleEnd) < todayN || (flexibleStart && dnum(flexibleEnd) < dnum(flexibleStart)))) {
    flexible = false; flexibleStart = null; flexibleEnd = null;
  }
  if (flexibleEnd && dnum(flexibleEnd) < todayN) flexibleEnd = null;

  return {
    dates: uniqueFiltered,
    flexible,
    flexible_start: flexibleStart,
    flexible_end: flexibleEnd,
    contract_end: contractEnd,
    shortstay_dates: shortstayDates,
  };
}

function extractFeatures(html) {
  const features = {};
  const text = html.replace(/<[^>]+>/g, " ");
  const areaM = text.match(/(?:Approx\.?\s*)?(\d+\.?\d*)\s*m²/i);
  if (areaM) features.area = `${parseFloat(areaM[1])}m²`;
  if (/king\s*single/i.test(text)) features.bed = "King Single";
  else if (/queen\s*bed/i.test(text)) features.bed = "Queen";
  else if (/double\s*bed/i.test(text)) features.bed = "Double";
  else if (/king\s*bed/i.test(text)) features.bed = "King";
  return features;
}

function formatPrice(prices, key) {
  const val = prices[key];
  if (val === undefined || val === null) return "—";
  return `$${val.toLocaleString("en-US")}`;
}

function formatDates(dateDataIn) {
  const dates = Array.isArray(dateDataIn) ? dateDataIn : (dateDataIn?.dates || []);
  const flexible = Array.isArray(dateDataIn) ? false : !!dateDataIn?.flexible;
  if (!dates.length) return "灵活自选";
  const byYm = new Map();
  for (const [y, m, d] of dates) {
    const k = `${y}-${m}`;
    if (!byYm.has(k)) byYm.set(k, { y, m, days: [] });
    byYm.get(k).days.push(d);
  }
  const sortedKeys = [...byYm.keys()].sort((a, b) => {
    const [ay, am] = a.split("-").map(Number), [by, bm] = b.split("-").map(Number);
    return ay - by || am - bm;
  });
  const parts = [];
  for (const k of sortedKeys) {
    const { y, m, days } = byYm.get(k);
    days.sort((a, b) => a - b);
    const ranges = [];
    let s = days[0], e = days[0];
    for (let i = 1; i < days.length; i++) {
      const d = days[i];
      if (d === e + 1) e = d; else { ranges.push([s, e]); s = e = d; }
    }
    ranges.push([s, e]);
    const dayStrs = ranges.map(([a, b]) => (a === b ? `${a}日` : `${a}-${b}日`));
    parts.push(`${y}年${m}月${dayStrs.join("、")}`);
  }
  const dateStr = parts.join("、");
  if (flexible && dates.length) return `灵活自选 + ${dateStr}`;
  return dateStr;
}

function groupByMonth(ds) {
  const byM = new Map();
  for (const [, m, d] of ds) { if (!byM.has(m)) byM.set(m, []); byM.get(m).push(d); }
  const parts = [];
  for (const m of [...byM.keys()].sort((a, b) => a - b)) {
    const days = byM.get(m).sort((a, b) => a - b);
    const segs = [[days[0], days[0]]];
    for (let i = 1; i < days.length; i++) {
      const d = days[i];
      if (d === segs[segs.length - 1][1] + 1) segs[segs.length - 1][1] = d;
      else segs.push([d, d]);
    }
    const segTxt = segs.map(([a, b]) => (a === b ? `${a}日` : `${a}-${b}日`));
    parts.push(`${m}月${segTxt.join("、")}`);
  }
  return parts.join("、");
}

function flexTextOf(flexibleStart, flexibleEnd) {
  if (!flexibleStart) return null;
  let s = `${flexibleStart[0]}年${flexibleStart[1]}月${flexibleStart[2]}日`;
  if (flexibleEnd && dnum(flexibleEnd) > dnum(flexibleStart) && flexibleEnd[1] !== flexibleStart[1]) {
    if (flexibleEnd[0] === flexibleStart[0]) s += `~${flexibleEnd[1]}月${flexibleEnd[2]}日`;
    else s += `~${flexibleEnd[0]}年${flexibleEnd[1]}月${flexibleEnd[2]}日`;
  }
  return s;
}

function flexFullOf(flexibleStart, flexibleEnd, contractEnd) {
  const ft = flexTextOf(flexibleStart, flexibleEnd);
  if (!ft) return null;
  if (contractEnd) return `${ft} 起（合同至 ${contractEnd[0]}年${contractEnd[1]}月${contractEnd[2]}日）`;
  return `${ft} 起`;
}

function formatStartLabel(availStatus, dateDataIn) {
  const dateData = dateDataIn && typeof dateDataIn === "object" ? dateDataIn : {};
  const dates = dateData.dates || [];
  const flexible = !!dateData.flexible;
  const ssDates = dateData.shortstay_dates || [];
  const flexibleStart = dateData.flexible_start;
  const flexibleEnd = dateData.flexible_end;
  const contractEnd = dateData.contract_end;
  const thisYear = new Date().getFullYear();
  const thisDates = dates.filter((d) => d[0] === thisYear).sort((a, b) => dnum(a) - dnum(b));
  const futureDates = dates.filter((d) => d[0] > thisYear).sort((a, b) => dnum(a) - dnum(b));
  const ssThis = ssDates.filter((d) => d[0] === thisYear).sort((a, b) => dnum(a) - dnum(b));
  const fsThis = !!(flexibleStart && flexibleStart[0] === thisYear);
  const full = (ds) => formatDates({ dates: ds, flexible: false });

  if (thisDates.length || ssThis.length || fsThis) {
    const parts = [];
    if (ssThis.length) parts.push("短租 " + groupByMonth(ssThis) + " 起");
    if (thisDates.length) parts.push("固定起租 " + groupByMonth(thisDates) + " 起");
    if (flexible && flexibleStart) parts.push("长租灵活 " + flexFullOf(flexibleStart, flexibleEnd, contractEnd));
    if (futureDates.length) {
      if (thisDates.length || (flexible && flexibleStart)) parts.push("长租亦可 " + full(futureDates));
      else parts.push("长租 " + full(futureDates));
    }
    return "今年可订：" + parts.join("；");
  }
  if (futureDates.length) return "今年已无房：" + full(futureDates);
  if (flexible) {
    if (flexibleStart) return "今年已无房：长租灵活 " + flexFullOf(flexibleStart, flexibleEnd, contractEnd);
    return "灵活自选";
  }
  if (ssDates.length) return "今年可订：短租 " + full(ssDates) + " 起";
  if (availStatus === "waitlist") return "今年无房（等位）";
  return "待定";
}

function buildDateCell(room) {
  const dateData = room.date_data || {};
  const avail = room.avail_status;
  if (avail === "soldout") return '<span class="tag tag-off tag-mini">已售罄</span>';
  if (avail === "waitlist") return '<span class="tag tag-bad tag-mini">等位无房</span>';
  if (avail === "unknown") return '<span class="tag tag-off tag-mini">未知</span>';

  const dates = dateData.dates || [];
  const flexible = !!dateData.flexible;
  const ssDates = dateData.shortstay_dates || [];
  const flexibleStart = dateData.flexible_start;
  const flexibleEnd = dateData.flexible_end;
  const contractEnd = dateData.contract_end;
  const thisYear = new Date().getFullYear();
  const fmt = (ds) => formatDates({ dates: ds, flexible: false });

  const thisDates = dates.filter((d) => d[0] === thisYear);
  const futureDates = dates.filter((d) => d[0] > thisYear);
  const ssThis = ssDates.filter((d) => d[0] === thisYear);
  const fsThis = !!(flexibleStart && flexibleStart[0] === thisYear);

  if (thisDates.length || ssThis.length || fsThis) {
    const parts = [];
    if (ssThis.length) parts.push(`短租 ${groupByMonth(ssThis)} 起`);
    if (thisDates.length) parts.push(`固定起租 ${groupByMonth(thisDates)} 起`);
    if (flexible && flexibleStart) parts.push(`长租灵活 ${flexFullOf(flexibleStart, flexibleEnd, contractEnd)}`);
    if (futureDates.length) {
      if (thisDates.length || (flexible && flexibleStart)) parts.push(`长租亦可 ${fmt(futureDates)}`);
      else parts.push(`长租 ${fmt(futureDates)}`);
    }
    return `<span class="tag tag-ok tag-mini">今年可订</span> <span class="date-detail">${parts.join("；")}</span>`;
  }
  if (futureDates.length) return `<span class="tag tag-off tag-mini">今年无房</span> <span class="date-detail">${fmt(futureDates)} 起</span>`;
  if (flexible) {
    if (flexibleStart) return `<span class="tag tag-off tag-mini">今年无房</span> <span class="date-detail">长租灵活 ${flexFullOf(flexibleStart, flexibleEnd, contractEnd)}</span>`;
    return '<span class="tag tag-ok tag-mini">今年可订</span> <span class="date-detail">灵活自选</span>';
  }
  if (ssDates.length) return `<span class="tag tag-ok tag-mini">今年可订</span> <span class="date-detail">短租 ${fmt(ssDates)} 起</span>`;
  return '<span class="tag tag-off tag-mini">待定</span>';
}

function availInfo(status, count) {
  if (status === "available") return ["row-ok", `<span class="tag tag-ok">${count ? count + "间" : "有房"}</span>`];
  if (status === "limited") return ["row-warn", `<span class="tag tag-warn">${count ? "仅剩" + count + "间" : "紧张"}</span>`];
  if (status === "waitlist") return ["row-bad", '<span class="tag tag-bad">等位</span>'];
  if (status === "soldout") return ["row-off", '<span class="tag tag-off">售罄</span>'];
  return ["row-off", '<span class="tag tag-off">未知</span>'];
}

function buildRoomRow(room) {
  const p = room.prices || {};
  const [rowCls, statusHtml] = availInfo(room.avail_status, room.avail_count);
  const noteHtml = room.note ? `<span class="room-note">${room.note}</span>` : "";
  return `<tr class="${rowCls}">` +
    `<td><span class="room-name">${room.name}</span>${noteHtml}</td>` +
    `<td>${room.area}</td>` +
    `<td>${room.bed}</td>` +
    `<td><span class="price">${formatPrice(p, "12月")}</span></td>` +
    `<td><span class="price">${formatPrice(p, "44周")}</span></td>` +
    `<td><span class="price">${formatPrice(p, "22周")}</span></td>` +
    `<td><span class="price">${formatPrice(p, "短租")}</span></td>` +
    `<td>${statusHtml}</td>` +
    `<td>${buildDateCell(room)}</td>` +
    `</tr>`;
}

function roomSortKey(room) {
  const availRank = { available: 0, limited: 1, waitlist: 2, soldout: 3 }[room.avail_status] ?? 4;
  const dateData = room.date_data || {};
  const dates = dateData.dates || [];
  const flexible = !!dateData.flexible;
  const ssDates = dateData.shortstay_dates || [];
  const thisYear = new Date().getFullYear();
  const ssThis = ssDates.some((d) => d[0] === thisYear);
  let dateRank;
  if (flexible || dates.some((d) => d[0] === thisYear) || ssThis) dateRank = 0;
  else if (dates.length || ssDates.length) dateRank = 1;
  else dateRank = 2;
  return [availRank, dateRank, room.name];
}

function buildPropPanel(prop, isFirst) {
  const rooms = [...prop.rooms].sort((a, b) => {
    const ka = roomSortKey(a), kb = roomSortKey(b);
    if (ka[0] !== kb[0]) return ka[0] - kb[0];
    if (ka[1] !== kb[1]) return ka[1] - kb[1];
    return ka[2] < kb[2] ? -1 : ka[2] > kb[2] ? 1 : 0;
  });
  const thead = "<th>房型</th><th>面积</th><th>床型</th><th>12/24月</th><th>44周</th><th>22周</th><th>短租</th><th>库存</th><th>起租日期</th>";
  let comingSoonHtml = "";
  if (!rooms.length) {
    if (COMING_SOON.has(prop.slug)) {
      comingSoonHtml = '<div class="coming-soon"><div class="cs-badge">🚧 即将开业</div><p class="cs-title">Iglu Mascot Duo</p>' +
        '<p class="cs-text">预计 <b>2027 年 1 月</b> 开业，官网目前为招租登记阶段，尚未公布可预订房型与价格。<br>房型上线后本页将自动同步真实房态。</p></div>';
    } else {
      comingSoonHtml = '<div class="coming-soon"><p class="cs-text">暂无房型数据</p></div>';
    }
  }
  return `<div class="prop-panel${isFirst ? " active" : ""}" id="prop-${prop.slug}">
<div class="table-wrap"><table>
<thead><tr>${thead}</tr></thead>
<tbody>${rooms.map(buildRoomRow).join("")}</tbody>
</table></div>${comingSoonHtml}
</div>`;
}

function buildCityBlock(citySlug, cityData) {
  const props = cityData.properties;
  const roomResults = cityData.room_results || {};
  const navButtons = [];
  const panels = [];
  let i = 0;
  for (const [name, slug] of Object.entries(props)) {
    const active = i === 0 ? " active" : "";
    const badge = COMING_SOON.has(slug) ? "即将" : String((roomResults[slug] || []).length);
    navButtons.push(`<button class="prop-btn${active}" id="prop-btn-${slug}" onclick="switchProp('${citySlug}','${slug}')">${name}<span class="count">${badge}</span></button>`);
    panels.push(buildPropPanel({ name, slug, rooms: roomResults[slug] || [] }, i === 0));
    i++;
  }
  return `<div class="city-block" data-city="${citySlug}">
<nav class="prop-nav fade-in" style="animation-delay:80ms" id="prop-nav-${citySlug}">${navButtons.join("")}</nav>
${panels.join("")}
</div>`;
}

function buildHtml(allCities, template) {
  const now = bjNow();
  const updateTime = `${now.getUTCFullYear()}年${pad(now.getUTCMonth() + 1)}月${pad(now.getUTCDate())}日 ${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}`;
  const updateBadge = `${pad(now.getUTCMonth() + 1)}/${pad(now.getUTCDate())} ${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())} 更新`;
  const summaryParts = Object.entries(allCities).map(([, d]) => `${d.label} ${Object.keys(d.properties).length} 所`);
  const citySummary = "📍 " + summaryParts.join(" · ") + " Iglu 公寓";
  const cityBlocks = Object.entries(allCities).map(([slug, data]) => buildCityBlock(slug, data)).join("\n");
  return template
    .replaceAll("{{UPDATE_TIME}}", updateTime)
    .replaceAll("{{UPDATE_BADGE}}", updateBadge)
    .replaceAll("{{CITY_SUMMARY}}", citySummary)
    .replaceAll("{{CITY_BLOCKS}}", cityBlocks);
}

async function mapConcurrent(items, limit, fn) {
  const results = new Array(items.length);
  let idx = 0;
  async function worker() {
    for (;;) {
      const i = idx++;
      if (i >= items.length) return;
      results[i] = await fn(items[i], i);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

async function scrapeRoom(city, propertySlug, roomSlug, roomMeta) {
  const url = `https://iglu.com.au/rooms/${city}/${propertySlug}/${roomSlug}/`;
  let html;
  try {
    html = await fetchPage(url);
  } catch (e) {
    return { error: String(e?.message || e), url, slug: roomSlug };
  }
  const prices = extractPrices(html);
  const dateData = extractDates(html);
  const [availStatus, availCount, availText] = extractAvailability(html, dateData);
  const features = extractFeatures(html);
  const meta = roomMeta[roomSlug] || [roomSlug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()), "Unknown", "?", "?", ""];
  return {
    slug: roomSlug, url,
    name: meta[0], type: meta[1],
    area: features.area || meta[2],
    bed: features.bed || meta[3],
    note: meta[4] || "",
    prices, avail_status: availStatus, avail_count: availCount, avail_text: availText,
    date_data: dateData,
    date_str: DATE_OVERRIDES[meta[0]] || formatStartLabel(availStatus, dateData),
  };
}

async function scrapeProperty(city, name, slug, roomMeta, propertyRooms) {
  const roomSlugs = propertyRooms[slug] || [];
  console.log(`  📍 ${city} · ${name} (${slug}) — ${roomSlugs.length} 个房型`);
  const rawResults = await mapConcurrent(roomSlugs, MAX_WORKERS, (rs) => scrapeRoom(city, slug, rs, roomMeta));
  const rooms = [];
  const errors = [];
  rawResults.forEach((result, i) => {
    if (!result.error) {
      rooms.push(result);
    } else {
      console.log(`     ❌ ${roomSlugs[i]}: ${result.error}`);
      errors.push(`${slug}/${roomSlugs[i]}: ${result.error}`);
    }
  });
  const typeRank = Object.fromEntries(TYPE_ORDER.map((t, i) => [t, i]));
  rooms.sort((a, b) => {
    const ra = typeRank[a.type] ?? 99, rb = typeRank[b.type] ?? 99;
    if (ra !== rb) return ra - rb;
    return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
  });
  console.log(`     ✅ ${rooms.length}/${roomSlugs.length} 房型抓取成功`);
  return { name, slug, rooms, errors };
}

// ── 变化检测 & 企微推送 ──
function buildSnapshot(allCities) {
  const snap = {};
  for (const [city, cityData] of Object.entries(allCities)) {
    for (const [propSlug, rooms] of Object.entries(cityData.room_results)) {
      for (const r of rooms) {
        snap[`${city}/${propSlug}/${r.slug || ""}`] = {
          prices: r.prices || {}, avail: r.avail_status || "", count: r.avail_count ?? "", date: r.date_str || "",
        };
      }
    }
  }
  return snap;
}

function diffSnapshot(oldSnap, newSnap) {
  const changes = [];
  for (const [key, cur] of Object.entries(newSnap)) {
    const prev = oldSnap[key];
    if (prev === undefined) continue;
    for (const field of ["prices", "avail", "count", "date"]) {
      if (JSON.stringify(prev[field]) !== JSON.stringify(cur[field])) {
        changes.push([key, field, prev[field], cur[field]]);
      }
    }
  }
  return changes;
}

function formatChanges(changes, allCities) {
  const propLabel = {};
  for (const [city, cityData] of Object.entries(allCities)) {
    for (const [name, slug] of Object.entries(cityData.properties)) propLabel[`${city}/${slug}`] = name;
  }
  const roomLabel = {};
  for (const [city, cityData] of Object.entries(allCities)) {
    for (const [propSlug, rooms] of Object.entries(cityData.room_results)) {
      for (const r of rooms) roomLabel[`${city}/${propSlug}/${r.slug || ""}`] = r.name || r.slug || "";
    }
  }
  const groups = new Map();
  for (const [key, field, oldv, newv] of changes) {
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push([field, oldv, newv]);
  }
  const lines = [];
  for (const [key, items] of groups) {
    const [city, propSlug, roomSlug] = key.split("/");
    const name = roomLabel[key] || roomSlug;
    const pname = propLabel[`${city}/${propSlug}`] || propSlug;
    lines.push(`**${pname} · ${name}**`);
    for (const [field, oldv, newv] of items) {
      if (field === "prices") {
        const fmtPrice = (p) => {
          if (!p || typeof p !== "object") return "—";
          const vals = Object.values(p).filter(Boolean).map(String);
          return vals.length ? "$" + vals.join("/") : "—";
        };
        lines.push(`> 价格: ${fmtPrice(oldv)} → ${fmtPrice(newv)}`);
      } else if (field === "avail") {
        lines.push(`> 库存: ${oldv || "?"} → ${newv || "?"}`);
      } else if (field === "count") {
        lines.push(`> 余量: ${oldv || "-"} → ${newv || "-"}`);
      } else if (field === "date") {
        lines.push(`> 起租: ${oldv || "—"} → ${newv || "—"}`);
      }
    }
    lines.push("");
  }
  let text = lines.join("\n").trim();
  if (text.length > 3500) text = text.slice(0, 3500) + "\n... (更多变化请查看页面)";
  return text;
}

async function notifyWecom(text, mentionAll = false) {
  if (!WECOM_WEBHOOK) { console.log("  ℹ️  未配置 WECOM_WEBHOOK，跳过推送"); return; }
  try {
    const resp = await fetch(WECOM_WEBHOOK, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ msgtype: "markdown", markdown: { content: text } }),
      signal: AbortSignal.timeout(10000),
    });
    console.log(`  📨 企微推送: ${(await resp.text()).slice(0, 120)}`);
  } catch (e) {
    console.log(`  ❌ 企微推送失败: ${e?.message || e}`);
    return;
  }
  if (mentionAll) {
    try {
      await fetch(WECOM_WEBHOOK, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ msgtype: "text", text: { content: "Iglu 房态有变化，详见上方消息", mentioned_list: ["@all"] } }),
        signal: AbortSignal.timeout(10000),
      });
    } catch (e) {
      console.log(`  ❌ @全体成员推送失败: ${e?.message || e}`);
    }
  }
}

// ── 对外入口：抓取 + 渲染 + 写入 DATA_DIR（供 server.mjs 定时调用）──
export async function runScrape({ dataDir, templatePath, publicSite }) {
  const startedAt = Date.now();
  console.log(`🔄 Iglu 房态抓取开始 — ${new Date().toISOString()}`);
  const template = await readFile(templatePath, "utf8");

  const allCities = {};
  let totalProps = 0, totalRooms = 0;
  const errorSamples = [];
  await openBrowser();
  try {
    for (const [citySlug, cityCfg] of Object.entries(CITIES)) {
      console.log(`🏙️  ${citySlug.toUpperCase()} (${cityCfg.label})`);
      const roomResults = {};
      for (const [propName, propSlug] of Object.entries(cityCfg.properties)) {
        const propData = await scrapeProperty(citySlug, propName, propSlug, cityCfg.room_meta, cityCfg.property_rooms);
        roomResults[propSlug] = propData.rooms;
        totalProps++;
        totalRooms += propData.rooms.length;
        if (propData.errors?.length && errorSamples.length < 5) errorSamples.push(...propData.errors.slice(0, 5 - errorSamples.length));
      }
      allCities[citySlug] = { label: cityCfg.label, properties: cityCfg.properties, room_results: roomResults };
    }
  } finally {
    await closeBrowser();
  }
  console.log(`📊 共 ${totalProps} 楼盘, ${totalRooms} 个房型`);

  await mkdir(dataDir, { recursive: true });
  const snapshotPath = path.join(dataDir, "snapshot.json");
  let oldSnap = {};
  try { oldSnap = JSON.parse(await readFile(snapshotPath, "utf8")); } catch { /* 首次运行没有快照 */ }
  const newSnap = buildSnapshot(allCities);
  const prevTotal = Object.keys(oldSnap).length;

  // 熔断：房型总数比上次骤降，大概率是抓取本身失败（网络问题/官网改版），不是真的全下架。
  // 首次运行（没有旧快照）也要单独兜底：totalRooms===0 不该被 prevTotal>0 的判断放过。
  const scrapeLooksBroken = totalRooms === 0 || (prevTotal > 0 && totalRooms < prevTotal * 0.5);
  if (scrapeLooksBroken) {
    console.log(`⚠️  抓取结果异常：房型数从 ${prevTotal} 骤降到 ${totalRooms}，跳过本次更新，保留旧数据`);
    await notifyWecom(
      `**⚠️ Iglu 抓取异常，已跳过本次更新**（${bjTimeStr()}）\n\n房型数从 ${prevTotal} 骤降到 ${totalRooms}，疑似网络问题或官网改版，线上数据未被覆盖。\n\n[查看实时房态](${publicSite})`
    );
    return { ok: false, reason: "scrape-looks-broken", totalRooms, prevTotal, errorSamples };
  }

  const html = buildHtml(allCities, template);
  const pagePath = path.join(dataDir, "cache.html");
  const tmpPage = `${pagePath}.tmp-${process.pid}`;
  await writeFile(tmpPage, html, "utf8");
  await rename(tmpPage, pagePath);

  const changes = diffSnapshot(oldSnap, newSnap);
  const changedCount = new Set(changes.map((c) => c[0])).size;

  const tmpSnap = `${snapshotPath}.tmp-${process.pid}`;
  await writeFile(tmpSnap, JSON.stringify(newSnap, null, 1), "utf8");
  await rename(tmpSnap, snapshotPath);

  if (changes.length) {
    const msg = formatChanges(changes, allCities);
    await notifyWecom(`**📢 Iglu 房态变化** (${bjTimeStr()})\n\n${msg}\n\n[查看实时房态](${publicSite})`, true);
  }

  const elapsedSec = Math.round((Date.now() - startedAt) / 1000);
  console.log(`✅ 完成，用时 ${elapsedSec}s，${changedCount} 个房型有变化`);
  return { ok: true, totalRooms, totalProps, changedCount, elapsedSec, errorSamples };
}
