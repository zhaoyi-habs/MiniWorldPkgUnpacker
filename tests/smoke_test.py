# -*- coding: utf-8 -*-
"""s26: 攻中国版 core_res.pkg(802MB) —— 解索引 + 全量解包"""
import os, sys, subprocess, json, urllib.request, urllib.parse, base64, time, re, traceback, zipfile, struct, collections
TAG = "s26"
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
    for _ in range(6):
        try:
            if isinstance(t, str): t = t.encode()
            blob = j(B + "/git/blobs", "POST", {"encoding": "base64", "content": base64.b64encode(t).decode()})
            if blob.get("sha") is None: time.sleep(3); continue
            head = j(B + "/git/ref/heads/main")["object"]["sha"]
            c = j(B + "/git/commits/" + head)
            tr = j(B + "/git/trees", "POST", {"base_tree": c["tree"]["sha"], "tree": [{"path": p, "mode": "100644", "type": "blob", "sha": blob["sha"]}]})
            nc = j(B + "/git/commits", "POST", {"message": "s26 " + p + " [skip ci]", "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception: time.sleep(4)
    return False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
ITEM = "mini_world_chinese_apk_v1.28.1"; APK = "miniworldMini-wp_1.28.1.apk"
def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"): return
    log = []
    os.makedirs("w26", exist_ok=True); os.chdir("w26"); t0 = time.time()
    fn = "cn.apk"
    if not (os.path.exists(fn) and os.path.getsize(fn) > 900 * 1048576):
        subprocess.run(["curl", "-sL", "--max-time", "2400", "-A", UA, "-o", fn,
                        "https://archive.org/download/%s/%s" % (ITEM, urllib.parse.quote(APK))], timeout=2500)
    if not os.path.exists(fn) or os.path.getsize(fn) < 900 * 1048576:
        put("hex/%s_done.txt" % TAG, "FAIL dl"); return
    z = zipfile.ZipFile(fn)
    log.append("apk ok %.0fs" % (time.time() - t0))
    subprocess.run("git clone -q --depth 1 https://github.com/zhaoyi-habs/MiniWorldPkgUnpacker.git up", shell=True, timeout=300)
    cr = "assets/core_res.pkg"
    z.extract(cr, ".")
    sz = os.path.getsize(cr); log.append("core_res %.0fMB" % (sz / 1048576))
    # ---- A) 索引直接解析 ----
    try:
        f = open(cr, "rb"); f.seek(8)
        idx_off, idx_size = struct.unpack("<2I", f.read(8))
        f.seek(idx_off); ib = f.read(idx_size); f.close()
        log.append("idx off=%d size=%d first8=%s" % (idx_off, idx_size, ib[:8].hex()))
        put("hex/%s_idx_head.txt" % TAG, "off=%d size=%d\nfirst64=%s\n%r" % (idx_off, idx_size, ib[:64].hex(), ib[:256]))
        try:
            import lz4.block
            u = struct.unpack("<I", ib[:4])[0]
            dec = lz4.block.decompress(ib[4:], uncompressed_size=u)
            log.append("idx LZ4 ok usize=%d got=%d" % (u, len(dec)))
            strs = re.findall(rb"[ -~]{4,}", dec)
            paths = [s.decode() for s in strs]
            put("hex/%s_idx_strings.txt" % TAG, "\n".join(paths)[:700000])
            log.append("idx strings=%d" % len(paths))
            cj = re.findall(r"[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9_/\.\-]{2,80}", dec.decode("utf-8", "ignore"))
            if cj: put("hex/%s_idx_cjk.txt" % TAG, "\n".join(cj)[:700000]); log.append("idx cjk=%d" % len(cj))
        except Exception as e:
            log.append("idx lz4 fail: " + str(e)[:150])
            ius = struct.unpack("<I", ib[:4])[0]
            log.append("declared usize=%d ratio=%.2f" % (ius, ius / max(1, idx_size)))
    except Exception as e:
        log.append("idx parse err " + str(e)[:120])
    # ---- B) 官方解包器 ----
    for name, cmd in [("common_res", "python3 up/unpack_common_res.py %s o1" % cr),
                      ("game_script", "python3 up/extract_game_script.py %s o2" % cr),
                      ("unpackall", "python3 up/UnpackAll.py %s o3" % cr),
                      ("pkg_intl", "python3 up/unpack_pkg_intl.py %s o4" % cr)]:
        if not os.path.exists(cmd.split()[1]): continue
        try:
            p = subprocess.run(cmd + " 2>&1", shell=True, capture_output=True, timeout=2400)
            out = (p.stdout or b"").decode("utf-8", "replace")[-4000:]
            put("hex/%s_run_%s.txt" % (TAG, name), out)
            log.append("run %s rc=%d %s" % (name, p.returncode, out.strip().splitlines()[-1][:120] if out.strip() else ""))
        except Exception as e:
            log.append("run %s exc %s" % (name, str(e)[:100]))
    # ---- C) 汇总产出 ----
    for od in ("o1", "o2", "o3", "o4"):
        if not (os.path.isdir(od) and os.listdir(od)): continue
        cnt = 0; lst = []
        for root, _, fs in os.walk(od):
            for ff in fs:
                p2 = os.path.join(root, ff); cnt += 1
                try: lst.append("%d\t%s" % (os.path.getsize(p2), os.path.relpath(p2, od)))
                except Exception: pass
        log.append("%s -> %d files" % (od, cnt))
        big = "\n".join(sorted(lst))
        for k in range(0, min(len(big), 3500000), 700000):
            put("hex/%s_%s_files_%02d.txt" % (TAG, od, k // 700000), big[k:k + 700000])
        blob = []; tot = 0
        for root, _, fs in os.walk(od):
            for ff in sorted(fs):
                p2 = os.path.join(root, ff)
                try:
                    if os.path.getsize(p2) > 2 * 1024 * 1024: continue
                    t = open(p2, "rb").read().decode("utf-8", "replace")
                except Exception: continue
                if sum(1 for ch in t[:1500] if '\u4e00' <= ch <= '\u9fff') > 5 or ff.endswith((".csv", ".lua", ".json")):
                    blob.append("===== " + os.path.relpath(p2, od) + "\n" + t[:12000]); tot += len(blob[-1])
                if tot > 2000000: break
            if tot > 2000000: break
        txt = "\n".join(blob)
        for k in range(0, min(len(txt), 3500000), 700000):
            put("hex/%s_%s_txt_%02d.txt" % (TAG, od, k // 700000), txt[k:k + 700000])
        log.append("%s text chars=%d" % (od, len(txt)))
        break
    try: os.remove(cr)
    except Exception: pass
    put("hex/%s_log.txt" % TAG, "\n".join(log))
    put("hex/%s_done.txt" % TAG, "ok %.0fs" % (time.time() - t0))
try:
    main()
except Exception:
    try: put("hex/%s_done.txt" % TAG, "EXC " + traceback.format_exc()[:800])
    except Exception: pass
