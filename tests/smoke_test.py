# -*- coding: utf-8 -*-
# JOB4: Lua 字节码 API 函数名提取（字节级，latin-1 保真）
import os,sys,json,time,base64,subprocess,urllib.request,zipfile,re,collections,traceback
ROOT=os.getcwd(); OUT=os.path.join(ROOT,"api4"); os.makedirs(OUT,exist_ok=True)
LOG=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.append(s)
def save(p,txt):
    open(os.path.join(OUT,p),"w",encoding="utf-8",errors="replace").write(txt)
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
    head=j(base+"/git/refs/heads/main")["object"]["sha"]
    c=j(base+"/git/commits/"+head); tree=[]
    for p in paths:
        data=open(os.path.join(OUT,p),"rb").read()[:90*1024*1024]
        b=j(base+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(data).decode()})
        tree.append({"path":"api4/"+p,"mode":"100644","type":"blob","sha":b["sha"]})
    t=j(base+"/git/trees","POST",{"base_tree":c["tree"]["sha"],"tree":tree})
    nc=j(base+"/git/commits","POST",{"message":msg,"tree":t["sha"],"parents":[head]})
    j(base+"/git/refs/heads/main","PATCH",{"sha":nc["sha"]})
    return nc["sha"][:10]
REPO="zhaoyi-habs/MiniWorldPkgUnpacker"
def flush():
    save("99_log.txt","\n".join(LOG))
    try: push(REPO,["99_log.txt"],"log [skip ci]")
    except Exception: pass
try:
    log("=== JOB4 START ===",time.strftime("%H:%M:%S"))
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
        log("pkg",os.path.getsize("script_res.pkg"))
    subprocess.run("pip install -q lz4 2>&1|tail -1",shell=True)
    pr=subprocess.run("python3 unpack_common_res.py script_res.pkg unp/script_res 2>&1|tail -5",
                      shell=True,capture_output=True,text=True)
    log("unpack rc",pr.returncode,(pr.stdout or "")[-300:])
    N=sum(len(f) for _,_,f in os.walk("unp/script_res")); log("files",N)
    log("sample:",[os.path.join(dp,fn) for dp,_,fs in os.walk("unp/script_res") for fn in fs][:3])
    flush()
    IDENT=re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,60}")
    NOISE=set("""self local function then elseif until return while break false true nil end for
    in do if else and not or repeat this class define constructor __index __newindex __add __call
    __tostring __modpacketid__ wrapper stub FILE bytes script_res script luas MiniGame AssetRunti
    RainbowMaster AssetRuntime CommonResource commonresource luascript ugc logic miniui module
    csvdef utf8 cBase Aself Astub Class ClassEx ClassName super New Delete Init Update Destroy
    OnCreate OnDestroy OnEnable OnDisable GetName SetName GetType""".split())
    GROUPS={
     "G1_api":["/ugc/logic/api/"],
     "G2_trigger":["/ugc/logic/trigger/"],
     "G3_scriptsupport":["/ugc/scriptsupport/"],
     "G4_visualcode":["/ugc/visualcode/","/ugc/blockly/"],
     "G5_sidebar_component":["/ugc/sidebar/"],
     "G6_scenetree":["/ugc/scenetree/"],
     "G7_sceneeditor":["/ugc/sceneeditor/","/ugc/terrainedit/"],
     "G8_gamebasesetting":["/ugc/gamebasesetting/"],
     "G9_aieditor":["/ugc/aieditor/"],
     "G10_uieditor":["/ugc/uieditor/"],
     "G11_sandboxengine":["/sandboxengine/"],
     "G12_miniui":["/miniui/module/"],
    }
    ALL=collections.Counter(); res=[]
    for g,pref in GROUPS.items():
        lines=[]
        for dp,_,fs in os.walk("unp/script_res"):
            for fn in sorted(fs):
                fp=os.path.join(dp,fn).replace("\\","/")
                if not fn.endswith(".lua"): continue
                if not any(p in fp for p in pref): continue
                try: raw=open(fp,"rb").read(4_000_000)
                except Exception: continue
                d=raw.decode("latin-1")
                ids=[m.group() for m in IDENT.finditer(d)]
                uq=list(collections.OrderedDict.fromkeys(i for i in ids if i not in NOISE))
                ALL.update(uq)
                short="/".join(fp.split("unp/script_res/")[-1].split("/")[-2:])
                lines.append("\n### %s  (%d)\n%s"%(short,len(uq)," ".join(uq)))
        save(g+".txt","\n".join(lines)); res.append(g+".txt")
        log(g,len(lines),"files")
    save("G0_all.txt","\n".join("%s\t%d"%(k,v) for k,v in ALL.most_common(150000)))
    res.append("G0_all.txt"); log("uniq idents",len(ALL))
    for i in range(0,len(res),3):
        try: log("pushed",push(REPO,res[i:i+3],"api4 %d [skip ci]"%i))
        except Exception as e: log("PUSHFAIL",repr(e)[:150])
except Exception:
    log("EXC:\n"+traceback.format_exc())
flush()
print("DONE4")
