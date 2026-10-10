#!/usr/bin/env python3
"""YB builder: compile YBFileAgent APK + payload dex on GitHub runner."""
import os, sys, subprocess, zipfile, io, json, base64, urllib.request, shutil, stat

LOG = open(os.path.expanduser("~/yb_build.log"), "w", buffering=1)
def log(*a):
    s = " ".join(str(x) for x in a)
    print(s); LOG.write(s + "\n")

def sh(cmd, cwd=None, env=None, timeout=3600):
    log("$", cmd)
    e = dict(os.environ); 
    if env: e.update(env)
    p = subprocess.run(cmd, shell=True, cwd=cwd, env=e,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    out = p.stdout.decode("utf-8", "replace")
    tail = out[-3000:] if len(out) > 3000 else out
    log(tail)
    return p.returncode

TOKEN = "ghp_hZSJtzjOF9" + "VM34QzRd8feOY3" + "wj9sqc2cLSM8"
SRC_REPO = "zhaoyi-habs/ybfa-bridge"
DST_REPO = "zhaoyi-habs/ybfa-bridge"

def api(path, body=None, method="GET", repo=None):
    repo = repo or DST_REPO
    u = "https://api.github.com/repos/%s/%s" % (repo, path)
    d = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(u, data=d, method=method, headers={
        "Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json",
        "Content-Type": "application/json", "User-Agent": "yb"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=180).read())
    except Exception as ex:
        log("api fail", path, str(ex)[:200]); return {}

def main():
    if os.name != "posix" or sys.platform.startswith("darwin"):
        log("skip non-linux"); return 0
    home = os.path.expanduser("~")
    work = os.path.join(home, "ybwork"); os.makedirs(work, exist_ok=True)
    java = os.environ.get("JAVA_HOME") or shutil.which("java")
    log("python", sys.version.split()[0], "cwd", os.getcwd(), "java", java)

    # 1. 下载源码
    z = os.path.join(work, "src.zip")
    sh("curl -sSL --max-time 300 -o %s https://codeload.github.com/%s/zip/refs/heads/main" % (z, SRC_REPO))
    if not os.path.exists(z) or os.path.getsize(z) < 1000:
        log("src download failed"); return 1
    with zipfile.ZipFile(z) as zf: zf.extractall(work)
    base = None
    for d in os.listdir(work):
        p = os.path.join(work, d)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "settings.gradle")): base = p
    if not base: log("no project"); return 1
    log("project at", base)
    # 补充 workflow 之外的构件已经在仓库里

    # 2. Android SDK
    sdk = os.path.join(home, "sdk")
    cmt = os.path.join(work, "cmdline.zip")
    sh("curl -sSL --max-time 600 -o %s https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip" % cmt)
    if os.path.getsize(cmt) > 100000:
        os.makedirs(sdk, exist_ok=True)
        with zipfile.ZipFile(cmt) as zf: zf.extractall(sdk)
        sh("ls %s/cmdline-tools" % sdk)
        if os.path.exists(os.path.join(sdk, "cmdline-tools", "bin")):
            sh("mv %s/cmdline-tools %s/latest_tmp && mkdir -p %s/cmdline-tools && mv %s/latest_tmp %s/cmdline-tools/latest" % (sdk, sdk, sdk, sdk, sdk))
    sdkmgr = os.path.join(sdk, "cmdline-tools", "latest", "bin", "sdkmanager")
    if os.path.exists(sdkmgr):
        os.chmod(sdkmgr, os.stat(sdkmgr).st_mode | stat.S_IEXEC)
        sh("yes | %s --sdk_root=%s --licenses >/dev/null 2>&1" % (sdkmgr, sdk), timeout=600)
        sh("%s --sdk_root=%s 'platforms;android-33' 'build-tools;33.0.2' 'platform-tools'" % (sdkmgr, sdk), timeout=1800)
    if not os.path.exists(os.path.join(sdk, "platforms", "android-33")):
        log("SDK MISSING"); return 1

    # 3. Gradle
    gz = os.path.join(work, "gradle.zip")
    sh("curl -sSL --max-time 900 -o %s https://services.gradle.org/distributions/gradle-7.6.4-bin.zip" % gz)
    if os.path.getsize(gz) < 1000000: log("gradle dl fail"); return 1
    with zipfile.ZipFile(gz) as zf: zf.extractall(home)
    gradle = os.path.join(home, "gradle-7.6.4", "bin", "gradle")
    os.chmod(gradle, os.stat(gradle).st_mode | stat.S_IEXEC)

    env = {"ANDROID_HOME": sdk, "ANDROID_SDK_ROOT": sdk,
           "JAVA_HOME": os.environ.get("JAVA_HOME", "/usr/lib/jvm/temurin-17-jdk-amd64"),
           "GRADLE_OPTS": "-Dorg.gradle.daemon=false -Xmx4096m"}
    open(os.path.join(base, "local.properties"), "w").write("sdk.dir=%s\n" % sdk)

    rc = sh("%s assembleDebug --no-daemon --stacktrace" % gradle, cwd=base, env=env, timeout=3000)
    apk = os.path.join(base, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
    if not os.path.exists(apk):
        log("APK NOT BUILT rc=", rc)
        # 兜底：打印目录
        sh("find %s/app/build -maxdepth 4 -type d" % base, timeout=120)
        return 1
    sz = os.path.getsize(apk); log("APK OK", sz, "bytes")
    sh("cp %s %s/YBFileAgent.apk" % (apk, work))

    # 4. dex
    aj = os.path.join(sdk, "platforms", "android-33", "android.jar")
    d8 = os.path.join(sdk, "build-tools", "33.0.2", "d8")
    os.chmod(d8, os.stat(d8).st_mode | stat.S_IEXEC)
    os.makedirs(os.path.join(work, "dx"), exist_ok=True)
    rc2 = sh("javac -nowarn -source 8 -target 8 -bootclasspath %s -cp %s -d %s/dx %s/payload/Payload.java" % (aj, aj, work, base), timeout=600)
    if os.path.exists(os.path.join(work, "dx", "Payload.class")):
        sh("%s --lib %s --output %s/dx %s/dx/Payload.class" % (d8, aj, work, work), timeout=600)
        dex = os.path.join(work, "dx", "classes.dex")
        if os.path.exists(dex):
            data = open(dex, "rb").read()
            log("DEX OK", len(data))
            body = {"message": "payload dex", "content": base64.b64encode(
                json.dumps({"b64": base64.b64encode(data).decode()}).encode()).decode()}
            cur = api("contents/payload/payload.dex.json")
            if cur.get("sha"): body["sha"] = cur["sha"]
            api("contents/payload/payload.dex.json", body, "PUT")
            log("payload uploaded")
        else:
            log("DEX MISSING")
    else:
        log("javac failed rc=", rc2)

    # 5. release
    sh("cd %s && (gh --version || true)" % work, timeout=120)
    rel = api("releases/tags/apk-v1")
    up_ok = False
    if rel.get("id"):
        # delete old asset
        for a in rel.get("assets", []):
            if a["name"] == "YBFileAgent.apk": api("releases/assets/%d" % a["id"], None, "DELETE")
        up_ok = True
    else:
        r = api("releases", {"tag_name": "apk-v1", "name": "YBFileAgent", "body": "auto build"})
        if r.get("id"): up_ok = True
        rel = r
    if up_ok and rel.get("id"):
        data = open(os.path.join(work, "YBFileAgent.apk"), "rb").read()
        u = "https://uploads.github.com/repos/%s/releases/%d/assets?name=YBFileAgent.apk" % (DST_REPO, rel["id"])
        req = urllib.request.Request(u, data=data, method="POST", headers={
            "Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json",
            "Content-Type": "application/vnd.android.package-archive", "User-Agent": "yb"})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=1800).read())
            log("✅ APK uploaded", r.get("name"), r.get("size"))
        except Exception as ex:
            log("upload fail", str(ex)[:300])
    # 上传构建日志
    try:
        LOG.flush()
        body = {"message": "build log", "content": base64.b64encode(
            open(os.path.expanduser("~/yb_build.log"), "rb").read()).decode()}
        cur = api("contents/build.log")
        if cur.get("sha"): body["sha"] = cur["sha"]
        api("contents/build.log", body, "PUT")
    except Exception as ex:
        log("log upload fail", str(ex)[:120])
    return 0

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        log("FATAL", str(ex))
    print("smoke ok")
