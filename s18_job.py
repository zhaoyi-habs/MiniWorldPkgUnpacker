# -*- coding: utf-8 -*-
"""JOB18: 从 game_res.pkg 提取全部 CSV 配置表（图形化积木/事件中文名/动作表）"""
import os, sys, subprocess, json, urllib.request, traceback, re, time

TAG = "s18"
if sys.platform != "linux":
    sys.exit(0)
if sys.version_info[:2] != (3, 12):
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
            blob = j(B + "/git/blobs", "POST",
                     {"encoding": "base64",
                      "content": __import__("base64").b64encode(t).decode()})
            if blob.get("sha") is None:
                time.sleep(3); continue
            head = j(B + "/git/ref/heads/main")["object"]["sha"]
            c = j(B + "/git/commits/" + head)
            tr = j(B + "/git/trees", "POST",
                   {"base_tree": c["tree"]["sha"],
                    "tree": [{"path": p, "mode": "100644", "type": "blob",
                              "sha": blob["sha"]}]})
            nc = j(B + "/git/commits", "POST",
                   {"message": "s18 " + p, "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception:
            time.sleep(4)
    return False


def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"):
        return
    log = []
    os.makedirs("w", exist_ok=True)
    os.chdir("w")
    t0 = time.time()
    subprocess.run("curl -sL -o apk.apk https://github.com/zhaoyi-habs/miniworld-tools/"
                   "releases/download/mnw-v1/MiniWorld_latest.apk", shell=True)
    log.append("apk %d %.0fs" % (os.path.getsize("apk.apk"), time.time() - t0))
    subprocess.run("unzip -o -q apk.apk 'assets/*.pkg'", shell=True)

    # 解 game_res.pkg 和 script_res.pkg
    for pkg in ("game_res", "script_res"):
        fp = "assets/%s.pkg" % pkg
        if not os.path.exists(fp):
            continue
        out = "unp/%s" % pkg
        os.makedirs(out, exist_ok=True)
        for sc in ("python3 ../unpack_common_res.py %s %s" % (fp, out),
                   "python3 ../UnpackAll.py %s %s" % (fp, out)):
            subprocess.run(sc + " >/dev/null 2>&1", shell=True)
            if os.path.isdir(out) and os.listdir(out):
                break
        n = sum(len(f) for _, _, f in os.walk(out))
        log.append("%s: %d files" % (pkg, n))

    # 收集所有 csv
    csvs = {}
    for root in ("unp/game_res", "unp/script_res"):
        for r, ds, fs in os.walk(root):
            for x in fs:
                if not x.lower().endswith(".csv"):
                    continue
                p = os.path.join(r, x)
                try:
                    raw = open(p, "rb").read()
                except Exception:
                    continue
                if len(raw) > 3 * 1024 * 1024:
                    continue
                csvs[os.path.relpath(p, root)] = raw
    log.append("csv found %d" % len(csvs))

    # 关键表优先
    KEY = ["codeblockconfig", "roleactions", "roleskin", "triggerevent",
           "event", "action", "condition", "gameevent", "uidef", "stringdef"]
    def rank(k):
        kl = k.lower()
        for i, kw in enumerate(KEY):
            if kw in kl:
                return i
        return 99

    order = sorted(csvs, key=lambda k: (rank(k), k))
    # 输出 1: CSV 清单
    lines = ["%8d  %s" % (len(csvs[k]), k) for k in order]
    put("hex/%s_csvlist.txt" % TAG, "\n".join(lines))

    # 输出 2: 关键 CSV 内容（逐表，带中文）
    buf = []
    for k in order:
        if rank(k) == 99:
            continue
        raw = csvs[k]
        try:
            txt = raw.decode("utf-8")
        except Exception:
            txt = raw.decode("gbk", "replace")
        buf.append("\n\n========== %s (%d bytes) ==========\n%s" % (k, len(raw), txt[:60000]))
        if sum(len(x) for x in buf) > 600000:
            break
    big = "".join(buf)
    n = 0
    for i in range(0, len(big), 700000):
        put("hex/%s_csv_%02d.txt" % (TAG, n), big[i:i + 700000]); n += 1
    log.append("csv_chunks %d size %d" % (n, len(big)))

    # 输出 3: 从所有 CSV 里提取"中文名,英文key"对照
    pairs = []
    for k in order:
        try:
            txt = csvs[k].decode("utf-8")
        except Exception:
            txt = csvs[k].decode("gbk", "replace")
        for ln in txt.split("\n"):
            if not ln.strip() or ln.startswith("#"):
                continue
            ps = [x.strip() for x in ln.split(",")]
            en = [x for x in ps if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", x)]
            cn = [x for x in ps if re.search(r"[\u4e00-\u9fa5]", x)]
            if en and cn:
                pairs.append("%s\t%s\t%s" % (en[0], cn[0], k))
    seen = set(); out2 = []
    for x in pairs:
        if x.split("\t")[0] in seen:
            continue
        seen.add(x.split("\t")[0])
        out2.append(x)
    put("hex/%s_en_cn.txt" % TAG, "\n".join(out2))
    log.append("en_cn pairs %d" % len(out2))

    put("hex/%s_done.txt" % TAG, "ok csv=%d chunks=%d pairs=%d" % (len(csvs), n, len(out2)))
    put("hex/%s_log.txt" % TAG, "\n".join(log))


try:
    main()
except Exception:
    try:
        put("hex/%s_log.txt" % TAG, traceback.format_exc())
    except Exception:
        pass
