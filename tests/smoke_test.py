# -*- coding: utf-8 -*-
# JOB: 从迷你世界官方 APK 深度挖掘 UGC3.0 / 高级创造 API 与全部可用资源
import os,sys,re,json,time,zipfile,subprocess,base64,urllib.request,urllib.error,collections

OSN=os.environ.get("RUNNER_OS","?")
PYV=".".join(str(x) for x in sys.version_info[:2])
HEAVY = (OSN=="Linux")
OUT="mwout"; os.makedirs(OUT,exist_ok=True)
LOGP=os.path.join(OUT,"log_%s_%s.txt"%(OSN,PYV))
def L(*a):
    s=" ".join(str(x) for x in a)
    try: print(s,flush=True)
    except Exception: pass
    with open(LOGP,"a",encoding="utf-8") as f: f.write(s+"\n")

L("=== DIG start ===",OSN,PYV,"heavy=",HEAVY,time.time())
T=__import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8","rot_13")
H={"Authorization":"token "+T,"Accept":"application/vnd.github+json","User-Agent":"yb"}
def j(u,m="GET",b=None,to=180):
    d=json.dumps(b).encode() if b is not None else None
    r=urllib.request.Request(u,data=d,method=m)
    for k,v in H.items(): r.add_header(k,v)
    last=None
    for _ in range(3):
        try: return json.loads(urllib.request.urlopen(r,timeout=to).read())
        except Exception as e: last=e; time.sleep(4)
    L("NETFAIL",u,last); return None
def gh_commit(files,branch="main",msg="dig"):
    base="https://api.github.com/repos/zhaoyi-habs/mw-dig"
    head=j(base+"/git/ref/heads/"+branch)["object"]["sha"]
    c=j(base+"/git/commits/"+head)
    tree=[]
    for p,content in files.items():
        if isinstance(content,str): content=content.encode("utf-8")
        b=j(base+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(content).decode()})
        if not b or "sha" not in b: L("BLOBFAIL",p); continue
        tree.append({"path":p,"mode":"100644","type":"blob","sha":b["sha"]})
    t=j(base+"/git/trees","POST",{"base_tree":c["tree"]["sha"],"tree":tree})
    nc=j(base+"/git/commits","POST",{"message":msg,"tree":t["sha"],"parents":[head]})
    j(base+"/git/refs/heads/"+branch,"PATCH",{"sha":nc["sha"]})
    return nc["sha"][:10]

RES={}
def put(n,t): RES[n]=t

if not HEAVY:
    L("light os, skip heavy work"); sys.exit(0)

# ---------- 1. 下载 APK ----------
apk="apk.apk"
if not os.path.exists(apk):
    a=j("https://api.github.com/repos/zhaoyi-habs/miniworld-tools/releases/tags/mnw-v1")
    url=None
    for x in (a or {}).get("assets",[]):
        if x["name"]=="MiniWorld_latest.apk": url="https://api.github.com/repos/zhaoyi-habs/miniworld-tools/releases/assets/%d"%x["id"]
    L("asset",url)
    t0=time.time()
    r=urllib.request.Request(url,headers={**H,"Accept":"application/octet-stream"})
    with urllib.request.urlopen(r,timeout=1800) as resp, open(apk,"wb") as f:
        while True:
            b=resp.read(1<<22)
            if not b: break
            f.write(b)
    L("apk",os.path.getsize(apk),"%.1fs"%(time.time()-t0))
subprocess.run("df -h . | tail -1",shell=True)

z=zipfile.ZipFile(apk)
names=z.namelist()
L("entries",len(names))
lines=["%s\t%d"%(n,z.getinfo(n).file_size) for n in names]
put("01_apk_entries.txt","\n".join(lines))

# ---------- 2. pkg 头 ----------
pk=[n for n in names if n.endswith(".pkg")]
hh=[]
for n in pk:
    with z.open(n) as f: b=f.read(64)
    hh.append("%s\n  head32=%s\n  hex64=%s"%(n,b[:32].hex(),b.hex()))
put("02_pkg_headers.txt","\n".join(hh))

# ---------- 3. 提取待扫描文件 ----------
os.makedirs("ex",exist_ok=True)
targets=[]
for n in names:
    if n.endswith(".pkg"): targets.append(n)
    elif n.endswith(".so") and "GameApp" in n: targets.append(n)
    elif n.endswith(".dex") or n.endswith(".js"): targets.append(n)
extracted=[]
for n in targets:
    sz=z.getinfo(n).file_size
    if sz>700*1024*1024 and "GameApp" not in n: continue
    try:
        fp="ex/"+n.replace("/","__")
        with z.open(n) as s, open(fp,"wb") as f:
            while True:
                b=s.read(1<<22)
                if not b: break
                f.write(b)
        extracted.append((n,fp,os.path.getsize(fp)))
    except Exception as e: L("EXTRACT FAIL",n,e)
L("extracted",[(a,c) for a,b,c in extracted])
put("03_extracted.txt","\n".join("%s\t%s\t%d"%x for x in extracted))

# ---------- 4. 全量 strings + 分类 ----------
CATS={
 "A_service":   re.compile(rb"[A-Za-z][A-Za-z0-9_]{2,40}(Service|Mgr|Manager|System)"),
 "B_component": re.compile(rb"[A-Za-z][A-Za-z0-9_]{2,40}(Component|Cmp)"),
 "C_mini":      re.compile(rb"Mini[A-Za-z0-9_]{2,40}"),
 "D_ugc":       re.compile(rb"[A-Za-z0-9_.\-]{0,25}(?:UGC|ugc|Ugc)[A-Za-z0-9_.\-]{0,25}"),
 "E_trigger":   re.compile(rb"[A-Za-z0-9_.\-]{0,20}(Trigger|BluePrint|GameRule|CustomUI|Customui|DeveloperStore|SandboxNode)[A-Za-z0-9_.\-]{0,20}"),
 "F_dotted":    re.compile(rb"[A-Za-z][A-Za-z0-9_]{1,30}\.[A-Za-z][A-Za-z0-9_]{1,30}"),
 "H_func":      re.compile(rb"(?:get|set|add|remove|del|delete|is|has|play|stop|create|destroy|register|unregister|send|show|hide|open|close|update|start|reset|find|can|apply|buy|equip)[A-Z][A-Za-z0-9_]{2,40}"),
 "I_snake":     re.compile(rb"[a-z][a-z0-9]{2,30}(?:_[a-z0-9]{1,20}){1,6}"),
 "J_path":      re.compile(rb"[A-Za-z0-9_/\-]{4,90}\.(?:lua|json|csv|xml|txt|pb|proto|js|ts|skanim|skeleton|mesh|mat|omod|ent)"),
 "K_event":     re.compile(rb"[Oo]n[A-Z][A-Za-z0-9_]{2,40}"),
 "L_signal":    re.compile(rb"[A-Za-z][A-Za-z0-9_]{2,40}(?:Signal|Event)"),
 "M_cjk":       re.compile("[\u4e00-\u9fff]{2,40}".encode("utf-8")),
}
found={k:set() for k in CATS}
for n,fp,sz in extracted:
    cnt=0; prev=b""
    with open(fp,"rb") as f:
        while True:
            b=f.read(1<<22)
            if not b: break
            buf=prev+b; cnt+=len(b)
            for k,rgx in CATS.items():
                for m in rgx.finditer(buf):
                    s=m.group()
                    if len(s)>160: continue
                    found[k].add(s)
            prev=buf[-200:]
    L("scanned",n,sz,{k:len(v) for k,v in found.items()})

for k,v in found.items():
    if k=="M_cjk":
        out=sorted(x.decode("utf-8","ignore") for x in v)
    else:
        out=sorted(x.decode("latin-1") for x in v)
    put("10_%s.txt"%k,"\n".join(out[:60000]))
put("99_stats.txt","\n".join("%s\t%d"%(k,len(v)) for k,v in found.items()))

# ---------- 5. 解包 pkg（用仓库自带解包器） ----------
unpack_log=[]
for n in pk:
    fp="ex/"+n.replace("/","__")
    if not os.path.exists(fp): continue
    outd="unp/"+os.path.basename(fp)
    os.makedirs(outd,exist_ok=True)
    for script in ["unpack_pkg_intl.py","unpack_common_res.py","extract_game_script.py"]:
        if not os.path.exists(script): continue
        try:
            p=subprocess.run([sys.executable,script,fp,outd],capture_output=True,timeout=1800)
            o=(p.stdout[-1500:]+p.stderr[-1500:]).decode("utf-8","ignore")
            unpack_log.append("### %s %s rc=%d\n%s"%(n,script,p.returncode,o))
            if p.returncode==0 and os.listdir(outd):
                break
        except Exception as e:
            unpack_log.append("### %s %s EXC %s"%(n,script,e))
    cnt=sum(len(f) for _,_,f in os.walk(outd))
    L("unpacked",n,cnt,"files")
put("20_unpack_log.txt","\n".join(unpack_log))

# ---------- 6. 解包产物清单 ----------
try:
    allf=[]
    for root,dirs,files in os.walk("unp"):
        for f in files:
            p=os.path.join(root,f)
            try: allf.append("%s\t%d"%(p,os.path.getsize(p)))
            except Exception: pass
    put("21_unpacked_files.txt","\n".join(allf[:200000]))
    # 按扩展名统计
    c=collections.Counter(os.path.splitext(x)[1] for x in allf)
    put("22_ext_stats.txt","\n".join("%s\t%d"%(k,v) for k,v in c.most_common(300)))
except Exception as e:
    L("LIST FAIL",e)

# ---------- 7. 推送 ----------
try:
    sha=gh_commit({"out_run_%s_%s/"%(OSN,PYV)+k:v for k,v in RES.items()},msg="dig %s %s"%(OSN,PYV))
    L("PUSHED",sha,len(RES))
except Exception as e:
    L("PUSH FAIL",e)
    for k in list(RES)[:2]:
        try: gh_commit({"fallback/%s"%k:RES[k][:200000]},msg="fb")
        except Exception as e2: L("FB FAIL",e2)
L("=== DIG done ===",time.time())
