# -*- coding: utf-8 -*-
# JOB3: 从 Lua 字节码提取 API 函数名（按文件分组）
import os,sys,json,time,base64,subprocess,urllib.request,zipfile,re,collections
ROOT=os.getcwd(); OUT=os.path.join(ROOT,"api3"); os.makedirs(OUT,exist_ok=True)
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
    head=j(base+"/git/refs/heads/main")["object"]["sha"]
    c=j(base+"/git/commits/"+head); tree=[]
    for p in paths:
        data=open(os.path.join(OUT,p),"rb").read()[:90*1024*1024]
        b=j(base+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(data).decode()})
        tree.append({"path":"api3/"+p,"mode":"100644","type":"blob","sha":b["sha"]})
    t=j(base+"/git/trees","POST",{"base_tree":c["tree"]["sha"],"tree":tree})
    nc=j(base+"/git/commits","POST",{"message":msg,"tree":t["sha"],"parents":[head]})
    j(base+"/git/refs/heads/main","PATCH",{"sha":nc["sha"]})
    return nc["sha"][:10]
REPO="zhaoyi-habs/MiniWorldPkgUnpacker"
log("=== JOB3 START ===",time.strftime("%H:%M:%S"))
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
subprocess.run("pip install -q lz4 2>&1|tail -1",shell=True)
subprocess.run("python3 unpack_common_res.py script_res.pkg unp/script_res 2>&1|tail -3",shell=True)
N=sum(len(f) for _,_,f in os.walk("unp/script_res")); log("files",N)

IDENT=re.compile(rb"[A-Za-z_][A-Za-z0-9_]{3,60}")
CJK=re.compile("[\u4e00-\u9fff]{2,30}".encode())
SKIP=set("""self local function then elseif until return while break false true nil
end for in do if else and not or repeat this class define constructor __index
__newindex __add __call __tostring __modpacketid__ SSC MainManager TransfomOrigin
Current wrapper stub LuaQ AssetRuntime CommonResource Script luascript ugc logic""".split())

GROUPS={
 "G1_api":["/ugc/logic/api/"],
 "G2_trigger":["/ugc/logic/trigger/"],
 "G3_scriptsupport":["/ugc/scriptsupport/"],
 "G4_visualcode":["/ugc/visualcode/","/ugc/blockly/"],
 "G5_component_sidebar":["/ugc/sidebar/"],
 "G6_scenetree":["/ugc/scenetree/"],
 "G7_sceneeditor":["/ugc/sceneeditor/","/ugc/terrainedit/"],
 "G8_gamebasesetting":["/ugc/gamebasesetting/"],
 "G9_aieditor":["/ugc/aieditor/"],
 "G10_uieditor":["/ugc/uieditor/"],
 "G11_sandboxengine":["/sandboxengine/"],
 "G12_miniui_other":["/miniui/module/"],
}
ALLID=collections.Counter(); ALLCJK=collections.Counter()
res=[]
for g,pref in GROUPS.items():
    lines=[]; seen=collections.OrderedDict()
    for dp,_,fs in os.walk("unp/script_res"):
        for fn in fs:
            fp=os.path.join(dp,fn).replace("\\","/")
            if not fn.endswith(".lua"): continue
            if not any(p in fp for p in pref): continue
            try: d=open(fp,"rb").read(4_000_000)
            except Exception: continue
            names=[]
            for m in IDENT.finditer(d):
                s=m.group().decode()
                if s in SKIP or len(s)<4: continue
                names.append(s)
            cj=[m.group().decode("utf-8") for m in CJK.finditer(d)]
            # 去重保序
            uq=list(collections.OrderedDict.fromkeys(names))
            uqc=list(collections.OrderedDict.fromkeys(cj))
            ALLID.update(uq); ALLCJK.update(uqc)
            short=fp.split("unp/script_res/")[-1]
            lines.append("\n### %s  (%d idents)\n%s"%("|".join(short.split("/")[-2:]),len(uq)," ".join(uq)))
            if uqc: lines.append("  [中文] "+" | ".join(uqc[:40]))
    p=g+".txt"; open(os.path.join(OUT,p),"w",encoding="utf-8").write("\n".join(lines))
    res.append(p); log(g,len(lines)//2,"files")
open(os.path.join(OUT,"G0_all_identifiers.txt"),"w",encoding="utf-8").write(
    "\n".join("%s\t%d"%(k,v) for k,v in ALLID.most_common(120000)))
res.append("G0_all_identifiers.txt")
open(os.path.join(OUT,"G0_all_chinese.txt"),"w",encoding="utf-8").write(
    "\n".join("%s\t%d"%(k,v) for k,v in ALLCJK.most_common(120000)))
res.append("G0_all_chinese.txt")
log("uniq idents",len(ALLID),"chinese",len(ALLCJK))
open(os.path.join(OUT,"99_log.txt"),"w",encoding="utf-8").write("\n".join(LOG))
res.append("99_log.txt")
for i in range(0,len(res),3):
    try: log("pushed",push(REPO,res[i:i+3],"api3 %d [skip ci]"%i))
    except Exception as e: log("PUSHFAIL",repr(e)[:150])
print("DONE3")
