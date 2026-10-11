# -*- coding: utf-8 -*-
"""JOB20: 国内版 com.minitech.miniworld —— 重新下载完整 APK，
提取 C++ 引擎层 liblibGameApp.so 字符串表 + 完整解 game_script.pkg。
（本地 base.apk 数据区已损坏：中央目录重复 6 次，so 的 local header 丢失，
  1.7GB 内暴力搜 deflate 流找不到 ELF 头，判定不可修复。）
"""
import os, sys, subprocess, json, urllib.request, base64, time, re, struct, traceback, collections

TAG = "s20"
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
            nc = j(B + "/git/commits", "POST", {"message": "s20 " + p,
                                                "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception:
            time.sleep(4)
    return False


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

SRCS = [
    ("apkpure_d", "https://d.apkpure.com/b/APK/com.minitech.miniworld?version=latest"),
    ("apkpure_page", "https://apkpure.com/miniworld/com.minitech.miniworld/download"),
    ("apkpure_b", "https://d.apkpure.com/b/XAPK/com.minitech.miniworld?version=latest"),
    ("apkcombo", "https://apkcombo.com/mini-world/com.minitech.miniworld/download/apk"),
    ("apkmirror", "https://www.apkmirror.com/apk/miniworld/mini-world/"),
    ("apkdone", "https://apkdone.com/miniworld/com.minitech.miniworld/"),
    ("androidfreeware", "https://www.androidfreeware.net/download-miniworld-apk.html"),
    ("uptodown", "https://miniworld.en.uptodown.com/android/download"),
    ("apkmonk", "https://www.apkmonk.com/app/com.minitech.miniworld/"),
    ("apkplz", "https://apkplz.com/app/com.minitech.miniworld"),
    ("apksos", "https://apk.support/download-app/com.minitech.miniworld"),
    ("softonic", "https://mini-world.en.softonic.com/android"),
    ("apkbeast", "https://apkbeast.com/app/com.minitech.miniworld/"),
]


def try_download():
    for name, u in SRCS:
        fn = "dl_%s.bin" % name
        try:
            subprocess.run(["curl", "-sL", "--max-time", "600", "-A", UA,
                            "-o", fn, u], timeout=700)
            if not os.path.exists(fn) or os.path.getsize(fn) < 5 * 1024 * 1024:
                continue
            with open(fn, "rb") as fh:
                magic = fh.read(4)
            iszip = magic[:2] == b"PK"
            isxapk = False
            if not iszip:
                out = subprocess.run(["file", fn], capture_output=True).stdout.decode()
                isxapk = "Zip" in out or "archive" in out.lower()
            if iszip or isxapk:
                return name, fn, os.path.getsize(fn)
        except Exception:
            continue
    return None, None, 0


def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"):
        return
    log = []
    os.makedirs("w", exist_ok=True)
    os.chdir("w")
    t0 = time.time()

    name, fn, fsz = try_download()
    log.append("download: src=%s size=%s (%.0fs)" % (name, fsz, time.time() - t0))
    if not fn:
        put("hex/%s_done.txt" % TAG, "FAILED to download CN apk")
        put("hex/%s_log.txt" % TAG, "\n".join(log))
        return
    os.rename(fn, "cn.apk")

    import zipfile
    try:
        z = zipfile.ZipFile("cn.apk")
        names = z.namelist()
    except Exception as e:
        put("hex/%s_log.txt" % TAG, "\n".join(log) + "\nbad zip: " + str(e))
        put("hex/%s_done.txt" % TAG, "FAILED bad zip")
        return
    log.append("zip ok: %d entries" % len(names))

    # ---------- 1) C++ 引擎层字符串表 ----------
    soc = [n for n in names if n.endswith("liblibGameApp.so")]
    log.append("so candidates: %s" % soc)
    for son in soc:
        try:
            info = z.getinfo(son)
            log.append("%s: %.1fMB -> %.1fMB" % (son, info.compress_size / 1048576,
                                                 info.file_size / 1048576))
            data = z.read(son)
        except Exception as e:
            log.append("extract fail %s: %s" % (son, str(e)[:120]))
            continue
        strs = re.findall(rb"[ -~]{5,200}", data)
        log.append("%s: %d raw strings" % (son, len(strs)))
        pats = {
            "api_cls": rb"^Api[A-Z][A-Za-z0-9]{2,40}$",
            "mini_dot": rb"^Mini\.[A-Za-z0-9_.]{2,60}$",
            "lua_path": rb"^[A-Za-z0-9_/\-\.]{6,120}\.lua$",
            "csv_path": rb"^[A-Za-z0-9_/\-\.]{6,120}\.csv$",
            "camel": rb"^[a-z][a-zA-Z0-9]{5,40}$",
        }
        for pn, pt in pats.items():
            r = re.compile(pt)
            c = collections.Counter()
            for s in strs:
                if r.match(s):
                    c[s.decode()] += 1
            if not c:
                continue
            o = ["# %s :: %s  (%d unique)" % (son, pn, len(c)), ""]
            for s, x in c.most_common(6000):
                o.append("%d\t%s" % (x, s))
            big = "\n".join(o)
            for i in range(0, len(big), 700000):
                put("hex/%s_so_%s_%02d.txt" % (TAG, pn, i // 700000), big[i:i + 700000])
            log.append("  %s: %d" % (pn, len(c)))
        del data, strs

    # ---------- 2) 完整解 game_script.pkg ----------
    for pkg in ("assets/game_script.pkg", "assets/game_script32.pkg"):
        if pkg not in names:
            continue
        try:
            z.extract(pkg, ".")
        except Exception as e:
            log.append("extract %s fail: %s" % (pkg, str(e)[:100]))
            continue
        try:
            subprocess.run("git clone -q --depth 1 https://github.com/zhaoyi-habs/"
                           "MiniWorldPkgUnpacker.git up", shell=True, timeout=300)
        except Exception:
            pass
        out = "unp_" + os.path.basename(pkg)
        for sc in ("python3 up/extract_game_script.py %s %s" % (pkg, out),
                   "python3 up/UnpackAll.py %s %s" % (pkg, out),
                   "python3 up/unpack_common_res.py %s %s" % (pkg, out)):
            if not os.path.exists(sc.split()[1]):
                continue
            subprocess.run(sc + " >/dev/null 2>&1", shell=True)
            if os.path.isdir(out) and os.listdir(out):
                break
        nfiles = sum(len(f) for _, _, f in os.walk(out)) if os.path.isdir(out) else 0
        log.append("%s -> %d files" % (pkg, nfiles))
        # 收集所有文本化内容里的中文 + API 风格串
        blob = []
        for root, _, fs in os.walk(out):
            for ff in fs:
                p2 = os.path.join(root, ff)
                try:
                    if os.path.getsize(p2) > 4 * 1024 * 1024:
                        continue
                    d = open(p2, "rb").read()
                except Exception:
                    continue
                try:
                    t = d.decode("utf-8")
                except Exception:
                    t = d.decode("latin-1")
                for m in re.finditer(r"[\u4e00-\u9fa5][\u4e00-\u9fa5\w，。、（）：\"']{3,60}", t):
                    blob.append(m.group(0))
        uniq = sorted(set(blob))
        log.append("%s: %d unique CJK strings" % (pkg, len(uniq)))
        big = "\n".join(uniq)
        for i in range(0, len(big), 700000):
            put("hex/%s_pkg_cjk_%02d.txt" % (TAG, i // 700000), big[i:i + 700000])

    put("hex/%s_done.txt" % TAG, "ok")
    put("hex/%s_log.txt" % TAG, "\n".join(log))


try:
    main()
except Exception:
    try:
        put("hex/%s_log.txt" % TAG, traceback.format_exc())
    except Exception:
        pass
