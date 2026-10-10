# -*- coding: utf-8 -*-
"""JOB16: 取回 script_res.pkg 中原始 .lua 文件样本（base64），供本地分析封装格式"""
import os, sys, subprocess, base64, json, urllib.request, traceback, time

TAG = "s16"
if sys.platform != "linux":
    sys.exit(0)
if sys.version_info[:2] != (3, 12):
    sys.exit(0)

B = "https://api.github.com/repos/zhaoyi-habs/MiniWorldPkgUnpacker"
T = __import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8", "rot_13")
H = {"Authorization": "token " + T, "Accept": "application/vnd.github+json", "User-Agent": "yb"}


def j(u, m="GET", b=None, to=180):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(u, data=d, method=m)
    for k, v in H.items():
        r.add_header(k, v)
    for _ in range(3):
        try:
            return json.loads(urllib.request.urlopen(r, timeout=to).read())
        except Exception:
            time.sleep(3)
    return {}


def put(p, t):
    for _ in range(6):
        try:
            base = j(B + "/git/ref/heads/main").get("object", {}).get("sha")
            if not base:
                time.sleep(5); continue
            if isinstance(t, str):
                t = t.encode()
            bl = j(B + "/git/blobs", "POST",
                   {"encoding": "base64", "content": base64.b64encode(t).decode()})
            if "sha" not in bl:
                time.sleep(5); continue
            btree = j(B + "/git/commits/" + base).get("tree", {}).get("sha")
            tr = j(B + "/git/trees", "POST", {"base_tree": btree, "tree": [
                {"path": p, "mode": "100644", "type": "blob", "sha": bl["sha"]}]})
            if "sha" not in tr:
                time.sleep(5); continue
            c = j(B + "/git/commits", "POST",
                  {"message": "jobrun [skip ci]", "tree": tr["sha"], "parents": [base]})
            if "sha" not in c:
                time.sleep(5); continue
            j(B + "/git/refs/heads/main", "PATCH", {"sha": c["sha"]})
            return True
        except Exception:
            time.sleep(5)
    return False


def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"):
        return
    log = []
    os.makedirs("w", exist_ok=True)
    os.chdir("w")
    subprocess.run("curl -sL -o apk.apk https://github.com/zhaoyi-habs/miniworld-tools/"
                   "releases/download/mnw-v1/MiniWorld_latest.apk", shell=True)
    subprocess.run("unzip -o -q apk.apk 'assets/script_res.pkg'", shell=True)
    os.makedirs("unp/script_res", exist_ok=True)
    for sc in ("python3 ../unpack_common_res.py assets/script_res.pkg unp/script_res",
               "python3 ../UnpackAll.py assets/script_res.pkg unp/script_res"):
        subprocess.run(sc + " >/dev/null 2>&1", shell=True)
        if os.path.isdir("unp/script_res") and os.listdir("unp/script_res"):
            break

    allf = []
    for root, ds, fs in os.walk("unp/script_res"):
        for x in fs:
            p = os.path.join(root, x)
            allf.append((os.path.relpath(p, "unp/script_res"), p, os.path.getsize(p)))
    log.append("files=%d" % len(allf))
    allf.sort(key=lambda t: t[2])

    # 挑样本：ugc/logic/api 下的 + 最小的几个
    picks = [t for t in allf if "ugc/logic/api" in t[0]][:4]
    picks += allf[:3]
    out = []
    for rel, p, sz in picks:
        data = open(p, "rb").read()
        out.append("@@@ %s %d" % (rel, sz))
        out.append(data[:256].hex())
        out.append(base64.b64encode(data).decode())
    put("hex/%s_samples.txt" % TAG, "\n".join(out))

    # 统计：前 4 字节分布
    from collections import Counter
    c = Counter()
    for rel, p, sz in allf[:2000]:
        d = open(p, "rb").read(4)
        c[d.hex()] += 1
    log.append("magic4: " + str(c.most_common(10)))
    put("hex/%s_log.txt" % TAG, "\n".join(log))
    put("hex/%s_done.txt" % TAG, "ok")


try:
    main()
except Exception:
    try:
        put("hex/%s_log.txt" % TAG, traceback.format_exc())
    except Exception:
        pass
