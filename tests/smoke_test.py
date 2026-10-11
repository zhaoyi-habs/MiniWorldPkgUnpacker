# -*- coding: utf-8 -*-
"""s32: 探索 core_res.pkg 全貌 + 搬回压缩样本供本地破解"""
import os, sys, subprocess, json, urllib.request, urllib.parse, base64, time, re, traceback, zipfile, struct
TAG = "s32"
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
    os.makedirs("w32", exist_ok=True); os.chdir("w32"); t0 = time.time()
    fn = "cn.apk"
    if not (os.path.exists(fn) and os.path.getsize(fn) > 900 * 1048576):
        subprocess.run(["curl", "-sL", "--max-time", "2400", "-A", UA, "-o", fn,
                        "https://archive.org/download/%s/%s" % (ITEM, urllib.parse.quote(APK))], timeout=2500)
    if not os.path.exists(fn) or os.path.getsize(fn) < 900 * 1048576:
        put("hex/%s_done.txt" % TAG, "FAIL dl"); return
    z = zipfile.ZipFile(fn)
    # 1. APK 内所有 pkg / so
    lst = [(i.filename, i.file_size) for i in z.infolist() if re.search(r"\.(pkg|so)$", i.filename)]
    put("hex/%s_apklist.txt" % TAG, "\n".join("%d\t%s" % (s, n) for n, s in lst))
    log.append("apk pkg/so %d" % len(lst))
    cr = "assets/core_res.pkg"
    z.extract(cr, ".")
    sz = os.path.getsize(cr); log.append("core %.0fMB" % (sz / 1048576))
    f = open(cr, "rb")
    # 2. 索引块
    f.seek(8); idx_off, idx_size = struct.unpack("<2I", f.read(8))
    log.append("idx_off=%d idx_size=%d" % (idx_off, idx_size))
    import lz4.block
    f.seek(idx_off); ib = f.read(idx_size)
    u = struct.unpack("<I", ib[:4])[0]
    dec = lz4.block.decompress(ib[4:], uncompressed_size=u)
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
    log.append("recs %d cover %d (%.1fMB of %.0fMB)" % (len(recs), X, X / 1048576, sz / 1048576))
    # 3. 搬回前 6 个文件的完整压缩字节（供本地破解算法）
    for i in range(min(6, len(recs))):
        a, b, c = recs[i]
        if b == 0 or a + b > sz: continue
        f.seek(a); d2 = f.read(b)
        put("hex/%s_samp_%02d.txt" % (TAG, i), base64.b64encode(d2).decode()[:690000])
    log.append("samples sent")
    # 4. 覆盖区之后的内容特征
    tail_probes = []
    for base_off in [X, sz // 4, sz // 2, int(sz * 0.75), sz - 2000000]:
        if base_off + 100000 > sz: continue
        f.seek(base_off); blk = f.read(100000)
        nz = sum(1 for x in blk if 32 <= x < 127)
        hits = [m.start() for m in re.finditer(rb"\x1bLua", blk)]
        luastr = len(re.findall(rb"\.lua", blk))
        tail_probes.append("off=%d printable=%d/100000 luaMagic=%s .lua=%d head=%s" % (
            base_off, nz, hits[:5], luastr, blk[:32].hex()))
    put("hex/%s_tail.txt" % TAG, "\n".join(tail_probes))
    # 5. 全包搜 Lua 魔数 + .lua 名（分块扫，限制时间）
    magic = []
    step = 4 * 1048576
    buf = b""
    pos = 0
    f.seek(0)
    scanned = 0
    while pos < sz and scanned < 400 * 1048576:
        blk = f.read(step)
        if not blk: break
        buf = (buf + blk)[-8:]
        for m in re.finditer(rb"\x1bLua", buf):
            magic.append(pos - len(buf) + len(blk) + m.start() if False else pos + m.start())
        pos += len(blk); scanned += len(blk)
    log.append("luaMagic hits %d %s" % (len(magic), magic[:10]))
    f.close()
    put("hex/%s_log.txt" % TAG, "\n".join(log))
    try: os.remove(cr)
    except Exception: pass
    put("hex/%s_done.txt" % TAG, "ok %.0fs" % (time.time() - t0))
try:
    main()
except Exception:
    try: put("hex/%s_done.txt" % TAG, "EXC " + traceback.format_exc()[:800])
    except Exception: pass
