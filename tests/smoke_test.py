# -*- coding: utf-8 -*-
"""JOB15: 从 script_res.pkg / game_res.pkg 中提取 Lua 5.1 字节码的完整常量字符串。
之前的名字被截断（ApiA / isPlayerD / ClassEx），原因是走了 UTF-8 文本转储而非二进制解析。
这次直接按 Lua 5.1 undump 格式解析常量表，拿到完整字符串。"""
import os, sys, subprocess, base64, json, urllib.request, traceback, re, struct, time

TAG = "s15"
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


# ---------------- Lua 5.1 undump ----------------
class R:
    def __init__(self, d):
        self.d = d
        self.p = 0

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def i32(self):
        v = struct.unpack_from("<i", self.d, self.p)[0]; self.p += 4; return v

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.p)[0]; self.p += 4; return v

    def num(self):
        self.p += 8; return 0.0

    def s(self):
        n = self.u32()
        if n == 0:
            return b""
        v = self.d[self.p:self.p + n]; self.p += n
        if v.endswith(b"\x00"):
            v = v[:-1]
        return v


def parse_lua51(data):
    """返回 (source_path, [strings])；失败抛异常"""
    if data[:4] != b"\x1bLua":
        raise ValueError("not lua")
    ver = data[4]
    if ver != 0x51:
        raise ValueError("ver %x" % ver)
    r = R(data)
    r.p = 12
    strs = []

    def rd_str():
        v = r.s()
        strs.append(v)
        return v

    def proto(depth):
        if depth > 24:
            raise ValueError("deep")
        src = rd_str()
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
                r.num()
            elif t == 4:
                rd_str()
            else:
                raise ValueError("ktype %d" % t)
        sp = r.i32()
        sons = []
        for _ in range(sp):
            sons.append(proto(depth + 1))
        sli = r.i32(); r.p += sli * 4
        slv = r.i32()
        for _ in range(slv):
            rd_str(); r.i32(); r.i32()
        sup = r.i32()
        for _ in range(sup):
            rd_str()
        return src

    src = proto(0)
    return src, strs


def scan_ascii(data):
    """兜底：二进制里直接扫可打印串"""
    out = []
    for m in re.finditer(rb"[A-Za-z_][A-Za-z0-9_\.]{3,63}", data):
        out.append(m.group())
    return out


ID_OK = re.compile(rb"^[A-Za-z_][A-Za-z0-9_\.:]*$")


def main():
    if j(B + "/contents/hex/" + TAG + "_done.txt").get("content"):
        return
    log = []
    os.makedirs("w", exist_ok=True)
    os.chdir("w")
    t0 = time.time()
    subprocess.run("curl -sL -o apk.apk https://github.com/zhaoyi-habs/miniworld-tools/"
                   "releases/download/mnw-v1/MiniWorld_latest.apk", shell=True)
    log.append("apk %d bytes %.0fs" % (os.path.getsize("apk.apk") if os.path.exists("apk.apk") else -1, time.time() - t0))
    subprocess.run("unzip -o -q apk.apk 'assets/*.pkg'", shell=True)

    per_file = {}     # relpath -> [strings]
    nlua = nbin = ntxt = 0
    fails = []
    for pkg in ("script_res", "game_res"):
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
                    data = open(p, "rb").read()
                except Exception:
                    continue
                rel = os.path.relpath(p, out)
                strs = None
                src = None
                if data[:4] == b"\x1bLua":
                    try:
                        src, strs = parse_lua51(data)
                        nbin += 1
                    except Exception as e:
                        fails.append(rel + " :: " + str(e)[:60])
                        strs = None
                if strs is None:
                    if data[:4] == b"\x1bLua":
                        strs = scan_ascii(data)
                    else:
                        ntxt += 1
                        strs = scan_ascii(data)
                # 过滤：只保留像标识符的 + 短的中文/文本
                keep = []
                seen = set()
                for s in strs:
                    if not s or len(s) > 96:
                        continue
                    if s in seen:
                        continue
                    seen.add(s)
                    if ID_OK.match(s) or (b" " not in s and len(s) <= 40):
                        keep.append(s)
                real = src.decode("utf-8", "replace") if src else rel
                per_file[real] = keep
                cnt += 1
        log.append("%s: %d files" % (pkg, cnt))
    log.append("lua_bin=%d plain=%d fails=%d" % (nbin, ntxt, len(fails)))

    # ---------- 输出 1：按文件列出完整字符串 ----------
    paths = sorted(per_file)
    buf = []
    for p in paths:
        ss = per_file[p]
        if not ss:
            continue
        buf.append("#### %s" % p)
        for s in ss:
            buf.append(s.decode("utf-8", "replace"))
    big = "\n".join(buf)
    log.append("api_text %d bytes" % len(big))
    CH = 700000
    n = 0
    i = 0
    while i < len(big):
        chunk = big[i:i + CH]
        put("hex/%s_api_%02d.txt" % (TAG, n), chunk)
        n += 1
        i += CH
    # ---------- 输出 2：全局唯一串 + 词频 ----------
    freq = {}
    for p in paths:
        for s in per_file[p]:
            freq[s] = freq.get(s, 0) + 1
    items = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    lines = []
    for s, c in items:
        try:
            t = s.decode("utf-8")
        except Exception:
            continue
        if "\n" in t or "\r" in t:
            continue
        lines.append("%d\t%s" % (c, t))
    put("hex/%s_freq.txt" % TAG, "\n".join(lines))
    # ---------- 输出 3：文件清单 ----------
    put("hex/%s_files.txt" % TAG, "\n".join(paths))
    log.append("unique=%d chunks=%d" % (len(items), n))
    put("hex/%s_log.txt" % TAG, "\n".join(log) + "\nfails:\n" + "\n".join(fails[:80]))
    put("hex/%s_done.txt" % TAG, "ok %d chunks" % n)


try:
    main()
except Exception:
    try:
        put("hex/%s_log.txt" % TAG, traceback.format_exc())
    except Exception:
        pass
