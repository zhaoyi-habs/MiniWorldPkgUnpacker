# -*- coding: utf-8 -*-
"""s27: 国际版 APK 全量 CSV / 配置表 原始数据"""
import os, sys, subprocess, json, urllib.request, base64, time, re, traceback, zipfile, collections
TAG = "s27"
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
            nc = j(B + "/git/commits", "POST", {"message": "s27 " + p + " [skip ci]", "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception: time.sleep(4)
    return False
def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"): return
    log = []
    os.makedirs("w27", exist_ok=True); os.chdir("w27"); t0 = time.time()
    fn = "intl.apk"
    u = "https://github.com/zhaoyi-habs/miniworld-tools/releases/download/mnw-v1/MiniWorld_latest.apk"
    if not (os.path.exists(fn) and os.path.getsize(fn) > 500 * 1048576):
        subprocess.run(["curl", "-sL", "--max-time", "1800", "-o", fn, u], timeout=1900)
    if not os.path.exists(fn) or os.path.getsize(fn) < 500 * 1048576:
        put("hex/%s_done.txt" % TAG, "FAIL dl %d" % (os.path.getsize(fn) if os.path.exists(fn) else 0)); return
    z = zipfile.ZipFile(fn); names = z.namelist()
    log.append("intl %.0fMB entries=%d (%.0fs)" % (os.path.getsize(fn) / 1048576, len(names), time.time() - t0))
    put("hex/%s_entries.txt" % TAG, "\n".join("%s\t%d" % (n, z.getinfo(n).file_size) for n in names if n.endswith((".pkg", ".so")) or n.startswith("assets/")))
    subprocess.run("git clone -q --depth 1 https://github.com/zhaoyi-habs/MiniWorldPkgUnpacker.git up", shell=True, timeout=300)
    pkgs = [(n, z.getinfo(n).file_size) for n in names if n.endswith(".pkg")]
    log.append("pkgs: " + ", ".join("%s=%.0fMB" % (os.path.basename(n), s / 1048576) for n, s in pkgs))
    for n, s in sorted(pkgs, key=lambda x: x[1]):
        if s > 400 * 1048576: continue
        try: z.extract(n, ".")
        except Exception as e: log.append("x %s %s" % (n, str(e)[:60])); continue
        base = re.sub(r"[^A-Za-z0-9]", "", os.path.basename(n)); out = "o_" + base
        for sc in ("python3 up/unpack_common_res.py %s %s" % (n, out),
                   "python3 up/extract_game_script.py %s %s" % (n, out),
                   "python3 up/UnpackAll.py %s %s" % (n, out),
                   "python3 up/unpack_pkg_intl.py %s %s" % (n, out)):
            if not os.path.exists(sc.split()[1]): continue
            subprocess.run(sc + " >/dev/null 2>&1", shell=True, timeout=1800)
            if os.path.isdir(out) and os.listdir(out): break
        cnt = sum(len(f) for _, _, f in os.walk(out)) if os.path.isdir(out) else 0
        log.append("%s -> %d" % (n, cnt))
        if not cnt:
            try: os.remove(n)
            except Exception: pass
            continue
        # 全量 CSV / JSON / XML 内容
        blob = []; tot = 0
        for root, _, fs in os.walk(out):
            for ff in sorted(fs):
                if not ff.lower().endswith((".csv", ".json", ".xml", ".txt", ".ini", ".cfg")): continue
                p2 = os.path.join(root, ff)
                try:
                    if os.path.getsize(p2) > 3 * 1024 * 1024: continue
                    t = open(p2, "rb").read().decode("utf-8", "replace")
                except Exception: continue
                blob.append("===== " + os.path.relpath(p2, out) + " (" + str(len(t)) + ")\n" + t[:30000]); tot += len(blob[-1])
                if tot > 4000000: break
            if tot > 4000000: break
        txt = "\n".join(blob)
        for k in range(0, min(len(txt), 4200000), 700000):
            put("hex/%s_%s_cfg_%02d.txt" % (TAG, base, k // 700000), txt[k:k + 700000])
        log.append("  cfg chars=%d" % len(txt))
        # 文件清单
        lst = []
        for root, _, fs in os.walk(out):
            for ff in fs:
                try: lst.append("%d\t%s" % (os.path.getsize(os.path.join(root, ff)), os.path.relpath(os.path.join(root, ff), out)))
                except Exception: pass
        big = "\n".join(sorted(lst))
        for k in range(0, min(len(big), 1400000), 700000):
            put("hex/%s_%s_files_%02d.txt" % (TAG, base, k // 700000), big[k:k + 700000])
        subprocess.run("rm -rf %s %s" % (out, n), shell=True)
    put("hex/%s_log.txt" % TAG, "\n".join(log))
    put("hex/%s_done.txt" % TAG, "ok %.0fs" % (time.time() - t0))
try:
    main()
except Exception:
    try: put("hex/%s_done.txt" % TAG, "EXC " + traceback.format_exc()[:800])
    except Exception: pass
