// -*- coding: utf-8 -*-
// Iglu 澳洲房态 · uhouzz 容器版（自包含，零 Cloudflare 依赖）
// 架构：public/index.html 为烤入的数据快照，正常访问零外部依赖；
// 数据更新：GitHub Actions 爬虫（iglu-sydney-fangtai 仓库）抓取 iglu.com.au 后，
// 经公司部署网关整体重新部署本容器，快照随部署刷新（服务端按 mtime 热加载，无需重启）。
// 申请直链（agent A1336）：容器出网被墙，直连 iglu.com.au 必然失败，
// 「申请」按钮直接跳转 pages.dev 的海外 Pages Function 代理（自动登录 A1336）。
// /iglu/* 容器内代理保留为兜底，连不上时降级为提示页 + 直链。
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT) || 80;
const PAGE_PATH = path.join(__dirname, "public", "index.html");
const STALE_MS = 3 * 60 * 60 * 1000; // 爬虫整点抓取，数据时间超过 3 小时视为待更新

const IGLU_ORIGIN = "https://iglu.com.au";
const AGENT_CODE = "A1336";
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
const PROXY_TIMEOUT_MS = 30_000;
// 容器在国内连不上 iglu.com.au，申请代理只能借道海外的 pages.dev Pages Function
const APPLY_PROXY_URL = "https://iglu-centralpark.pages.dev/iglu/apply-online/";

const REBRAND = [
  [/#FF5A1F/g, "#E04047"],
  [/#FF7A45/g, "#EA6E72"],
  [/rgba\(255,\s*90,\s*31/gi, "rgba(224,64,71"],
];

const HIDE_BADGE_STYLE = "<style>.uhomes-badge,.watermark{display:none!important}</style>";

// 快照缓存：部署替换 index.html 后按 mtime 自动重载
let pageCache = { mtimeMs: 0, html: "" };

async function loadPage() {
  const st = await fs.stat(PAGE_PATH);
  if (pageCache.html && st.mtimeMs === pageCache.mtimeMs) return pageCache.html;
  const html = await fs.readFile(PAGE_PATH, "utf8");
  pageCache = { mtimeMs: st.mtimeMs, html };
  return html;
}

function rebrand(html) {
  return REBRAND.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), html);
}

// 快照页自带的数据时间（爬虫按北京时间写入）
function dataTimeOf(html) {
  const m = html.match(/更新于\s*(\d{4})年(\d{2})月(\d{2})日\s*(\d{2}):(\d{2})/);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : null;
}

function isFresh(dataTime) {
  if (!dataTime) return false;
  return Date.now() - Date.parse(`${dataTime.replace(" ", "T")}:00+08:00`) < STALE_MS;
}

function syncChip(dataTime) {
  const fresh = isFresh(dataTime);
  const timeStr = dataTime || "内置快照";
  const statusText = dataTime ? (fresh ? "每小时自动抓取" : "数据待更新") : "离线快照模式";
  const dotColor = fresh ? "#22c55e" : "#f59e0b";
  const brandColor = "#E04047";
  return `
    <div style="position:fixed;left:16px;bottom:16px;z-index:99999;background:rgba(255,255,255,.96);border:1px solid #f0ebea;border-radius:14px;padding:10px 14px;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.08);backdrop-filter:blur(8px);min-width:180px;">
      <div style="display:flex;align-items:center;gap:7px;margin-bottom:4px;">
        <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${dotColor};box-shadow:0 0 0 3px ${dotColor}22;"></span>
        <span style="font-size:11px;font-weight:600;color:${brandColor};letter-spacing:.04em;">最新更新</span>
      </div>
      <div style="font-size:14px;font-weight:600;color:#1f2937;line-height:1.3;">${timeStr}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:3px;">${statusText}</div>
    </div>`;
}

function decorate(html, dataTime) {
  return rebrand(html)
    .replace("</head>", `${HIDE_BADGE_STYLE}</head>`)
    .replace(`'/iglu/apply-online/?p='`, `'${APPLY_PROXY_URL}?p='`)
    .replace("</body>", `${syncChip(dataTime)}</body>`);
}

async function serveHtml() {
  const base = await loadPage();
  return decorate(base, dataTimeOf(base));
}

// ---------- 经纪人代理（移植自 Cloudflare Pages Function） ----------
let cachedCookie = null;
let cookieExpiry = 0;

function extractSetCookies(headers) {
  if (headers.getSetCookie) {
    const sc = headers.getSetCookie();
    if (sc && sc.length) return sc;
  }
  const raw = headers.get("set-cookie");
  if (raw) return raw.split(/,\s*(?=[a-zA-Z_]+=)/);
  return [];
}

async function getSessionCookie() {
  if (cachedCookie && Date.now() < cookieExpiry) return cachedCookie;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROXY_TIMEOUT_MS);
  try {
    const resp = await fetch(`${IGLU_ORIGIN}/wp-admin/admin-ajax.php`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": IGLU_ORIGIN,
        "Referer": `${IGLU_ORIGIN}/iglu-agent-portal-login/`,
        "User-Agent": UA,
      },
      body: `action=agent_code_action&code=${AGENT_CODE}`,
      redirect: "manual",
      signal: controller.signal,
    });
    const allCookies = [];
    for (const sc of extractSetCookies(resp.headers)) allCookies.push(sc.split(";")[0]);
    if (resp.status >= 300 && resp.status < 400) {
      const loc = resp.headers.get("Location");
      if (loc) {
        const redirectUrl = loc.startsWith("http") ? loc : IGLU_ORIGIN + loc;
        const resp2 = await fetch(redirectUrl, {
          headers: {
            "Cookie": allCookies.join("; "),
            "User-Agent": UA,
            "Referer": `${IGLU_ORIGIN}/iglu-agent-portal-login/`,
          },
          redirect: "manual",
          signal: controller.signal,
        });
        for (const s of extractSetCookies(resp2.headers)) allCookies.push(s.split(";")[0]);
      }
    }
    if (allCookies.length > 0) {
      cachedCookie = allCookies.join("; ");
      cookieExpiry = Date.now() + 5 * 60 * 1000;
      return cachedCookie;
    }
    return "";
  } catch (e) {
    console.error("Agent login failed:", e?.message ?? e);
    return "";
  } finally {
    clearTimeout(timer);
  }
}

function proxyInterceptorScript() {
  // 代理基址由浏览器端从当前 URL 推导（容器在子路径下，服务端不知道公共前缀）
  return `<script>
(function(){
  var idx = location.pathname.indexOf('/iglu/');
  var P = location.origin + (idx >= 0 ? location.pathname.substring(0, idx + 6) : '/iglu/');
  function rw(u){
    if(!u||typeof u!=='string')return u;
    if(u.indexOf(P)===0)return u;
    if(u.indexOf('iglu.com.au')>=0){try{var x=new URL(u);return P+x.pathname.substring(6)+x.search+x.hash;}catch(e){}}
    if(u[0]==='/'&&u.indexOf('/iglu/')!==0)return P+u.substring(1);
    if(u.indexOf(location.origin)===0){try{var y=new URL(u);if(y.pathname.indexOf('/iglu/')!==0)return P+y.pathname.substring(1)+y.search+y.hash;}catch(e){}}
    return u;
  }
  var oo=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(m,u){return oo.call(this,m,rw(u));};
  var of=window.fetch;
  if(of)window.fetch=function(i,o){if(typeof i==='string')i=rw(i);else if(i instanceof Request)i=new Request(rw(i.url),i);return of.call(window,i,o);};
  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('form').forEach(function(f){var a=f.getAttribute('action');if(a)f.setAttribute('action',rw(a));});
    document.querySelectorAll('a[href]').forEach(function(a){var h=a.getAttribute('href');if(h&&(h[0]==='/'||h.indexOf('iglu.com.au')>=0||h.indexOf(location.origin)===0))a.setAttribute('href',rw(h));});
  });
})();
</script>`;
}

function proxyFallbackPage(targetPath) {
  const direct = IGLU_ORIGIN + targetPath;
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>经纪人通道暂时不可用</title>
<style>body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#FAF6F5;color:#1f2937;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:24px;box-sizing:border-box}
.card{max-width:480px;background:#fff;border:1px solid #f0d9d7;border-radius:16px;padding:32px;box-shadow:0 8px 30px rgba(0,0,0,.06)}
h1{font-size:19px;margin:0 0 10px;color:#E04047}p{font-size:14px;line-height:1.7;color:#4b5563;margin:0 0 8px}
a.btn{display:inline-block;margin-top:14px;padding:12px 22px;background:#E04047;color:#fff;border-radius:10px;text-decoration:none;font-size:14px;font-weight:600}
a.btn:hover{background:#c93a41}code{background:#f5f5f4;padding:2px 6px;border-radius:5px;font-size:12px}</style></head>
<body><div class="card"><h1>⚠️ 经纪人代理通道暂时不可用</h1>
<p>容器到 iglu.com.au 的连接失败，申请直链暂时无法带经纪人身份（A1336）打开。</p>
<p>你可以先直接打开官网页面（不计入经纪人渠道）：</p>
<a class="btn" href="${direct}" target="_blank" rel="noopener">直接打开 iglu.com.au</a>
<p style="margin-top:14px;font-size:12px;color:#9ca3af">目标路径：<code>${targetPath}</code></p>
</div></body></html>`;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

async function handleIgluProxy(req, res, url) {
  const rest = url.pathname.split("/iglu/")[1] ?? "";
  const targetPath = "/" + rest + (url.search || "");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROXY_TIMEOUT_MS);
  try {
    const cookie = await getSessionCookie();
    const headers = {
      "Cookie": cookie,
      "Referer": `${IGLU_ORIGIN}/iglu-agent-portal-login/`,
      "User-Agent": UA,
    };
    for (const h of ["Accept", "Accept-Language", "Content-Type"]) {
      const v = req.headers[h.toLowerCase()];
      if (v) headers[h] = v;
    }
    let targetUrl = IGLU_ORIGIN + targetPath;
    let resp = null;
    const hasBody = req.method !== "GET" && req.method !== "HEAD";
    const reqBody = hasBody ? await readBody(req) : undefined;
    // 服务端手动跟随重定向，避免子路径下 Location 前缀问题
    for (let hop = 0; hop < 5; hop += 1) {
      const init = {method: req.method, headers, redirect: "manual", signal: controller.signal};
      if (hasBody) init.body = reqBody;
      resp = await fetch(targetUrl, init);
      if (resp.status >= 300 && resp.status < 400) {
        const loc = resp.headers.get("Location");
        if (!loc) break;
        targetUrl = loc.startsWith("http") ? loc : new URL(loc, targetUrl).toString();
        continue;
      }
      break;
    }
    if (!resp) throw new Error("无响应");
    clearTimeout(timer);
    const contentType = resp.headers.get("content-type") || "";
    if (contentType.includes("text/html")) {
      let html = await resp.text();
      html = html.replace(/<head([^>]*)>/i, `<head$1><base href="${IGLU_ORIGIN}/">`);
      html = html.replace("</head>", proxyInterceptorScript() + "</head>");
      res.writeHead(resp.status, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"});
      return res.end(html);
    }
    const passthrough = {};
    for (const [k, v] of resp.headers.entries()) {
      if (!["content-encoding", "content-length", "transfer-encoding", "set-cookie"].includes(k)) passthrough[k] = v;
    }
    passthrough["Cache-Control"] = "no-store";
    res.writeHead(resp.status, passthrough);
    const buffer = Buffer.from(await resp.arrayBuffer());
    return res.end(buffer);
  } catch (e) {
    clearTimeout(timer);
    const message = e?.name === "AbortError" ? "连接超时" : (e?.message || String(e));
    console.error(`iglu proxy error ${targetPath}:`, message);
    res.writeHead(200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"});
    return res.end(proxyFallbackPage(targetPath));
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  try {
    if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/index.html")) {
      const html = await serveHtml();
      res.writeHead(200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"});
      res.end(html);
      return;
    }
    if (url.pathname.startsWith("/iglu/") || url.pathname === "/iglu") {
      return handleIgluProxy(req, res, url);
    }
    if (req.method === "GET" && url.pathname === "/api/status") {
      const base = await loadPage();
      const dataTime = dataTimeOf(base);
      res.writeHead(200, {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"});
      res.end(JSON.stringify({
        mode: "baked-snapshot",
        dataTime,
        fresh: isFresh(dataTime),
      }));
      return;
    }
    if (url.pathname === "/favicon.ico") {
      res.writeHead(204);
      res.end();
      return;
    }
    res.writeHead(404, {"Content-Type": "text/plain; charset=utf-8"});
    res.end("not found");
  } catch (error) {
    res.writeHead(500, {"Content-Type": "text/plain; charset=utf-8"});
    res.end(`server error: ${error instanceof Error ? error.message : "unknown"}`);
  }
});

server.listen(PORT, () => {
  console.log(`iglu-rate-desk listening on :${PORT}`);
  loadPage()
    .then((html) => console.log(`快照已加载（${Math.round(html.length / 1024)}KB，数据时间 ${dataTimeOf(html) ?? "未知"}）`))
    .catch((error) => console.error("快照加载失败:", error?.message ?? error));
});
