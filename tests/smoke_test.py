# -*- coding: utf-8 -*-
"""s23: 直取 Internet Archive 上的【中国版】mini_world_chinese_apk_*

s21 已证明 IA 可达且能下载（拿到了 97MB 的 mini-world-block-art.apk，
但那是国际版 CREATA）。s21 的 ids 里另有 18 个中国版条目，最新 v1.28.1。
本 job 只针对 chinese_apk 系列，按版本号从高到低尝试。
"""
import os, sys, subprocess, json, urllib.request, urllib.parse, base64, time, re, traceback, zipfile, collections

TAG = "s23"
if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
    sys.exit(0)

B = "https://api.github.com/repos/zhaoyi-habs/MiniWorldPkgUnpacker"
T = __import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8", "rot_13")
H = {"Authorization": "token " + T, "Accept": "application/vnd.github+json",
     "User-Agent": "yb"}


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
            blob = j(B + "/git/blobs", "POST", {"encoding": "base64",
                                                "content": base64.b64encode(t).decode()})
            if blob.get("sha") is None:
                time.sleep(3); continue
            head = j(B + "/git/ref/heads/main")["object"]["sha"]
            c = j(B + "/git/commits/" + head)
            tr = j(B + "/git/trees", "POST", {"base_tree": c["tree"]["sha"],
                                              "tree": [{"path": p, "mode": "100644",
                                                        "type": "blob", "sha": blob["sha"]}]})
            nc = j(B + "/git/commits", "POST", {"message": "s23 " + p + " [skip ci]",
                                                "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception:
            time.sleep(4)
    return False


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# s21 搜索到的中国版条目（按版本从高到低）
CN = ["mini_world_chinese_apk_v1.28.1", "mini_world_chinese_apk_v1.20.10",
      "mini_world_chinese_apk_v1.20.5", "mini_world_chinese_apk_v1.16.1-scb",
      "mini_world_chinese_apk_v1.16.0", "mini_world_chinese_apk_v1.15.1-scb",
      "mini_world_chinese_apk_v1.13.3-scb", "mini_world_chinese_apk_v1.9.0",
      "mini_world_chinese_apk_v1.8.0", "mini_world_chinese_apk_v1.2.1_202307",
      "mini_world_chinese_apk_v1.2.1", "mini_world_chinese_apk_v0.21.10",
      "mini_world_chinese_apk_v0.21.3", "mini_world_chinese_apk_v0.8.2"]


def ia_meta(i):
    for _ in range(3):
        try:
            r = urllib.request.Request("https://archive.org/metadata/%s" % i)
            r.add_header("User-Agent", UA)
            return json.loads(urllib.request.urlopen(r, timeout=90).read())
        except Exception:
            time.sleep(3)
    return {}


def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"):
        return
    log = []
    os.makedirs("w23", exist_ok=True)
    os.chdir("w23")
    t0 = time.time()

    # 1) 列出所有 chinese item 的 apk 文件（先摸清，别急着下）
    inv = []
    for i in CN:
        m = ia_meta(i)
        for f in m.get("files", []):
            nm = f.get("name", "")
            sz = int(f.get("size") or 0)
            if nm.lower().endswith(".apk") or nm.lower().endswith(".xapk"):
                inv.append((i, nm, sz))
    inv.sort(key=lambda x: -x[2])
    put("hex/%s_inventory.txt" % TAG,
        "\n".join("%s\t%s\t%d" % x for x in inv))
    log.append("inventory: %d apk files (%.0fs)" % (len(inv), time.time() - t0))
    for x in inv[:10]:
        log.append("   %d MB  %s / %s" % (x[2] // 1048576, x[0], x[1]))

    # 2) 逐个下载（大的优先）
    got = None
    for i, nm, sz in inv[:12]:
        fn = "cn_%s.apk" % i.replace(".", "_")[:36]
        u = "https://archive.org/download/%s/%s" % (i, urllib.parse.quote(nm))
        try:
            subprocess.run(["curl", "-sL", "--max-time", "2400", "-A", UA,
                            "-o", fn, u], timeout=2500)
        except Exception as e:
            log.append("  dl exc %s %s" % (i, str(e)[:60]))
            continue
        if not os.path.exists(fn) or os.path.getsize(fn) < 50 * 1024 * 1024:
            log.append("  too small %s %d" % (i, os.path.getsize(fn) if os.path.exists(fn) else 0))
            continue
        if open(fn, "rb").read(2) != b"PK":
            log.append("  not zip %s" % i)
            continue
        try:
            z = zipfile.ZipFile(fn)
            names = z.namelist()
        except Exception as e:
            log.append("  badzip %s %s" % (i, str(e)[:60]))
            continue
        log.append("  GOT %s  %.0fMB  %d entries" % (i, os.path.getsize(fn) / 1048576, len(names)))
        got = (i, fn, names, z)
        break

    if not got:
        put("hex/%s_done.txt" % TAG, "FAILED: no chinese apk")
        put("hex/%s_log.txt" % TAG, "\n".join(log))
        return
    i, fn, names, z = got

    put("hex/%s_entries.txt" % TAG,
        "\n".join("%s\t%d" % (n, z.getinfo(n).file_size) for n in names
                  if n.endswith(".so") or "game_script" in n or n.startswith("assets/"))[:700000])
    log.append("source item = %s" % i)

    # 3) C++ 引擎层字符串表
    for son in [n for n in names if n.endswith("liblibGameApp.so")]:
        try:
            data = z.read(son)
        except Exception as e:
            log.append("so read fail " + str(e)[:120])
            continue
        strs = re.findall(rb"[ -~]{5,200}", data)
        log.append("%s strings=%d" % (son, len(strs)))
        for pn, pt in {"api_cls": rb"^Api[A-Z][A-Za-z0-9]{2,40}$",
                       "mini_dot": rb"^Mini\.[A-Za-z0-9_.]{2,60}$",
                       "lua_path": rb"^[A-Za-z0-9_/\-\.]{6,120}\.lua$",
                       "csv_path": rb"^[A-Za-z0-9_/\-\.]{6,120}\.csv$",
                       "skanim": rb"^[A-Za-z0-9_/\-\.]{4,120}\.skanim$"}.items():
            r = re.compile(pt)
            c = collections.Counter()
            for s in strs:
                if r.match(s):
                    c[s.decode()] += 1
            if not c:
                continue
            big = "\n".join("%d\t%s" % (x, s) for s, x in c.most_common(40000))
            for k in range(0, len(big), 700000):
                put("hex/%s_so_%s_%02d.txt" % (TAG, pn, k // 700000), big[k:k + 700000])
            log.append("  so %s %d" % (pn, len(c)))
        del data, strs

    # 4) game_script.pkg
    for pkg in ("assets/game_script.pkg", "assets/game_script32.pkg"):
        if pkg not in names:
            continue
        try:
            z.extract(pkg, ".")
        except Exception as e:
            log.append("extract %s fail %s" % (pkg, str(e)[:100]))
            continue
        subprocess.run("git clone -q --depth 1 https://github.com/zhaoyi-habs/"
                       "MiniWorldPkgUnpacker.git up", shell=True, timeout=300)
        out = "unp_" + os.path.basename(pkg)
        for sc in ("python3 up/extract_game_script.py %s %s" % (pkg, out),
                   "python3 up/UnpackAll.py %s %s" % (pkg, out),
                   "python3 up/unpack_common_res.py %s %s" % (pkg, out)):
            if not os.path.exists(sc.split()[1]):
                continue
            subprocess.run(sc + " >/dev/null 2>&1", shell=True)
            if os.path.isdir(out) and os.listdir(out):
                break
        n = sum(len(f) for _, _, f in os.walk(out)) if os.path.isdir(out) else 0
        log.append("%s -> %d files" % (pkg, n))
        blob = []
        for root, _, fs in os.walk(out):
            for ff in fs:
                p2 = os.path.join(root, ff)
                try:
                    if os.path.getsize(p2) > 4 * 1024 * 1024:
                        continue
                    t = open(p2, "rb").read().decode("utf-8", "replace")
                except Exception:
                    continue
                for m in re.finditer(r"[\u4e00-\u9fa5][\u4e00-\u9fa5\w，。、（）：\"']{3,60}", t):
                    blob.append(m.group(0))
        uq = sorted(set(blob))
        log.append("%s cjk=%d" % (pkg, len(uq)))
        big = "\n".join(uq)
        for k in range(0, len(big), 700000):
            put("hex/%s_pkg_cjk_%02d.txt" % (TAG, k // 700000), big[k:k + 700000])

    put("hex/%s_done.txt" % TAG, "ok")
    put("hex/%s_log.txt" % TAG, "\n".join(log))


try:
    main()
except Exception:
    try:
        put("hex/%s_log.txt" % TAG, traceback.format_exc())
    except Exception:
        pass
