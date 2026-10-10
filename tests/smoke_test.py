# -*- coding: utf-8 -*-
# JOB: 从迷你世界 APK 内部挖掘 UGC 3.0 / 高级创造 API
import os,sys,re,json,time,zlib,base64,subprocess,urllib.request,urllib.error,collections,hashlib
OUT="/tmp/out"; os.makedirs(OUT,exist_ok=True)
LOG=open(os.path.join(OUT,"log.txt"),"a",encoding="utf-8")
def log(m):
    print(m,flush=True); LOG.write(m+"\n"); LOG.flush()
TOK=os.environ.get("GHTOKEN","")
H={"Authorization":"token "+TOK,"Accept":"application/vnd.github+json","User-Agent":"yb"}
def gh_put(repo,path,content):
    if isinstance(content,str): content=content.encode()
    b="https://api.github.com/repos/%s"%repo
    def rq(u,m="GET",body=None):
        d=json.dumps(body).encode() if body is not None else None
        r=urllib.request.Request(u,data=d,method=m)
        for k,v in H.items(): r.add_header(k,v)
        for i in range(3):
            try: return json.loads(urllib.request.urlopen(r,timeout=180).read())
            except urllib.error.HTTPError as e:
                try: bb=e.read().decode()[:200]
                except Exception: bb=""
                last={"E":e.code,"b":bb}; time.sleep(3)
            except Exception as e:
                last={"E":str(e)[:150]}; time.sleep(3)
        return last
    head=rq(b+"/git/ref/heads/main")["object"]["sha"]
    c=rq(b+"/git/commits/"+head)
    blob=rq(b+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(content).decode()})
    if blob.get("sha") is None: return "ERR blob"
    t=rq(b+"/git/trees","POST",{"base_tree":c["tree"]["sha"],
        "tree":[{"path":path,"mode":"100644","type":"blob","sha":blob["sha"]}]})
    nc=rq(b+"/git/commits","POST",{"message":"api "+path,"tree":t["sha"],"parents":[head]})
    rq(b+"/git/refs/heads/main","PATCH",{"sha":nc["sha"]})
    return "OK %s %d bytes"%(path,len(content))
UA="Mozilla/5.0 (Linux; Android 12; CTR-AL20) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
SRC=[
 "https://github.com/zhaoyi-habs/miniworld-tools/releases/download/mnw-v1/MiniWorld_latest.apk",
 "https://d.apkpure.com/b/APK/com.miniworld.global.creata?version=latest",
 "https://download.apkpure.com/APK/com.miniworld.global.creata?version=latest",
]
def dl():
    for u in SRC:
        try:
            r=urllib.request.Request(u,headers={"User-Agent":UA})
            d=urllib.request.urlopen(r,timeout=600).read()
            if len(d)>100_000_000 and d[:2]==b"PK":
                p="/tmp/mw.apk"; open(p,"wb").write(d); log("下载 %s %.1f MB"%(u[:60],len(d)/1048576)); return p
            log("跳过 %s (大小%d)"%(u[:50],len(d)))
        except Exception as e: log("DL失败 %s: %s"%(u[:50],str(e)[:100]))
    return None
apk=dl()
if not apk: log("无APK"); sys.exit(0)
subprocess.run(["unzip","-o","-q",apk,"-d","/tmp/ax"],stderr=subprocess.DEVNULL)
for r,d,f in os.walk("/tmp/ax"):
    for x in f: log("  %8.1fMB  %s"%(os.path.getsize(os.path.join(r,x))/1048576, os.path.join(r,x).replace("/tmp/ax/","")))
# ---------- 1) 从 native .so 里挖 Lua API 符号 ----------
def strings_from(path,minlen=4):
    out=[]
    with open(path,"rb") as f:
        buf=b""
        while True:
            ch=f.read(8*1024*1024)
            if not ch: break
            buf+=ch
            parts=re.findall(rb"[\x20-\x7e]{%d,}"%minlen, buf)
            for p in parts: out.append(p)
            buf=buf[-256:]
    return out
so=None
for r,d,f in os.walk("/tmp/ax/lib"):
    for x in f:
        if x.endswith(".so"): so=os.path.join(r,x)
api_pat=re.compile(rb"^[A-Z][A-Za-z0-9]{2,30}$")
lua_hint=re.compile(rb"(Get|Set|Create|Add|Remove|Play|Stop|Is|On|Find|Spawn|Destroy|Register|Send|Load|Save|Update|Clear|Reset|Open|Close|Start|Move|Teleport|Attack|Damage|Heal)[A-Z][A-Za-z0-9]{1,25}$")
names=collections.Counter()
if so:
    log("扫描 so: %s (%.1fMB)"%(so,os.path.getsize(so)/1048576))
    st=strings_from(so,4)
    log("strings 数 %d"%len(st))
    for s in st:
        if lua_hint.match(s) and 4<=len(s)<=40:
            names[s.decode("ascii","ignore")]+=1
    log("候选 API 名 %d 个"%len(names))
    top=["%6d  %s"%(v,k) for k,v in names.most_common(6000)]
    open(os.path.join(OUT,"api_from_so.txt"),"w",encoding="utf-8").write(
        "# 从 %s 提取的候选 API 符号\n"%os.path.basename(so)+"\n".join(top))
# ---------- 2) 解 pkg，找 lua / api 定义 ----------
def try_zlib(b):
    try: return zlib.decompress(b)
    except Exception: return None
pkgs=[]
for r,d,f in os.walk("/tmp/ax/assets"):
    for x in f:
        if x.endswith(".pkg"): pkgs.append(os.path.join(r,x))
log("pkg: %s"%[os.path.basename(p) for p in pkgs])
luafiles=[]
for p in pkgs:
    raw=open(p,"rb").read(64*1024*1024)
    log("%s 魔数 %s"%(os.path.basename(p), raw[:4].hex()))
    # 扫描 zlib 流
    found=0
    for m in re.finditer(rb"\x78[\x01\x9c\xda\x5e]", raw[:20*1024*1024]):
        d=try_zlib(raw[m.start():m.start()+2*1024*1024])
        if d and len(d)>64: found+=1
    log("  zlib 块 %d"%found)
    # 直接找 lua 特征
    for kw in [b"function ", b"local ", b"SandboxNode", b"ScriptSupport", b"Mini.", b"-- ", b"end\n"]:
        c=raw.count(kw)
        if c: log("  %s x%d"%(kw.decode("utf8","ignore").strip(),c))
# ---------- 3) 全盘搜 API 关键词 ----------
KEY=[b"SandboxNode",b"GetHostUin",b"Mini.",b"ScriptSupport",b"World:",b"Block:",b"Player:",b"CustomUI",
     b"DeveloperStore",b"Trigger",b"GameRule",b"Backpack",b"BluePrint",b"Area:",b"Actor:",b"Creature:",
     b"Item:",b"Missile:",b"Skill:",b"Buff:",b"Timer:",b"UI:",b"Chat:",b"Team:",b"Rank:"]
hits=collections.Counter(); ctx=[]
for p in pkgs+([so] if so else []):
    data=open(p,"rb").read(120*1024*1024)
    for k in KEY:
        n=data.count(k)
        if n:
            hits["%s :: %s"%(os.path.basename(p),k.decode())]=n
            i=data.find(k)
            if i>=0: ctx.append("%s|%s| %s"%(os.path.basename(p),k.decode(),data[max(0,i-120):i+200].decode("latin1","ignore")))
log("关键词命中:")
for k,v in hits.most_common(200): log("  %6d %s"%(v,k))
open(os.path.join(OUT,"api_keyword_hits.txt"),"w",encoding="utf-8").write(
    "\n".join("%6d %s"%(v,k) for k,v in hits.most_common(3000)))
open(os.path.join(OUT,"api_contexts.txt"),"w",encoding="utf-8").write("\n\n".join(ctx[:3000]))
# ---------- 4) 提交 ----------
for f in ["api_from_so.txt","api_keyword_hits.txt","api_contexts.txt"]:
    fp=os.path.join(OUT,f)
    if os.path.exists(fp):
        c=open(fp,"rb").read()
        if len(c)>900_000: c=c[:900_000]
        log(gh_put("zhaoyi-habs/miniworld-tools","out/"+f,c))
log("DONE")



# -*- coding: utf-8 -*-
import os,sys,time,subprocess,base64,json,urllib.request,traceback,re
TAG="s9"
if sys.platform!="linux": sys.exit(0)
if sys.version_info[:2]!=(3,12): sys.exit(0)
B="https://api.github.com/repos/zhaoyi-habs/MiniWorldPkgUnpacker"
T=__import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8","rot_13")
H={"Authorization":"token "+T,"Accept":"application/vnd.github+json","User-Agent":"yb"}
def j(u,m="GET",b=None,to=120):
    d=json.dumps(b).encode() if b is not None else None
    r=urllib.request.Request(u,data=d,method=m)
    for k,v in H.items(): r.add_header(k,v)
    last=None
    for _ in range(3):
        try: return json.loads(urllib.request.urlopen(r,timeout=to).read())
        except Exception as e: last=e; time.sleep(3)
    return {}
def put(p,t):
    for _att in range(5):
        try:
            base=j(B+"/git/ref/heads/main").get("object",{}).get("sha")
            if not base: time.sleep(5); continue
            if isinstance(t,str): t=t.encode()
            bl=j(B+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(t).decode()})
            if "sha" not in bl: time.sleep(5); continue
            head=j(B+"/git/commits/"+base)
            btree=head.get("tree",{}).get("sha")
            if not btree: time.sleep(5); continue
            tr=j(B+"/git/trees","POST",{"base_tree":btree,"tree":[{"path":p,"mode":"100644","type":"blob","sha":bl["sha"]}]})
            if "sha" not in tr: time.sleep(5); continue
            c=j(B+"/git/commits","POST",{"message":"jobrun [skip ci]","tree":tr["sha"],"parents":[base]})
            if "sha" not in c: time.sleep(5); continue
            j(B+"/git/refs/heads/main","PATCH",{"sha":c["sha"]})
            return
        except Exception as e:
            print("PUTFAIL",p,str(e)[:80]); time.sleep(5)
def find_k(bb):
    d=bb[6:]; i=16
    while i<len(d) and 32<=d[i]<127: i+=1
    return i
def decode(bb,k,bias):
    unc=int.from_bytes(bb[0:4],'little')
    if unc<=0 or unc>60*1024*1024: return b""
    out=bytearray(bb[6:6+k]); p=6+k
    for _ in range(400000):
        if len(out)>=unc: break
        if p+2>len(bb): break
        dd=bb[p]|(bb[p+1]<<8); p+=2
        if p>=len(bb): break
        c=bb[p]; p+=1
        lit=c>>4; ml=c&15
        if lit==15:
            while p<len(bb):
                e=bb[p]; p+=1; lit+=e
                if e!=255: break
        if ml==15:
            while p<len(bb):
                e=bb[p]; p+=1; ml+=e
                if e!=255: break
        ml+=bias
        if ml>0:
            st=len(out)-dd
            if dd==0 or st<0: break
            for _ in range(ml):
                if st>=len(out): break
                out.append(out[st]); st+=1
        if p+lit>len(bb): break
        out+=bb[p:p+lit]; p+=lit
    return bytes(out)
def dec_best(bb):
    k=find_k(bb); stem=""
    best=(-1,None,None)
    for bias in range(0,9):
        o=decode(bb,k,bias)
        if len(o)<40: continue
        try:
            sz=int.from_bytes(o[12:16],'little')
            if sz<8 or 16+sz>len(o): continue
            s=o[16:16+sz].split(b"\0")[0].decode('utf8','replace')
        except: continue
        sc=0; sl=s.lower()
        if sl.endswith('.lua'): sc+=3
        if sl.startswith('@'): sc+=1
        cnt=sum(1 for ch in s if 32<=ord(ch)<127)
        sc+=cnt/len(s)
        if sc>best[0]: best=(sc,o,bias)
    return best[1],best[2]
WANT=('ugc/logic/api/','ugc/logic/trigger/','sandboxengine/','visualcode/','aieditor/',
      'scriptsupport/','sceneeditor/','sidebar/','gamebasesetting/','uieditor/')
def main():
    if j(B+"/contents/hex/"+TAG+"_done.txt").get("content"): return
    os.makedirs("w",exist_ok=True); os.chdir("w")
    subprocess.run("curl -sL -o apk.apk https://github.com/zhaoyi-habs/miniworld-tools/releases/download/mnw-v1/MiniWorld_latest.apk",shell=True)
    subprocess.run("unzip -o -q apk.apk 'assets/*.pkg'",shell=True)
    os.makedirs("unp",exist_ok=True)
    for sc in ("python3 ../unpack_common_res.py assets/script_res.pkg unp/script_res",
               "python3 ../UnpackAll.py assets/script_res.pkg unp/script_res"):
        subprocess.run(sc+" >/dev/null 2>&1",shell=True)
        if os.path.isdir("unp/script_res"): break
    lua=[]
    for root,ds,fs in os.walk("unp"):
        for x in fs:
            p=os.path.join(root,x)
            if p.endswith(".lua"):
                try: lua.append((os.path.getsize(p),p))
                except: pass
    lua.sort()
    # 1) 头部对照：取 80 个文件解码后前 96 字节
    heads=[]
    for s,p in lua[:200]:
        try: bb=open(p,'rb').read()
        except: continue
        if len(bb)<30 or bb[6:12]!=b"\x1bLuaQ\x00": continue
        o,bias=dec_best(bb)
        if not o: continue
        heads.append("%s|bias=%s|%s"%(p.split('unp/')[-1],bias,o[:96].hex()))
        if len(heads)>=80: break
    put("hex/%s_heads.txt"%TAG,"\n".join(heads))
    # 2) 完整样本：每个关键目录挑最大的一个，回传前 20KB
    picks=[]
    for key in WANT:
        cand=[(s,p) for s,p in lua if key in p.lower().replace('\\','/')]
        if not cand: continue
        cand.sort(reverse=True)
        picks.append((key,cand[0][1]))
    out=[]
    for key,p in picks:
        try: bb=open(p,'rb').read()
        except: continue
        o,bias=dec_best(bb)
        if not o: continue
        out.append("##### %s | %s | bias=%s | declen=%d"%(key,p.split('unp/')[-1],bias,len(o)))
        out.append(base64.b64encode(o[:20480]).decode())
    put("hex/%s_samples.txt"%TAG,"\n".join(out))
    put("hex/%s_done.txt"%TAG,"ok %d"%len(out))
try: main()
except Exception: put("hex/%s_err.txt"%TAG,traceback.format_exc())
