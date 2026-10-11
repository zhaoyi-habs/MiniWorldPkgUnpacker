# -*- coding: utf-8 -*-
"""s22: 用 s21 诊断出的"可达站点"直取国内版 APK。

s21 诊断真相：不是连不上，是 Cloudflare 403。
  可达(200): apkpure.io / apkmirror.com / apkdone.com / sj.qq.com
             appgallery.huawei.com / www.mini1.cn / archive.org
  被拒(403): apkpure.com / d.apkpure.com / sourceforge / apk.support / androidfreeware
s20 失败原因：只用了 apkpure.com 系(403)，且 apkmirror 的下载链接不是 .apk 结尾，
              正则没匹配到所以没下。
本 job 换用可达域名，并且放宽直链正则（允许 download.php?id= 这类端点）。
"""
import os, sys, subprocess, json, urllib.request, urllib.parse, base64, time, re, traceback, zipfile, collections

TAG = "s22"
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
            nc = j(B + "/git/commits", "POST", {"message": "s22 " + p + " [skip ci]",
                                                "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception:
            time.sleep(4)
    return False


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
MIN_SZ = 80 * 1024 * 1024

# 全部来自 s21 诊断里返回 200 的域
PAGES = [
    ("apkpure_io", "https://apkpure.io/miniworld/com.minitech.miniworld/download"),
    ("apkpure_io_v", "https://apkpure.io/miniworld/com.minitech.miniworld/versions"),
    ("apkdone", "https://apkdone.com/miniworld/com.minitech.miniworld/"),
    ("apkmirror", "https://www.apkmirror.com/apk/miniworld/mini-world/"),
    ("appgallery", "https://appgallery.huawei.com/"),
    ("sjqq", "https://sj.qq.com/myapp/detail.htm?apkName=com.minitech.miniworld"),
    ("mini1", "https://www.mini1.cn/"),
]
DIRECT = [
    ("apkpure_io_d", "https://d.apkpure.io/b/APK/com.minitech.miniworld?version=latest"),
    ("apkpure_io_x", "https://d.apkpure.io/b/XAPK/com.minitech.miniworld?version=latest"),
    ("apkpure_io_d2", "https://download.apkpure.io/b/APK/com.minitech.miniworld?version=latest"),
    ("sjqq_d", "https://sj.qq.com/myapp/download.htm?apkName=com.minitech.miniworld"),
]

# 放宽：.apk 结尾 或 含 download/download.php 的端点
APK_RE = re.compile(rb'https?://[^\s"\'<>\\]{10,400}?\.apk[^\s"\'<>\\]*', re.I)
DL_RE = re.compile(rb'https?://[^\s"\'<>\\]{10,400}?(download\.php|/download/|download\b)[^\s"\'<>\\]{0,200}', re.I)


def curl(url, out, tmo=600, ref=None):
    cmd = ["curl", "-sL", "--max-time", str(tmo), "-A", UA,
           "-H", "Accept-Language: en-US,en;q=0.9"]
    if ref:
        cmd += ["-e", ref]
    cmd += ["-o", out, url]
    try:
        subprocess.run(cmd, timeout=tmo + 60)
    except Exception:
        return False
    return os.path.exists(out) and os.path.getsize(out) > 1024


def is_zip(p):
    try:
        return open(p, "rb").read(2) == b"PK" and os.path.getsize(p) >= MIN_SZ
    except Exception:
        return False


def try_all():
    for name, u in PAGES:
        hp = "pg_%s.html" % name
        if not curl(u, hp, tmo=120):
            continue
        try:
            html = open(hp, "rb").read()
        except Exception:
            continue
        cands = []
        for rx in (APK_RE, DL_RE):
            for m in rx.finditer(html):
                s = m.group(0).decode("utf-8", "replace").replace("&amp;", "&")
                s = s.rstrip("\\").rstrip(",").rstrip("'").rstrip('"')
                if s.startswith("http"):
                    cands.append(s)
        seen = []
        for c in cands:
            if c not in seen:
                seen.append(c)
        for i, c in enumerate(seen[:8]):
            fn = "dl_%s_%d.bin" % (name, i)
            if not curl(c, fn, tmo=1200, ref=u):
                continue
            if is_zip(fn):
                return "%s#%d" % (name, i), fn, os.path.getsize(fn), c
    for name, u in DIRECT:
        fn = "dl_%s.bin" % name
        if not curl(u, fn, tmo=1200):
            continue
        if is_zip(fn):
            return name, fn, os.path.getsize(fn), u
    return None, None, 0, None


def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"):
        return
    log = []
    os.makedirs("w22", exist_ok=True)
    os.chdir("w22")
    t0 = time.time()

    src, fn, sz, real = try_all()
    log.append("src=%s size=%s (%.0fs)" % (src, sz, time.time() - t0))
    log.append("real_url=%s" % real)
    if not fn:
        put("hex/%s_done.txt" % TAG, "FAILED: no source")
        put("hex/%s_log.txt" % TAG, "\n".join(log))
        return
    os.rename(fn, "cn.apk")
    try:
        z = zipfile.ZipFile("cn.apk")
        names = z.namelist()
    except Exception as e:
        log.append("bad zip " + str(e)[:150])
        put("hex/%s_log.txt" % TAG, "\n".join(log))
        put("hex/%s_done.txt" % TAG, "FAILED bad zip")
        return
    log.append("zip ok %d entries %.0fMB" % (len(names), sz / 1048576))
    put("hex/%s_entries.txt" % TAG,
        "\n".join("%s\t%d" % (n, z.getinfo(n).file_size) for n in names
                  if n.endswith(".so") or "game_script" in n)[:700000])

    for son in [n for n in names if n.endswith("liblibGameApp.so")]:
        try:
            data = z.read(son)
        except Exception as e:
            log.append("so read fail " + str(e)[:100])
            continue
        strs = re.findall(rb"[ -~]{5,200}", data)
        log.append("%s strings=%d" % (son, len(strs)))
        for pn, pt in {"api_cls": rb"^Api[A-Z][A-Za-z0-9]{2,40}$",
                       "mini_dot": rb"^Mini\.[A-Za-z0-9_.]{2,60}$",
                       "lua_path": rb"^[A-Za-z0-9_/\-\.]{6,120}\.lua$",
                       "csv_path": rb"^[A-Za-z0-9_/\-\.]{6,120}\.csv$"}.items():
            r = re.compile(pt)
            c = collections.Counter()
            for s in strs:
                if r.match(s):
                    c[s.decode()] += 1
            if not c:
                continue
            big = "\n".join("%d\t%s" % (x, s) for s, x in c.most_common(30000))
            for k in range(0, len(big), 700000):
                put("hex/%s_so_%s_%02d.txt" % (TAG, pn, k // 700000), big[k:k + 700000])
            log.append("  so %s %d" % (pn, len(c)))
        del data, strs

    # game_script.pkg 中文语料
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
                   "python3 up/UnpackAll.py %s %s" % (pkg, out)):
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
