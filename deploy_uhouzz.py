#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署到公司内部容器平台（app.uhomes.com），替代原 Cloudflare Pages 部署。
本地或 GitHub Actions 通用；口令从环境变量 DEPLOY_KEY（Actions 里对应 secret UHOUZZ_DEPLOY_KEY）
或 ~/.uhouzz-deploy/key 读取。
用法: python3 deploy_uhouzz.py --dir ./container --name iglu-rate-desk
"""
import os
import sys
import json
import base64
import argparse
import fnmatch
import urllib.request
import urllib.error

GATEWAY = os.environ.get("GATEWAY_URL", "https://app.uhomes.com/gateway").rstrip("/")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".wrangler"}
TEXT_EXT = {".html", ".htm", ".css", ".js", ".mjs", ".json", ".txt", ".md", ".py",
            ".yaml", ".yml", ".toml", ".sh", ".conf", ".ini", ".xml", ".svg",
            ".dockerignore", ".gitignore"}
SECRET_GLOBS = [".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", ".npmrc", ".netrc",
                "id_rsa*", "id_ed25519*", "credentials", "credentials.json", "*.secret"]
MAX_FILE = 2 * 1024 * 1024


def load_key():
    k = os.environ.get("DEPLOY_KEY", "").strip()
    if k:
        return k
    try:
        with open(os.path.expanduser("~/.uhouzz-deploy/key"), encoding="utf-8-sig") as f:
            return f.read().strip()
    except OSError:
        return ""


def is_secret(fn):
    low = fn.lower()
    if any(fnmatch.fnmatch(low, p) for p in ("*.example", "*.sample", "*.template")):
        return False
    return any(fnmatch.fnmatch(low, g) for g in SECRET_GLOBS)


def collect(root):
    files = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn == ".DS_Store" or is_secret(fn):
                continue
            rel = os.path.relpath(os.path.join(dp, fn), root).replace("\\", "/")
            full = os.path.join(dp, fn)
            if os.path.getsize(full) > MAX_FILE:
                print(f"⚠️  跳过大文件(>2MB): {rel}")
                continue
            with open(full, "rb") as f:
                data = f.read()
            ext = os.path.splitext(fn)[1].lower()
            if ext in TEXT_EXT or fn == "Dockerfile":
                try:
                    files[rel] = data.decode("utf-8")
                    continue
                except UnicodeDecodeError:
                    pass
            files[rel] = "b64:" + base64.b64encode(data).decode()
    return files


def fail(res):
    print(f"❌ 部署失败: {res.get('error') or res.get('detail') or res if isinstance(res, dict) else res}")
    if isinstance(res, dict) and res.get("log"):
        print("---- 构建日志(末尾) ----")
        print(str(res["log"])[-2000:])
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="应用目录（须含 Dockerfile，监听 80）")
    ap.add_argument("--name", required=True, help="应用名（与线上一致则原链接更新）")
    ap.add_argument("--ports", default="80")
    a = ap.parse_args()

    key = load_key()
    if not key:
        print("❌ 缺少部署口令：设置环境变量 DEPLOY_KEY（GitHub secret 名为 UHOUZZ_DEPLOY_KEY）")
        sys.exit(2)
    if not os.path.isfile(os.path.join(a.dir, "Dockerfile")):
        print(f"❌ 目录里没有 Dockerfile: {a.dir}")
        sys.exit(2)

    files = collect(a.dir)
    print(f"📦 打包 {len(files)} 个文件，部署「{a.name}」…")
    payload = {"name": a.name, "ports": a.ports, "files": files}
    req = urllib.request.Request(
        GATEWAY + "/api/deploy",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Deploy-Key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            res = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read().decode())
        except Exception:
            res = {"error": f"HTTP {e.code}"}
        fail(res)
    except Exception as e:
        print(f"❌ 网关连接失败: {e}")
        sys.exit(1)

    if isinstance(res, dict) and res.get("ok"):
        print(f"✅ 部署成功: {res.get('url', a.name)}")
    else:
        fail(res)


if __name__ == "__main__":
    main()
