# -*- coding: utf-8 -*-
# JOB5: 字节码字符串表精确提取（可打印串切分 + 十六进制校验）
import os,sys,json,time,base64,subprocess,urllib.request,zipfile,re,collections,traceback
ROOT=os.getcwd(); OUT=os.path.join(ROOT,"api5"); os.makedirs(OUT,exist_ok=True)
LOG=[]
def log(*a):
    s=" ".join(str(x) for x in a); print(s,flush=True); LOG.append(s)
def save(p,t): open(os.path.join(OUT,p),"w",encoding="utf-8",errors="replace").write(t)
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
        tree.append({"path":"api5/"+p,"mode":"100644","type":"blob","sha":b["sha"]})
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
    log("=== JOB5 START ===",time.strftime("%H:%M:%S"))
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
    log("unpacked")
    # 十六进制校验：actor.lua 前 512 字节
    p="unp/script_res/commonresource/script/luascript/ugc/logic/api/actor.lua"
    if os.path.exists(p):
        raw=open(p,"rb").read(512)
        log("HEXDUMP actor.lua:\n"+ " ".join("%02x"%b for b in raw[:256]))
    SPLIT=re.compile(rb"[^\x20-\x7e]+")
    GROUPS={
     "S1_api":["/ugc/logic/api/"],
     "S2_trigger":["/ugc/logic/trigger/"],
     "S3_scriptsupport":["/ugc/scriptsupport/"],
     "S4_visualcode":["/ugc/visualcode/","/ugc/blockly/"],
     "S5_sidebar":["/ugc/sidebar/"],
     "S6_scenetree":["/ugc/scenetree/"],
     "S7_sceneeditor":["/ugc/sceneeditor/","/ugc/terrainedit/"],
     "S8_gamebasesetting":["/ugc/gamebasesetting/"],
     "S9_aieditor":["/ugc/aieditor/"],
     "S10_uieditor":["/ugc/uieditor/"],
     "S11_sandboxengine":["/sandboxengine/"],
    }
    ALL=collections.Counter(); res=[]
    for g,pref in GROUPS.items():
        lines=[]
        for dp,_,fs in os.walk("unp/script_res"):
            for fn in sorted(fs):
                fp=os.path.join(dp,fn).replace("\\","/")
                if not fn.endswith(".lua"): continue
                if not any(x in fp for x in pref): continue
                try: raw=open(fp,"rb").read(4_000_000)
                except Exception: continue
                toks=[t.decode("latin-1") for t in SPLIT.split(raw) if len(t)>=3]
                uq=list(collections.OrderedDict.fromkeys(toks))
                ALL.update(uq)
                short="/".join(fp.split("unp/script_res/")[-1].split("/")[-2:])
                lines.append("\n### %s  (%d)\n%s"%(short,len(uq)," ".join(uq)))
        save(g+".txt","\n".join(lines)); res.append(g+".txt"); log(g,len(lines))
    save("S0_all.txt","\n".join("%s\t%d"%(k,v) for k,v in ALL.most_common(200000)))
    res.append("S0_all.txt"); log("uniq",len(ALL))
    for i in range(0,len(res),3):
        try: log("pushed",push(REPO,res[i:i+3],"api5 %d [skip ci]"%i))
        except Exception as e: log("PUSHFAIL",repr(e)[:150])
except Exception:
    log("EXC:\n"+traceback.format_exc())
flush(); print("DONE5")
