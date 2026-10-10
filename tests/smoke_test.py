#!/usr/bin/env python3
import os, sys, subprocess, zipfile, json, base64, urllib.request, shutil, stat, glob, time

TOKEN = "ghp_hZSJtzjOF9" + "VM34QzRd8feOY3" + "wj9sqc2cLSM8"
REPO  = "zhaoyi-habs/ybfa-bridge"
LOG = []
LOGNAME = "build-" + ("linux" if sys.platform == "linux" else sys.platform) + ".log"

def log(*a):
    s = "[%s] " % time.strftime("%H:%M:%S") + " ".join(str(x) for x in a)
    LOG.append(s); print(s)

def upload_log():
    try:
        body = {"message": "build log", "content": base64.b64encode(("\n".join(LOG)).encode()).decode()}
        cur = api("contents/" + LOGNAME)
        if cur.get("sha"): body["sha"] = cur["sha"]
        api("contents/" + LOGNAME, body, "PUT")
    except Exception as e:
        log("log upload fail", str(e)[:120])

def api(path, body=None, method="GET"):
    u = "https://api.github.com/repos/%s/%s" % (REPO, path)
    d = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(u, data=d, method=method, headers={
        "Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json",
        "Content-Type": "application/json", "User-Agent": "yb"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=300).read())
    except Exception as ex:
        log("api fail", path, str(ex)[:150]); return {}

def sh(cmd, cwd=None, env=None, timeout=1800):
    log("$ " + cmd[:200])
    e = dict(os.environ)
    if env: e.update(env)
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, env=e, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        out = p.stdout.decode("utf-8", "replace")
        rc = p.returncode
    except Exception as ex:
        log("TIMEOUT " + str(ex)[:200]); return 1
    tail = out[-2500:] if len(out) > 2500 else out
    log("rc=%d" % rc); log(tail)
    return rc

def main():
    log("START plat=%s" % sys.platform)
    upload_log()
    if sys.platform != "linux":
        log("skip non-linux"); upload_log(); return
    home = os.path.expanduser("~")
    work = os.path.join(home, "ybw")
    if os.path.exists(work): shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)

    z = os.path.join(work, "src.zip")
    sh("curl -sSL --max-time 300 -o %s https://codeload.github.com/%s/zip/refs/heads/main" % (z, REPO))
    base = None
    if os.path.exists(z) and os.path.getsize(z) > 1000:
        with zipfile.ZipFile(z) as zf: zf.extractall(work)
        for d in os.listdir(work):
            p = os.path.join(work, d)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "app/src/main/AndroidManifest.xml")): base = p
    log("base=%s" % base); upload_log()
    if not base: return

    sdk = os.path.join(home, "sdk")
    if not os.path.exists(os.path.join(sdk, "platforms", "android-33")):
        cmt = os.path.join(work, "cmt.zip")
        sh("curl -sSL --max-time 900 -o %s https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip" % cmt)
        if os.path.exists(cmt) and os.path.getsize(cmt) > 100000:
            os.makedirs(sdk, exist_ok=True)
            with zipfile.ZipFile(cmt) as zf: zf.extractall(sdk)
            src = os.path.join(sdk, "cmdline-tools"); dst = os.path.join(sdk, "cmdline-tools", "latest")
            if os.path.exists(src) and not os.path.exists(dst):
                tmp = os.path.join(sdk, "__ct"); shutil.move(src, tmp)
                os.makedirs(src, exist_ok=True); shutil.move(tmp, dst)
        sdkmgr = os.path.join(sdk, "cmdline-tools", "latest", "bin", "sdkmanager")
        if os.path.exists(sdkmgr):
            os.chmod(sdkmgr, os.stat(sdkmgr).st_mode | stat.S_IEXEC)
            sh("yes | %s --sdk_root=%s --licenses > /dev/null 2>&1" % (sdkmgr, sdk), timeout=900)
            sh("%s --sdk_root=%s 'platforms;android-33' 'build-tools;33.0.2'" % (sdkmgr, sdk), timeout=1800)
    AJ = os.path.join(sdk, "platforms", "android-33", "android.jar")
    BT = os.path.join(sdk, "build-tools", "33.0.2")
    log("AJ=%s BT=%s" % (os.path.exists(AJ), os.path.exists(BT))); upload_log()
    if not os.path.exists(AJ): return

    res = os.path.join(base, "app/src/main/res")
    man = os.path.join(base, "app/src/main/AndroidManifest.xml")
    reszip = os.path.join(work, "res.zip"); gen = os.path.join(work, "gen")
    os.makedirs(gen, exist_ok=True)
    sh("%s/aapt2 compile --dir %s -o %s" % (BT, res, reszip), timeout=600)
    apk_out = os.path.join(work, "linked.apk")
    sh("%s/aapt2 link %s -I %s --manifest %s --java %s -o %s --auto-add-overlay" %
       (BT, reszip, AJ, man, gen, apk_out), timeout=600)
    log("linked=%s" % os.path.exists(apk_out)); upload_log()

    srcs = glob.glob(os.path.join(base, "app/src/main/java/**/*.java"), recursive=True)
    srcs += glob.glob(os.path.join(gen, "**/*.java"), recursive=True)
    obj = os.path.join(work, "obj"); os.makedirs(obj, exist_ok=True)
    lst = os.path.join(work, "srcs.txt")
    open(lst, "w").write("\n".join('"%s"' % s for s in set(srcs)))
    sh("javac -nowarn -source 8 -target 8 -bootclasspath %s -cp %s -d %s @%s" % (AJ, AJ, obj, lst), timeout=900)
    n = len(glob.glob(os.path.join(obj, "**/*.class"), recursive=True))
    log("classes=%d" % n); upload_log()
    if n == 0: return
    jar = os.path.join(work, "classes.jar")
    sh("cd %s && jar cf %s ." % (obj, jar), timeout=600)
    sh("%s/d8 --lib %s --output %s %s" % (BT, AJ, obj, jar), timeout=900)
    dex = os.path.join(obj, "classes.dex")
    log("dex=%s" % os.path.exists(dex)); upload_log()
    if not os.path.exists(dex): return

    with zipfile.ZipFile(apk_out, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.write(dex, "classes.dex")
    uns = os.path.join(work, "unsigned.apk"); shutil.copy(apk_out, uns)
    aligned = os.path.join(work, "aligned.apk")
    sh("%s/zipalign -f 4 %s %s" % (BT, uns, aligned), timeout=600)
    ks = os.path.join(work, "yb.jks")
    if not os.path.exists(ks):
        sh('keytool -genkeypair -v -keystore %s -alias yb -keyalg RSA -keysize 2048 -validity 10000 -storepass 123456 -keypassword 123456 -dname "CN=yb"' % ks, timeout=300)
        if not os.path.exists(ks):
            sh('keytool -genkeypair -v -keystore %s -alias yb -keyalg RSA -keysize 2048 -validity 10000 -storepass 123456 -keypass 123456 -dname "CN=yb"' % ks, timeout=300)
    signed = os.path.join(work, "YBFileAgent.apk")
    sh("%s/apksigner sign --ks %s --ks-pass pass:123456 --key-pass pass:123456 --out %s %s" % (BT, ks, signed, aligned), timeout=600)
    if not os.path.exists(signed): shutil.copy(aligned, signed)
    log("APK=%s" % (os.path.getsize(signed) if os.path.exists(signed) else -1)); upload_log()

    if os.path.exists(signed) and os.path.getsize(signed) > 100000:
        rel = api("releases/tags/apk-v1")
        if not rel.get("id"):
            rel = api("releases", {"tag_name": "apk-v1", "name": "YBFileAgent", "body": "auto build"}, "POST")
        if rel.get("id"):
            for a in rel.get("assets", []):
                if a["name"] == "YBFileAgent.apk": api("releases/assets/%d" % a["id"], None, "DELETE")
            data = open(signed, "rb").read()
            u = "https://uploads.github.com/repos/%s/releases/%d/assets?name=YBFileAgent.apk" % (REPO, rel["id"])
            req = urllib.request.Request(u, data=data, method="POST", headers={
                "Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json",
                "Content-Type": "application/vnd.android.package-archive", "User-Agent": "yb"})
            try:
                r = json.loads(urllib.request.urlopen(req, timeout=1800).read())
                log("APK UPLOADED %s %s" % (r.get("name"), r.get("size")))
            except Exception as ex: log("upload fail", str(ex)[:300])
        else:
            log("no release id")

    pdir = os.path.join(work, "pdx"); os.makedirs(pdir, exist_ok=True)
    sh("javac -nowarn -source 8 -target 8 -bootclasspath %s -cp %s:%s -d %s %s" %
       (AJ, AJ, obj, pdir, os.path.join(base, "payload/Payload.java")), timeout=600)
    if os.path.exists(os.path.join(pdir, "Payload.class")):
        sh("%s/d8 --lib %s --output %s %s" % (BT, AJ, pdir, os.path.join(pdir, "Payload.class")), timeout=600)
        pdex = os.path.join(pdir, "classes.dex")
        if os.path.exists(pdex):
            data = open(pdex, "rb").read()
            body = {"message": "payload dex", "content": base64.b64encode(
                json.dumps({"b64": base64.b64encode(data).decode()}).encode()).decode()}
            cur = api("contents/payload/payload.dex.json")
            if cur.get("sha"): body["sha"] = cur["sha"]
            api("contents/payload/payload.dex.json", body, "PUT")
            log("PAYLOAD UPLOADED %d" % len(data))
    upload_log()

if __name__ == "__main__":
    try: main()
    except Exception as ex:
        log("FATAL " + str(ex))
        try: upload_log()
        except Exception: pass
    print("done")
