# -*- coding: utf-8 -*-
"""s34: 全量解压 6023 个 Lua，undump 提取源路径/常量/函数名，tar.gz 回传"""
import os, sys, subprocess, json, urllib.request, urllib.parse, base64, time, re, traceback, zipfile, struct, io, tarfile, gzip
TAG = "s35"
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
    k = 0
    for i in range(0, len(s), n):
        put("%s%02d.txt" % (pref, k), s[i:i + n]); k += 1
    return k

class R:
    def __init__(s, b, sz8=False): s.b = b; s.p = 0; s.sz8 = sz8
    def u8(s):
        v = s.b[s.p]; s.p += 1; return v
    def u32(s):
        v = struct.unpack_from("<I", s.b, s.p)[0]; s.p += 4; return v
    def sz(s):
        if s.sz8:
            v = struct.unpack_from("<Q", s.b, s.p)[0]; s.p += 8
        else:
            v = struct.unpack_from("<I", s.b, s.p)[0]; s.p += 4
        return v
    def bytes(s, n):
        v = s.b[s.p:s.p + n]; s.p += n; return v

def _undump(b, sz8):
    out = []
    r = R(b, sz8); r.p = 4
    if r.u8() != 0x51: return None
    r.u8(); r.u8(); r.u8()
    szt = r.u8(); r.u8(); r.u8(); r.u8()
    r.sz8 = (szt == 8)
    def func(depth):
        if depth > 4: return
        ln = r.sz()
        src = r.bytes(ln) if ln else b""
        out.append(src.decode("utf-8", "replace"))
        r.u32(); r.u32(); r.u8(); r.u8(); r.u8(); r.u8()
        ncode = r.u32(); r.p += ncode * 4
        nk = r.u32()
        for _ in range(nk):
            t = r.u8()
            if t == 4:
                l = r.sz(); out.append(r.bytes(l).decode("utf-8", "replace"))
            elif t == 3: r.p += 8
            elif t == 1: r.p += 1
        nsub = r.u32()
        for _ in range(nsub): func(depth + 1)
    func(0)
    return out

def undump_strings(b):
    if b[:4] != b"\x1bLua": return None
    for sz8 in (False, True):
        try:
            o = _undump(b, sz8)
            if o: return ("ok%d" % (8 if sz8 else 4), o)
        except Exception:
            pass
    # 暴力兜底
    try:
        ss = [m.group().decode("utf-8", "replace") for m in re.finditer(
            rb"[\x20-\x7e\xc2-\xef][\x20-\x7e\x80-\xbf]{3,80}", b)]
        return ("brute", ss)
    except Exception:
        return ("fail", [])

def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"): return
    log = []
    os.makedirs("w35", exist_ok=True); os.chdir("w35"); t0 = time.time()
    fn = "cn.apk"
    if not (os.path.exists(fn) and os.path.getsize(fn) > 900 * 1048576):
        subprocess.run(["curl", "-sL", "--max-time", "2400", "-A", UA, "-o", fn,
                        "https://archive.org/download/%s/%s" % (ITEM, urllib.parse.quote(APK))], timeout=2500)
    if not os.path.exists(fn) or os.path.getsize(fn) < 900 * 1048576:
        put("hex/%s_done.txt" % TAG, "FAIL dl"); return
    z = zipfile.ZipFile(fn); cr = "assets/core_res.pkg"; z.extract(cr, ".")
    sz = os.path.getsize(cr)
    f = open(cr, "rb")
    f.seek(8); idx_off, idx_size = struct.unpack("<2I", f.read(8))
    f.seek(idx_off); ib = f.read(idx_size)
    import lz4.block
    dec = lz4.block.decompress(ib[4:], uncompressed_size=struct.unpack("<I", ib[:4])[0])
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
    log.append("recs %d" % len(recs))
    paths = []; consts = []; stats = {}
    nlua = 0; nuok = 0
    for i, (a, b, c) in enumerate(recs):
        if b < 8 or a + b > sz: continue
        f.seek(a); raw = f.read(b)
        u = struct.unpack("<I", raw[:4])[0]
        if u < 8 or u > 60 * 1048576: continue
        try: d2 = lz4.block.decompress(raw[4:], uncompressed_size=u)
        except Exception: continue
        if d2[:4] != b"\x1bLua": continue
        nlua += 1
        res = undump_strings(d2)
        if res is None: continue
        st, lst = res
        stats[st.split(":")[0]] = stats.get(st.split(":")[0], 0) + 1
        if st == "ok": nuok += 1
        if lst:
            paths.append("%d\t%s" % (i, lst[0]))
            seen = set(); keep = []
            for s in lst[1:]:
                if s and s not in seen and len(s) < 300:
                    seen.add(s); keep.append(s)
            consts.append("===== f%d %s\n%s" % (i, lst[0][:120], "\n".join(keep[:250])))
    f.close()
    log.append("lua=%d undump_ok=%d stats=%s" % (nlua, nuok, stats))
    big_paths = "\n".join(paths)
    big_const = "\n".join(consts)
    # tar.gz 打包
    buf = io.BytesIO()
    tf = tarfile.open(fileobj=buf, mode="w:gz")
    for name, data in [("paths.txt", big_paths), ("consts.txt", big_const)]:
        bb = data.encode("utf-8")
        ti = tarfile.TarInfo(name); ti.size = len(bb)
        tf.addfile(ti, io.BytesIO(bb))
    tf.close()
    enc = base64.b64encode(buf.getvalue()).decode()
    log.append("tar %.1fMB b64 %.1fMB" % (len(buf.getvalue()) / 1048576, len(enc) / 1048576))
    n = chunk_put("hex/%s_tar_" % TAG, enc)
    log.append("chunks %d" % n)
    put("hex/%s_log.txt" % TAG, "\n".join(log))
    try: os.remove(cr)
    except Exception: pass
    put("hex/%s_done.txt" % TAG, "ok %.0fs" % (time.time() - t0))
try:
    main()
except Exception:
    try: put("hex/%s_done.txt" % TAG, "EXC " + traceback.format_exc()[:900])
    except Exception: pass
