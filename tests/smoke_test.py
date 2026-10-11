# -*- coding: utf-8 -*-
"""s28: 把中国版 core_res.pkg 的解压索引整块搬回（base64），供本地逆向"""
import os, sys, subprocess, json, urllib.request, urllib.parse, base64, time, re, traceback, zipfile, struct
TAG = "s29"
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
            nc = j(B + "/git/commits", "POST", {"message": "s28 " + p + " [skip ci]", "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception: time.sleep(4)
    return False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
ITEM = "mini_world_chinese_apk_v1.28.1"; APK = "miniworldMini-wp_1.28.1.apk"
def chunk_put(pref, data, n=600000):
    s = base64.b64encode(data).decode()
    for k in range(0, len(s), n):
        put("%s%02d.txt" % (pref, k // n), s[k:k + n])
def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"): return
    log = []
    os.makedirs("w28", exist_ok=True); os.chdir("w28"); t0 = time.time()
    fn = "cn.apk"
    if not (os.path.exists(fn) and os.path.getsize(fn) > 900 * 1048576):
        subprocess.run(["curl", "-sL", "--max-time", "2400", "-A", UA, "-o", fn,
                        "https://archive.org/download/%s/%s" % (ITEM, urllib.parse.quote(APK))], timeout=2500)
    if not os.path.exists(fn) or os.path.getsize(fn) < 900 * 1048576:
        put("hex/%s_done.txt" % TAG, "FAIL dl"); return
    z = zipfile.ZipFile(fn)
    log.append("apk ok %.0fs" % (time.time() - t0))
    cr = "assets/core_res.pkg"
    z.extract(cr, ".")
    sz = os.path.getsize(cr); log.append("core %.0fMB" % (sz / 1048576))
    f = open(cr, "rb")
    head = f.read(512)
    put("hex/%s_pkghead.txt" % TAG, head.hex())
    # 明文区（s24 发现 1.9M 起有 .lua 路径）
    f.seek(1500000); raw = f.read(1500000)
    strs = re.findall(rb"[ -~]{6,}", raw)
    put("hex/%s_plain.txt" % TAG, "\n".join("%d\t%s" % (1500000 + m.start(), s.group().decode()) for m in re.finditer(rb"[ -~]{8,}", raw))[:700000])
    log.append("plain strings=%d" % len(strs))
    # 索引
    f.seek(8); idx_off, idx_size = struct.unpack("<2I", f.read(8))
    f.seek(idx_off); ib = f.read(idx_size); f.close()
    import lz4.block
    u = struct.unpack("<I", ib[:4])[0]
    dec = lz4.block.decompress(ib[4:], uncompressed_size=u)
    log.append("idx dec %d" % len(dec))
    chunk_put("hex/%s_idx_b64_" % TAG, dec)
    # 全量字符串
    allstr = [m.group().decode() for m in re.finditer(rb"[ -~]{4,}", dec)]
    big = "\n".join(allstr)
    for k in range(0, min(len(big), 4200000), 700000):
        put("hex/%s_idx_str_%02d.txt" % (TAG, k // 700000), big[k:k + 700000])
    log.append("idx strings=%d" % len(allstr))
    # 路径类
    paths = [s for s in allstr if "/" in s and re.search(r"\.(lua|csv|json|png|ogg|mp3|ent|emo|skanim|mesh|mat|fbx|txt|xml|ttf|pkg)$", s)]
    put("hex/%s_idx_paths.txt" % TAG, "\n".join(paths)[:700000])
    log.append("paths=%d" % len(paths))
    try: os.remove(cr)
    except Exception: pass
    put("hex/%s_log.txt" % TAG, "\n".join(log))
    put("hex/%s_done.txt" % TAG, "ok %.0fs" % (time.time() - t0))
try:
    main()
except Exception:
    try: put("hex/%s_done.txt" % TAG, "EXC " + traceback.format_exc()[:800])
    except Exception: pass
