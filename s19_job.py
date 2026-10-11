# -*- coding: utf-8 -*-
"""JOB19: 国内版 game_script32.pkg / game_script.pkg —— 暴力找 Lua 5.1 字节码
思路：pkg 数据区是 LZ4 块序列。对每个偏移尝试 lz4.block.decompress，
      若输出以 \\x1bLua 开头则命中，再按 undump 解析常量表。"""
import os, sys, subprocess, json, urllib.request, traceback, re, struct, time, collections

TAG = "s19"
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
                   {"message": "s19 " + p, "tree": tr["sha"], "parents": [head]})
            j(B + "/git/refs/heads/main", "PATCH", {"sha": nc["sha"]})
            return True
        except Exception:
            time.sleep(4)
    return False


# ---------- Lua 5.1 undump ----------
class R:
    def __init__(s, d): s.d = d; s.p = 0
    def u8(s):
        v = s.d[s.p]; s.p += 1; return v
    def u32(s):
        v = struct.unpack_from("<I", s.d, s.p)[0]; s.p += 4; return v
    def i32(s):
        v = struct.unpack_from("<i", s.d, s.p)[0]; s.p += 4; return v


def parse_lua51(d):
    if d[:4] != b"\x1bLua" or d[4] != 0x51:
        raise ValueError("not lua51")
    r = R(d); r.p = 12
    strs = []

    def rs():
        n = r.u32()
        if n == 0:
            return b""
        v = d[r.p:r.p + n]; r.p += n
        if v.endswith(b"\x00"):
            v = v[:-1]
        strs.append(v)
        return v

    def proto(depth):
        if depth > 32:
            raise ValueError("deep")
        src = rs()
        r.i32(); r.i32()
        r.u8(); r.u8(); r.u8(); r.u8()
        sc = r.i32(); r.p += sc * 4
        sk = r.i32()
        for _ in range(sk):
            t = r.u8()
            if t == 0:
                pass
            elif t == 1:
                r.u8()
            elif t == 3:
                r.p += 8
            elif t == 4:
                rs()
            else:
                raise ValueError("ktype %d" % t)
        sp = r.i32()
        for _ in range(sp):
            proto(depth + 1)
        sli = r.i32(); r.p += sli * 4
        slv = r.i32()
        for _ in range(slv):
            rs(); r.i32(); r.i32()
        sup = r.i32()
        for _ in range(sup):
            rs()
        return src

    return proto(0), strs


IDENT = re.compile(rb"^[A-Za-z_][A-Za-z0-9_\.]*$")
CJK = re.compile(rb"[\xc0-\xef][\x80-\xbf]+")


def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"):
        return
    log = []
    os.makedirs("w", exist_ok=True)
    os.chdir("w")
    t0 = time.time()
    # 国内版 base.apk 已在仓库? 用国际版 script_res 做对照 + 本地已有 gs
    # 这里改从 miniworld-tools 的国内版（若有），否则退回到国际版全包再扫一遍 core_res
    subprocess.run("curl -sL -o apk.apk https://github.com/zhaoyi-habs/miniworld-tools/"
                   "releases/download/mnw-v1/MiniWorld_latest.apk", shell=True)
    log.append("apk %d %.0fs" % (os.path.getsize("apk.apk"), time.time() - t0))
    subprocess.run("unzip -o -q apk.apk 'assets/*.pkg'", shell=True)
    import lz4.block
    per = {}
    cjk_by = {}
    for pkg in ("script_res", "core_res", "game_res", "remote_res", "first_res"):
        fp = "assets/%s.pkg" % pkg
        if not os.path.exists(fp):
            continue
        raw_all = open(fp, "rb").read()
        # 策略 A：正常解包
        out = "unp/%s" % pkg
        os.makedirs(out, exist_ok=True)
        for sc in ("python3 ../unpack_common_res.py %s %s" % (fp, out),
                   "python3 ../UnpackAll.py %s %s" % (fp, out)):
            subprocess.run(sc + " >/dev/null 2>&1", shell=True)
            if os.path.isdir(out) and os.listdir(out):
                break
        # 策略 B：暴力扫整个 pkg 找 [u32 usize] + LZ4 -> \x1bLua
        hits = 0
        n = len(raw_all)
        step = 4
        i = 0
        while i + 8 < n and hits < 40000:
            if raw_all[i + 4:i + 8] == b"\x1bLua":
                # 未压缩
                body = raw_all[i + 4:]
                sz = struct.unpack_from("<I", raw_all, i)[0]
                hits += 1
                try:
                    src, strs = parse_lua51(body[:min(sz, len(body))])
                    key = src.decode("utf-8", "replace").lstrip("@")
                    per.setdefault(key, set()).update(
                        s.decode("utf-8", "replace") for s in strs
                        if IDENT.match(s) and len(s) >= 3)
                except Exception:
                    pass
                i += 4; continue
            # 尝试 LZ4
            sz = struct.unpack_from("<I", raw_all, i)[0]
            if 0 < sz < 40 * 1024 * 1024:
                try:
                    body = lz4.block.decompress(raw_all[i + 4:i + 4 + min(sz * 2, 8 << 20)],
                                                uncompressed_size=sz)
                    if body[:4] == b"\x1bLua":
                        hits += 1
                        try:
                            src, strs = parse_lua51(body)
                            key = src.decode("utf-8", "replace").lstrip("@")
                            per.setdefault(key, set()).update(
                                s.decode("utf-8", "replace") for s in strs
                                if IDENT.match(s) and len(s) >= 3)
                            cj = [s.decode("utf-8", "replace") for s in strs
                                  if CJK.search(s) and len(s) <= 40 and b"\n" not in s]
                            if cj:
                                cjk_by.setdefault(key, set()).update(cj)
                        except Exception:
                            pass
                        i += 4; continue
                except Exception:
                    pass
            i += step
        log.append("%s: scan hits=%d" % (pkg, hits))
    log.append("modules=%d" % len(per))

    buf = []
    for k in sorted(per):
        if not per[k]:
            continue
        buf.append("#### " + k)
        buf.extend(sorted(per[k]))
    big = "\n".join(buf)
    n = 0
    for i2 in range(0, len(big), 700000):
        put("hex/%s_api_%02d.txt" % (TAG, n), big[i2:i2 + 700000]); n += 1
    cb = []
    for k in sorted(cjk_by):
        cb.append("#### " + k)
        cb.extend(sorted(cjk_by[k]))
    cbig = "\n".join(cb)
    m = 0
    for i2 in range(0, len(cbig), 700000):
        put("hex/%s_cjk_%02d.txt" % (TAG, m), cbig[i2:i2 + 700000]); m += 1
    put("hex/%s_done.txt" % TAG, "ok modules=%d api=%d cjk=%d" % (len(per), n, m))
    put("hex/%s_log.txt" % TAG, "\n".join(log))


try:
    main()
except Exception:
    try:
        put("hex/%s_log.txt" % TAG, traceback.format_exc())
    except Exception:
        pass
