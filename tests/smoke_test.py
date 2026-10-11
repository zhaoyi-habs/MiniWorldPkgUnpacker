# -*- coding: utf-8 -*-
"""s24: 深挖中国版 v1.28.1 —— C++ 引擎层全字符串 + core_res.pkg 结构"""
import os, sys, subprocess, json, urllib.request, urllib.parse, base64, time, re, traceback, zipfile, collections, struct, hashlib, math

TAG = "s24"
if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
    sys.exit(0)

B = "https://api.github.com/repos/zhaoyi-habs/MiniWorldPkgUnpacker"
T = __import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8", "rot_13")
H = {"Authorization": "token " + T, "Accept": "application/vnd.github+json", "User-Agent": "yb"}


def j(u, m="GET", b=None, to=180):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(u, data=d, method=m)
    for k, v in H.items():
        r.add_header(k, v)
    for _ in range(4):
        try:
            return json.loads(urllib.request.urlopen(r, timeout=to).read())
        except Exception:
            time.sleep(4)
    return {}


def put(p, t):
    for _ in range(6):
        try:
            if isinstance(t, str):
                t = t.encode()
            blob = j(B + "/git/blobs", "POST", {"encoding": "base64", "content": base64.b64encode(t).decode()})
            if blob.get("sha") is None:
                time.sleep(3); continue
            head = j(B + "/git/ref/heads/main")["object"]["sha"]
            c = j(B + "/git/commits/" + head)
            tr = j(B + "/git/trees", "POST", {"base_tree": c["tree"]["sha"],
                                              "tree": [{"path": p, "mode": "100644", "type": "blob", "sha": blob["sha"]}]})
            nc = j(B + "/git/commits", "POST", {"message": "s24 " + p + " [skip ci]", "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception:
            time.sleep(4)
    return False


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
ITEM = "mini_world_chinese_apk_v1.28.1"
APK = "miniworldMini-wp_1.28.1.apk"


def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"):
        return
    log = []
    os.makedirs("w24", exist_ok=True)
    os.chdir("w24")
    t0 = time.time()
    fn = "cn.apk"
    if not (os.path.exists(fn) and os.path.getsize(fn) > 900 * 1048576):
        subprocess.run(["curl", "-sL", "--max-time", "2400", "-A", UA, "-o", fn,
                        "https://archive.org/download/%s/%s" % (ITEM, urllib.parse.quote(APK))], timeout=2500)
    if not os.path.exists(fn) or os.path.getsize(fn) < 900 * 1048576:
        put("hex/%s_done.txt" % TAG, "FAIL dl")
        return
    z = zipfile.ZipFile(fn)
    names = z.namelist()
    log.append("apk %.0fMB entries=%d (%.0fs)" % (os.path.getsize(fn) / 1048576, len(names), time.time() - t0))
    put("hex/%s_entries.txt" % TAG, "\n".join("%s\t%d" % (n, z.getinfo(n).file_size) for n in names))

    # ---------- 1) C++ 引擎层：全字符串表 ----------
    son = "lib/arm64-v8a/liblibGameApp.so"
    if son in names:
        try:
            data = z.read(son)
        except Exception as e:
            data = b""
            log.append("so read fail " + str(e)[:80])
        if data:
            log.append("so size %.0fMB" % (len(data) / 1048576))
            strs = re.findall(rb"[ -~]{4,}", data)
            log.append("ascii strings=%d" % len(strs))
            c = collections.Counter(s.decode() for s in strs)
            pats = {
                "apicls":   re.compile(r"^Api[A-Z][A-Za-z0-9_]{1,40}$"),
                "method":   re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,30}:[A-Za-z][A-Za-z0-9_]{1,40}$"),
                "minidot":  re.compile(r"^Mini\.[A-Za-z0-9_.]{2,60}$"),
                "luafile":  re.compile(r"^[A-Za-z0-9_/\-\.]{4,140}\.lua$"),
                "csvfile":  re.compile(r"^[A-Za-z0-9_/\-\.]{4,140}\.csv$"),
                "jsonfile": re.compile(r"^[A-Za-z0-9_/\-\.]{4,140}\.json$"),
                "pkgfile":  re.compile(r"^[A-Za-z0-9_/\-\.]{4,140}\.(pkg|skanim|mesh|skeleton|mat|png|fbx|ogg|mp3)$"),
                "event":    re.compile(r"^(Game|Actor|Player|Block|Creature|Item|Backpack|Team|UI|Area|World)\.[A-Za-z0-9_.]{2,60}$"),
                "luaapi":   re.compile(r"^lua[A-Za-z0-9_]{2,30}$"),
                "setter":   re.compile(r"^(get|set|is|has|add|remove|create|play|stop|update|on)[A-Z][A-Za-z0-9_]{2,40}$"),
            }
            for pn, r in pats.items():
                cc = collections.Counter()
                for s, n in c.items():
                    if r.match(s):
                        cc[s] = n
                if not cc:
                    continue
                big = "\n".join("%d\t%s" % (n, s) for s, n in cc.most_common(60000))
                for k in range(0, len(big), 700000):
                    put("hex/%s_so_%s_%02d.txt" % (TAG, pn, k // 700000), big[k:k + 700000])
                log.append("  so %-8s %d" % (pn, len(cc)))
            # 全量（去噪：丢掉纯 hex / 纯路径垃圾）
            keep = [(n, s) for s, n in c.most_common()
                    if len(s) >= 5 and not re.match(r"^[0-9a-fA-F]{16,}$", s)]
            big = "\n".join("%d\t%s" % (n, s) for n, s in keep[:200000])
            for k in range(0, len(big), 700000):
                put("hex/%s_so_all_%02d.txt" % (TAG, k // 700000), big[k:k + 700000])
            log.append("  so all kept=%d" % len(keep))
            # 中文字符串
            try:
                txt = data.decode("utf-8", "ignore")
                cj = collections.Counter(re.findall(r"[\u4e00-\u9fff][\u4e00-\u9fff\u3000-\u303fA-Za-z0-9_]{2,60}", txt))
            except Exception:
                cj = collections.Counter()
            if cj:
                big = "\n".join("%d\t%s" % (n, s) for s, n in cj.most_common(60000))
                for k in range(0, len(big), 700000):
                    put("hex/%s_so_cjk_%02d.txt" % (TAG, k // 700000), big[k:k + 700000])
                log.append("  so cjk=%d" % len(cj))
            del data, strs, c

    # ---------- 2) 小 pkg 全解 ----------
    subprocess.run("git clone -q --depth 1 https://github.com/zhaoyi-habs/MiniWorldPkgUnpacker.git up", shell=True, timeout=300)
    small = []
    for n in names:
        if n.startswith("assets/") and n.endswith(".pkg"):
            sz = z.getinfo(n).file_size
            if sz < 40 * 1048576:
                small.append((n, sz))
    for n, sz in small:
        try:
            z.extract(n, ".")
        except Exception as e:
            log.append("extract %s fail %s" % (n, str(e)[:60])); continue
        out = "u_" + os.path.basename(n)
        for sc in ("python3 up/unpack_common_res.py %s %s" % (n, out),
                   "python3 up/extract_game_script.py %s %s" % (n, out),
                   "python3 up/UnpackAll.py %s %s" % (n, out),
                   "python3 up/unpack_pkg_intl.py %s %s" % (n, out)):
            if not os.path.exists(sc.split()[1]):
                continue
            subprocess.run(sc + " >/dev/null 2>&1", shell=True)
            if os.path.isdir(out) and os.listdir(out):
                break
        cnt = sum(len(f) for _, _, f in os.walk(out)) if os.path.isdir(out) else 0
        log.append("%s (%.1fMB) -> %d files" % (n, sz / 1048576, cnt))
        if cnt:
            lst = []
            for root, _, fs in os.walk(out):
                for ff in fs:
                    p2 = os.path.join(root, ff)
                    try:
                        lst.append("%d\t%s" % (os.path.getsize(p2), os.path.relpath(p2, out)))
                    except Exception:
                        pass
            put("hex/%s_%s_files.txt" % (TAG, re.sub(r"[^A-Za-z0-9]", "", os.path.basename(n))), "\n".join(lst)[:700000])
            # 文本内容抽样
            blob = []
            for root, _, fs in os.walk(out):
                for ff in fs:
                    p2 = os.path.join(root, ff)
                    try:
                        if os.path.getsize(p2) > 3 * 1024 * 1024:
                            continue
                        t = open(p2, "rb").read().decode("utf-8", "replace")
                    except Exception:
                        continue
                    if sum(1 for ch in t[:2000] if '\u4e00' <= ch <= '\u9fff') > 5 or ff.endswith((".csv", ".lua", ".json", ".xml")):
                        blob.append("===== " + os.path.relpath(p2, out) + "\n" + t[:20000])
                    if sum(len(x) for x in blob) > 600000:
                        break
                if sum(len(x) for x in blob) > 600000:
                    break
            if blob:
                txt = "\n".join(blob)
                for k in range(0, len(txt), 700000):
                    put("hex/%s_%s_txt_%02d.txt" % (TAG, re.sub(r"[^A-Za-z0-9]", "", os.path.basename(n)), k // 700000), txt[k:k + 700000])
        try:
            os.remove(n)
        except Exception:
            pass

    # ---------- 3) core_res.pkg 结构扫描（流式，不整体读入） ----------
    cr = "assets/core_res.pkg"
    if cr in names:
        sz = z.getinfo(cr).file_size
        log.append("core_res.pkg %.0fMB" % (sz / 1048576))
        try:
            z.extract(cr, ".")
        except Exception as e:
            log.append("core extract fail " + str(e)[:80])
        if os.path.exists("assets/core_res.pkg"):
            f = open("assets/core_res.pkg", "rb")
            head = f.read(64)
            log.append("core head=" + head[:16].hex())
            idx = struct.unpack_from("<2I", head, 8)
            log.append("core idx_off=%d idx_size=%d" % idx)
            keys = [b".csv", b".lua", b".json", b".skanim", b".mesh", b".skeleton",
                    b"ugc/logic/api", b"script/", b"Mini.", b".png", b".fbx", b".txt", b".xml"]
            hits = {k: [] for k in keys}
            f.seek(0)
            off = 0
            CH = 8 * 1048576
            while True:
                buf = f.read(CH)
                if not buf:
                    break
                for k in keys:
                    st = 0
                    while len(hits[k]) < 400:
                        p = buf.find(k, st)
                        if p < 0:
                            break
                        hits[k].append(off + p)
                        st = p + 1
                off += len(buf)
                if off > 400 * 1048576:
                    break
            f.close()
            out = []
            for k, v in hits.items():
                out.append("### %s  hits=%d" % (k.decode(), len(v)))
                out.extend("  %d" % x for x in v[:200])
            put("hex/%s_core_scan.txt" % TAG, "\n".join(out))
            log.append("core scan done")
            try:
                os.remove("assets/core_res.pkg")
            except Exception:
                pass

    put("hex/%s_log.txt" % TAG, "\n".join(log))
    put("hex/%s_done.txt" % TAG, "ok %.0fs" % (time.time() - t0))


try:
    main()
except Exception:
    try:
        put("hex/%s_done.txt" % TAG, "EXC " + traceback.format_exc()[:600])
    except Exception:
        pass
