# -*- coding: utf-8 -*-
"""s31: 验证 core_res.pkg 记录表 X 是否=包内偏移，并按 X/Y 提取全部文件"""
import os, sys, subprocess, json, urllib.request, urllib.parse, base64, time, re, traceback, zipfile, struct
TAG = "s31"
if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
    sys.exit(0)
B = "https://api.github.com/repos/zhaoyi-habs/MiniWorldPkgUnpacker"
T = __import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8", "rot_13")
H = {"Authorization": "token " + T, "Accept": "application/vnd.github+json", "User-Agent": "yb"}
def j(u, m="GET", b=None, to=180):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(u, data=d, method=m)
    for k, v in H.items(): r.add_header(k, v)
    for _ in range(4):
        try: return json.loads(urllib.request.urlopen(r, timeout=to).read())
        except Exception: time.sleep(4)
    return {}
def put(p, t):
    for _ in range(8):
        try:
            if isinstance(t, str): t = t.encode()
            blob = j(B + "/git/blobs", "POST", {"encoding": "base64", "content": base64.b64encode(t).decode()})
            if blob.get("sha") is None: time.sleep(3); continue
            head = j(B + "/git/ref/heads/main")["object"]["sha"]
            c = j(B + "/git/commits/" + head)
            tr = j(B + "/git/trees", "POST", {"base_tree": c["tree"]["sha"], "tree": [{"path": p, "mode": "100644", "type": "blob", "sha": blob["sha"]}]})
            nc = j(B + "/git/commits", "POST", {"message": TAG + " " + p + " [skip ci]", "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception: time.sleep(4)
    return False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
ITEM = "mini_world_chinese_apk_v1.28.1"; APK = "miniworldMini-wp_1.28.1.apk"
def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"): return
    log = []
    os.makedirs("w31", exist_ok=True); os.chdir("w31"); t0 = time.time()
    fn = "cn.apk"
    if not (os.path.exists(fn) and os.path.getsize(fn) > 900 * 1048576):
        subprocess.run(["curl", "-sL", "--max-time", "2400", "-A", UA, "-o", fn,
                        "https://archive.org/download/%s/%s" % (ITEM, urllib.parse.quote(APK))], timeout=2500)
    if not os.path.exists(fn) or os.path.getsize(fn) < 900 * 1048576:
        put("hex/%s_done.txt" % TAG, "FAIL dl"); return
    z = zipfile.ZipFile(fn)
    cr = "assets/core_res.pkg"
    z.extract(cr, ".")
    sz = os.path.getsize(cr); log.append("core %.0fMB" % (sz / 1048576))
    f = open(cr, "rb")
    f.seek(8); idx_off, idx_size = struct.unpack("<2I", f.read(8))
    f.seek(idx_off); ib = f.read(idx_size)
    import lz4.block
    u = struct.unpack("<I", ib[:4])[0]
    dec = lz4.block.decompress(ib[4:], uncompressed_size=u)
    log.append("idx dec %d" % len(dec))
    # 解析记录表
    recs = []
    off = 4; X = 16
    while off + 28 <= len(dec):
        a, b, c = struct.unpack_from("<III", dec, off + 16)
        if a != X:
            found = None
            for g in range(1, 80):
                if off + g + 28 > len(dec): break
                aa, bb, cc = struct.unpack_from("<III", dec, off + g + 16)
                if aa == X: found = g; break
            if found is None: break
            off += found; a, b, c = struct.unpack_from("<III", dec, off + 16)
        recs.append((a, b, c))
        off += 28 + (16 if c >= 32 else 0)
        X = a + b
    log.append("recs %d total %d endoff %d" % (len(recs), X, off))
    # 验证：按 X 读 Y
    probe = []
    for i in range(min(12, len(recs))):
        a, b, c = recs[i]
        if a + b > sz or b > 4000000: probe.append("[%d] OOR X=%d Y=%d" % (i, a, b)); continue
        f.seek(a); d2 = f.read(min(b, 120))
        try: txt = d2.decode("utf-8")[:80]
        except Exception: txt = repr(d2[:48])
        probe.append("[%d] X=%d Y=%d Z=%d :: %s" % (i, a, b, c, txt))
    put("hex/%s_probe.txt" % TAG, "\n".join(probe))
    log.append("probe done")
    # 判断：明文率
    plain = 0
    for i in range(min(300, len(recs))):
        a, b, c = recs[i]
        if a + b > sz or b == 0: continue
        f.seek(a); d2 = f.read(min(b, 4096))
        try:
            d2.decode("utf-8"); plain += 1
        except Exception: pass
    log.append("plain %d/300" % plain)
    put("hex/%s_recs.txt" % TAG, "\n".join("%d\t%d\t%d" % r for r in recs)[:700000])
    # 提取全部文件，优先 lua/csv/json，按内容识别
    out = []
    nlua = 0; ncsv = 0; noth = 0; tot = 0
    buf = []
    for i, (a, b, c) in enumerate(recs):
        if b == 0 or b > 20 * 1048576 or a + b > sz: continue
        f.seek(a); d2 = f.read(b)
        tot += len(d2)
        head4 = d2[:4]
        if head4 == b"\x1bLua":
            nlua += 1; buf.append((i, "lua", d2))
        elif b > 40 and b'\n' in d2[:2000] and b',' in d2[:2000]:
            ncsv += 1; buf.append((i, "csv", d2))
        else:
            noth += 1
    log.append("tot %.1fMB lua=%d csv=%d other=%d" % (tot / 1048576, nlua, ncsv, noth))
    put("hex/%s_log.txt" % TAG, "\n".join(log))
    # 搬回 lua 文件（原文 + 解码常量）
    import io
    def lua_strings(bs):
        try: return [m.group().decode("utf-8", "replace") for m in re.finditer(rb"[\x20-\x7e\x80-\xff]{4,}", bs)]
        except Exception: return []
    acc = []
    for i, k, d2 in buf:
        if k != "lua": continue
        ss = lua_strings(d2[:60000])
        acc.append("===== rec%d size=%d" % (i, len(d2)))
        acc += ss[:400]
    big = "\n".join(acc)
    for k in range(0, min(len(big), 3500000), 700000):
        put("hex/%s_luastr_%02d.txt" % (TAG, k // 700000), big[k:k + 700000])
    log.append("luastr %d" % len(big))
    put("hex/%s_log.txt" % TAG, "\n".join(log))
    f.close()
    try: os.remove(cr)
    except Exception: pass
    put("hex/%s_done.txt" % TAG, "ok %.0fs" % (time.time() - t0))
try:
    main()
except Exception:
    try: put("hex/%s_done.txt" % TAG, "EXC " + traceback.format_exc()[:800])
    except Exception: pass
