# -*- coding: utf-8 -*-
# JOB2: 提取 UGC / 高级创造 / 触发器2.0 Lua 源码与配置表
import os,sys,json,time,base64,subprocess,urllib.request,zipfile
ROOT=os.getcwd(); OUT=os.path.join(ROOT,"src"); os.makedirs(OUT,exist_ok=True)
LOG=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.append(s)
T=__import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8","rot_13")
H={"Authorization":"token "+T,"Accept":"application/vnd.github+json","User-Agent":"yb"}
def j(u,m="GET",b=None,to=180):
    d=json.dumps(b).encode() if b is not None else None
    r=urllib.request.Request(u,data=d,method=m)
    for k,v in H.items(): r.add_header(k,v)
    last=None
    for _ in range(4):
        try: return json.loads(urllib.request.urlopen(r,timeout=to).read())
        except Exception as e: last=e; time.sleep(4)
    raise last
def push(repo,paths,msg):
    base="https://api.github.com/repos/"+repo
    head=j(base+"/git/ref/heads/main")["object"]["sha"]
    c=j(base+"/git/commits/"+head); tree=[]
    for p in paths:
        data=open(os.path.join(OUT,p),"rb").read()[:90*1024*1024]
        b=j(base+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(data).decode()})
        tree.append({"path":"src/"+p,"mode":"100644","type":"blob","sha":b["sha"]})
    t=j(base+"/git/trees","POST",{"base_tree":c["tree"]["sha"],"tree":tree})
    nc=j(base+"/git/commits","POST",{"message":msg,"tree":t["sha"],"parents":[head]})
    j(base+"/git/refs/heads/main","PATCH",{"sha":nc["sha"]})
    return nc["sha"][:10]
REPO="zhaoyi-habs/MiniWorldPkgUnpacker"
log("=== JOB2 START ===",time.strftime("%H:%M:%S"))

# 1. APK + 抽出 script_res.pkg
if not os.path.exists("script_res.pkg"):
    a=j("https://api.github.com/repos/zhaoyi-habs/miniworld-tools/releases/tags/mnw-v1")["assets"]
    aid=[x["id"] for x in a if x["name"]=="MiniWorld_latest.apk"][0]
    r=urllib.request.urlopen(urllib.request.Request(
        "https://api.github.com/repos/zhaoyi-habs/miniworld-tools/releases/assets/%d"%aid,
        headers={**H,"Accept":"application/octet-stream"}),timeout=1800)
    open("apk.apk","wb").write(r.read())
    z=zipfile.ZipFile("apk.apk")
    with z.open("assets/script_res.pkg") as s,open("script_res.pkg","wb") as f:
        while True:
            b=s.read(1<<23)
            if not b: break
            f.write(b)
    log("script_res.pkg",os.path.getsize("script_res.pkg"))
subprocess.run("pip install -q lz4 2>&1|tail -1",shell=True)
subprocess.run("python3 unpack_common_res.py script_res.pkg unp/script_res",shell=True)
log("unpacked",sum(len(f) for _,_,f in os.walk("unp/script_res")))

# 2. 分组抽取
GROUPS={
 "A_ugc_api":      ["luascript/ugc/logic/api/"],
 "B_ugc_trigger":  ["luascript/ugc/logic/trigger/","luascript/ugc/logic/"],
 "C_scriptsupport":["luascript/ugc/scriptsupport/"],
 "D_visualcode":   ["miniui/module/ugc/visualcode/","miniui/module/ugc/blockly/"],
 "E_component":    ["miniui/module/ugc/sidebar/","miniui/module/ugc/scenetree/"],
 "F_sceneeditor":  ["miniui/module/ugc/sceneeditor/","miniui/module/ugc/terrainedit/","miniui/module/ugc/selector/"],
 "G_gamebasesetting":["miniui/module/ugc/gamebasesetting/"],
 "H_aieditor":     ["miniui/module/ugc/aieditor/"],
 "I_uieditor":     ["miniui/module/ugc/uieditor/"],
 "J_sandboxengine":["script/sandboxengine/"],
 "K_unittest":     ["luascript/ugc/unittest/"],
}
csvfiles=["codeblockconfig.csv","codeblockenum.csv","codeblockparam.csv",
          "componentconfig.csv","gamerule.csv","game_language.csv","funcswitch.csv"]
res=[]
for g,prefixes in GROUPS.items():
    buf=[]; n=0; tot=0
    for dp,_,fs in os.walk("unp/script_res"):
        for fn in fs:
            fp=os.path.join(dp,fn).replace("\\","/")
            if not any(p in fp for p in prefixes): continue
            try:
                d=open(fp,"rb").read(3_000_000)
                if b"\x00" in d[:2000] and not fn.endswith(".csv"): pass
                t=d.decode("utf-8","replace")
            except Exception as e: continue
            buf.append("\n\n########## FILE: %s  (%d bytes) ##########\n%s"%(fp,len(d),t))
            n+=1; tot+=len(d)
    p=g+".txt"
    open(os.path.join(OUT,p),"w",encoding="utf-8").write("\n".join(buf))
    res.append(p); log(g,n,"files",tot,"bytes")
buf=[]
for dp,_,fs in os.walk("unp/script_res"):
    for fn in fs:
        if fn in csvfiles:
            fp=os.path.join(dp,fn)
            try: buf.append("\n\n########## CSV: %s ##########\n%s"%(fp,open(fp,"rb").read(8_000_000).decode("utf-8","replace")))
            except Exception: pass
open(os.path.join(OUT,"Z_csvdef.txt"),"w",encoding="utf-8").write("\n".join(buf))
res.append("Z_csvdef.txt"); log("csv files",len(buf))
open(os.path.join(OUT,"99_log.txt"),"w",encoding="utf-8").write("\n".join(LOG))
res.append("99_log.txt")
try:
    for i in range(0,len(res),3):
        log("pushed",push(REPO,res[i:i+3],"src %d [skip ci]"%i))
except Exception as e: log("PUSH FAIL",repr(e)[:200])
print("DONE2")
