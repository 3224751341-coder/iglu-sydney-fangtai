#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署到公司内部容器平台（app.uhomes.com）。

2026-10-16 重写。旧版（2026-10-13 之前）自己拼 POST /api/deploy，平台在10-15 升级成
「协作应用」后这套契约直接被拒：
    HTTP 409 {'code':'source_base_required',
              'error':'这是协作应用，请先用新版发布工具获取或同步代码，再发布。现有代码未被修改。'}
协作应用必须先有本地基准（.platform-source.json + .platform-base/），发布时带 base_revision，
网关据此判断你是不是基于最新线上代码改的。基准已随仓库提交（container/ 下），CI 全新
checkout 也能直接发。

发布工具本体不在仓库里（平台侧 https://app.uhomes.com/skill/deploy.py，客户端版本随请求
上报，网关据此提醒过旧的重新安装）。这里按需拉取并缓存到 .publish-tool/ 下：
  - 已缓存 → 直接用（离线也能跑）
  - 拉取失败且无缓存 → 明确报错退出，不静默跳过部署
工具会自更新，所以这里不写死版本号；--selftest 校验它确实是发布工具再用。

用法:
  python3 deploy_uhouzz.py --dir ./container --name iglu-rate-desk   # 发布
  python3 deploy_uhouzz.py --dir ./container --name iglu-rate-desk --check  # 只检查不发布
  python3 deploy_uhouzz.py --dir ./container --name iglu-rate-desk --sync   # 拉线上最新并保留本地改动
"""
import os
import sys
import json
import argparse
import hashlib
import subprocess
import urllib.request
import urllib.error

SKILL_BASE = os.environ.get("SKILL_BASE", "https://app.uhomes.com/skill").rstrip("/")
TOOL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".publish-tool")
TOOL_PATH = os.path.join(TOOL_DIR, "deploy.py")


def load_key():
    k = os.environ.get("DEPLOY_KEY", "").strip()
    if k:
        return k
    try:
        with open(os.path.expanduser("~/.uhouzz-deploy/key"), encoding="utf-8-sig") as f:
            return f.read().strip()
    except OSError:
        return ""


def fetch_tool(force=False):
    """拉取平台上的发布工具（self-update 逻辑在这份工具自己里面，这里只负责拿到入口副本）。
    返回本地路径；拿不到且无缓存时返回 None。"""
    if os.path.isfile(TOOL_PATH) and not force:
        return TOOL_PATH
    try:
        os.makedirs(TOOL_DIR, exist_ok=True)
        with urllib.request.urlopen(f"{SKILL_BASE}/deploy.py", timeout=60) as r:
            data = r.read()
    except Exception as e:
        if os.path.isfile(TOOL_PATH):
            print(f"⚠️ 拉取发布工具失败({e})，用本地缓存副本")
            return TOOL_PATH
        return None

    # 内容自检：挡住错误页/半截文件/写坏的脚本
    try:
        text = data.decode("utf-8-sig")
        compile(text, "deploy.py", "exec")
    except Exception:
        if os.path.isfile(TOOL_PATH):
            print("⚠️ 下载的发布工具没通过校验，用本地缓存副本")
            return TOOL_PATH
        return None
    if "CLIENT_VERSION" not in text or "--selftest" not in text:
        if os.path.isfile(TOOL_PATH):
            print("⚠️ 下载的不是发布工具，用本地缓存副本")
            return TOOL_PATH
        return None

    tmp = TOOL_PATH + ".new"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, TOOL_PATH)
    ver = ""
    for line in text.splitlines():
        if line.startswith("CLIENT_VERSION"):
            ver = line.split("=", 1)[1].split("#")[0].strip().strip('"')
            break
    print(f"📥 发布工具就绪 v{ver}（{hashlib.sha256(data).hexdigest()[:12]}）")
    return TOOL_PATH


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="应用目录（须含 Dockerfile，监听 80）")
    ap.add_argument("--name", required=True, help="应用名（与线上一致则原链接更新）")
    ap.add_argument("--ports", default=None, help="应用监听端口，默认 80")
    ap.add_argument("--check", action="store_true", help="只做发布前检查，不真的发布")
    ap.add_argument("--sync", action="store_true", help="拉取线上最新代码并保留本地改动")
    ap.add_argument("--refresh-tool", action="store_true", help="强制重新拉取发布工具")
    a = ap.parse_args()

    key = load_key()
    if not key:
        print("❌ 缺少部署口令：设置环境变量 DEPLOY_KEY（Actions 里对应 secret UHOUZZ_DEPLOY_KEY）")
        sys.exit(2)
    os.environ["DEPLOY_KEY"] = key

    if not os.path.isdir(a.dir):
        print(f"❌ 目录不存在: {a.dir}")
        sys.exit(2)
    if not a.sync and not os.path.isfile(os.path.join(a.dir, "Dockerfile")):
        print(f"❌ 目录里没有 Dockerfile: {a.dir}")
        sys.exit(2)

    tool = fetch_tool(force=a.refresh_tool)
    if not tool:
        print(f"❌ 拿不到发布工具（{SKILL_BASE}/deploy.py），且本地无缓存副本，无法发布。")
        print("   网络恢复后重跑，或手动下载该文件放到：" + TOOL_PATH)
        sys.exit(2)

    cmd = [sys.executable, tool, "--dir", a.dir, "--name", a.name, "--no-update"]
    if a.ports:
        cmd += ["--ports", a.ports]
    if a.sync:
        cmd += ["--sync"]
    elif a.check:
        cmd += ["--check"]

    # 发布工具要读平台清单做自更新，--no-update 已避免重复下载；
    # 子进程继承 stdout/stderr，日志直接进 Actions 日志
    result = subprocess.run(cmd, text=True, capture_output=True)
    out = (result.stdout or "") + (result.stderr or "")
    if out.strip():
        print(out.strip())
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()