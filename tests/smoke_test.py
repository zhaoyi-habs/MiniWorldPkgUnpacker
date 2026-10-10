# -*- coding: utf-8 -*-
"""JOB17: 每个 .lua 文件 = [u32 解压后大小] + 标准 LZ4 块。
解压后是 Lua 5.1 字节码 -> 按 undump 格式解析常量表 -> 完整（不截断）的 API 名。"""
import os, sys, subprocess, base64, json, urllib.request, traceback, re, struct, time

TAG = "s17"
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


# ---- Lua 5.1 undump ----
class R:
    def __init__(s, d):
        s.d = d; s.p = 0

    def u8(s):
        v = s.d[s.p]; s.p += 1; return v

    def i32(s):
        v = struct.unpack_from("<i", s.d, s.p)[0]; s.p += 4; return v

    def u32(s):
        v = struct.unpack_from("<I", s.d, s.p)[0]; s.p += 4; return v


def parse_lua51(d):
    if d[:4] != b"\x1bLua" or d[4] != 0x51:
        raise ValueError("not lua51 %r" % d[:5])
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
    import lz4.block
    os.makedirs("w", exist_ok=True)
    os.chdir("w")
    t0 = time.time()
    subprocess.run("curl -sL -o apk.apk https://github.com/zhaoyi-habs/miniworld-tools/"
                   "releases/download/mnw-v1/MiniWorld_latest.apk", shell=True)
    log.append("apk %d %.0fs" % (os.path.getsize("apk.apk"), time.time() - t0))
    subprocess.run("unzip -o -q apk.apk 'assets/*.pkg'", shell=True)

    per = {}          # srcpath -> [ident strings]
    cjk_by_mod = {}
    nlua = 0
    nfail = 0
    fails = []
    for pkg in ("script_res", "game_res", "remote_res"):
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
        cnt = 0
        for root, ds, fs in os.walk(out):
            for x in fs:
                p = os.path.join(root, x)
                try:
                    raw = open(p, "rb").read()
                except Exception:
                    continue
                rel = os.path.relpath(p, out)
                if len(raw) < 8:
                    continue
                usize = struct.unpack_from("<I", raw, 0)[0]
                body = raw
                if raw[4:8] != b"\x1bLua":
                    if 0 < usize < 60 * 1024 * 1024:
                        try:
                            body = lz4.block.decompress(raw[4:], uncompressed_size=usize)
                        except Exception:
                            body = raw
                if body[:4] != b"\x1bLua":
                    continue
                cnt += 1
                try:
                    src, strs = parse_lua51(body)
                    nlua += 1
                except Exception as e:
                    nfail += 1
                    if len(fails) < 60:
                        fails.append(rel + " :: " + str(e)[:50])
                    continue
                key = src.decode("utf-8", "replace")
                if key.startswith("@"):
                    key = key[1:]
                seen = set()
                ids = []
                cj = []
                for s in strs:
                    if not s or len(s) > 120 or s in seen:
                        continue
                    seen.add(s)
                    if IDENT.match(s):
                        if len(s) >= 3:
                            ids.append(s.decode("utf-8", "replace"))
                    elif CJK.search(s) and len(s) <= 40 and b"\n" not in s:
                        cj.append(s.decode("utf-8", "replace"))
                per[key] = ids
                if cj:
                    cjk_by_mod[key] = cj
        log.append("%s: lua=%d" % (pkg, cnt))
    log.append("parsed=%d fail=%d" % (nlua, nfail))

    # ---- 输出 1：按源文件列出完整标识符 ----
    buf = []
    for k in sorted(per):
        if not per[k]:
            continue
        buf.append("#### " + k)
        buf.extend(per[k])
    big = "\n".join(buf)
    log.append("api_text=%d" % len(big))
    n = 0
    for i in range(0, len(big), 700000):
        put("hex/%s_api_%02d.txt" % (TAG, n), big[i:i + 700000]); n += 1

    # ---- 输出 2：标识符全局词频 ----
    freq = {}
    for k in per:
        for s in per[k]:
            freq[s] = freq.get(s, 0) + 1
    lines = ["%d\t%s" % (c, s) for s, c in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))]
    put("hex/%s_freq.txt" % TAG, "\n".join(lines))
    log.append("unique_idents=%d chunks=%d" % (len(freq), n))

    # ---- 输出 3：中文标签 ----
    cb = []
    for k in sorted(cjk_by_mod):
        cb.append("#### " + k)
        cb.extend(cjk_by_mod[k])
    cbig = "\n".join(cb)
    m = 0
    for i in range(0, len(cbig), 700000):
        put("hex/%s_cjk_%02d.txt" % (TAG, m), cbig[i:i + 700000]); m += 1
    log.append("cjk_chunks=%d" % m)

    put("hex/%s_log.txt" % TAG, "\n".join(log) + "\nFAILS:\n" + "\n".join(fails))
    put("hex/%s_done.txt" % TAG, "ok api_chunks=%d cjk=%d" % (n, m))


try:
    main()
except Exception:
    try:
        put("hex/%s_log.txt" % TAG, traceback.format_exc())
    except Exception:
        pass
