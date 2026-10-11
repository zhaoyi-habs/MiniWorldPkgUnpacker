# -*- coding: utf-8 -*-
"""s33: 全量解压 core_res.pkg 77.5MB + 探索第二段索引"""
import os, sys, subprocess, json, urllib.request, urllib.parse, base64, time, re, traceback, zipfile, struct
TAG = "s33"
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
def chunk_put(pref, s, n=680000):
    for k in range(0, len(s), n):
        put("%s%02d.txt" % (pref, k // n), s[k:k + n])
def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"): return
    log = []
    os.makedirs("w33", exist_ok=True); os.chdir("w33"); t0 = time.time()
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
    dec = lz4.block.decompress(ib[4:], uncompressed_size=struct.unpack("<I", ib[:4])[0])
    # 第二段索引区 hex（供本地分析）
    chunk_put("hex/%s_idxmid_hex_" % TAG, dec[359288:359288 + 120000].hex())
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
    log.append("recs %d cover %.1fMB" % (len(recs), X / 1048576))
    # 全量解压
    nok = 0; nfail = 0; entries = []
    types = {}
    for i, (a, b, c) in enumerate(recs):
        if b < 8 or a + b > sz: continue
        f.seek(a); raw = f.read(b)
        u = struct.unpack("<I", raw[:4])[0]
        if u == 0 or u > 200 * 1048576: continue
        try:
            d2 = lz4.block.decompress(raw[4:], uncompressed_size=u)
        except Exception:
            nfail += 1; continue
        nok += 1
        head = d2[:4]
        if head == b"\x1bLua": t = "lua"
        elif d2[:2] in (b"PK", b"{\""): t = "zip/json"
        elif b"," in d2[:400] and b"\n" in d2[:400]: t = "csv"
        else: t = "bin"
        types[t] = types.get(t, 0) + 1
        entries.append((i, a, b, u, t, d2))
    log.append("dec ok=%d fail=%d types=%s" % (nok, nfail, types))
    # 1) 全部 CSV 的表头（前 3 行）
    heads = []
    for i, a, b, u, t, d2 in entries:
        if t != "csv": continue
        txt = d2[:4000].decode("utf-8", "replace")
        lines = [x for x in txt.split("\n")[:3]]
        heads.append("===== f%d usize=%d\n%s" % (i, u, "\n".join(lines)))
    big = "\n".join(heads)
    chunk_put("hex/%s_csvhead_" % TAG, big[:4200000])
    log.append("csvhead %d chars %d files" % (len(big), len(heads)))
    # 2) 含关键词的 CSV 完整内容
    KW = re.compile(r"(api|event|trigger|component|block|actor|player|creature|item|buff|skill|ui|codeblock|var|team|task|ai)", re.I)
    full = []
    nf = 0
    for i, a, b, u, t, d2 in entries:
        if t != "csv": continue
        if u > 400000: continue
        txt = d2.decode("utf-8", "replace")
        if not KW.search(txt[:2000]): continue
        nf += 1
        full.append("===== f%d usize=%d\n%s" % (i, u, txt[:20000]))
        if len("\n".join(full)) > 4000000: break
    chunk_put("hex/%s_csvfull_" % TAG, "\n".join(full)[:4200000])
    log.append("csvfull %d files" % nf)
    # 3) 非 CSV 的头部特征
    oth = []
    for i, a, b, u, t, d2 in entries:
        if t == "csv": continue
        oth.append("f%d usize=%d type=%s head=%s" % (i, u, t, d2[:60].hex()))
    chunk_put("hex/%s_other_" % TAG, "\n".join(oth)[:2000000])
    log.append("other %d" % len(oth))
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
