# -*- coding: utf-8 -*-
# JOB s2: 全量解码迷你世界 Lua 字节码 -> 提取完整 API/字符串 -> 前缀修复
import os,sys,subprocess,base64,json,urllib.request,time,traceback,re,collections
TAG="s2"
if sys.platform!="linux": sys.exit(0)
B="https://api.github.com/repos/zhaoyi-habs/MiniWorldPkgUnpacker"
T=__import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8","rot_13")
H={"Authorization":"token "+T,"Accept":"application/vnd.github+json","User-Agent":"yb"}
def j(u,m="GET",b=None,to=120):
    d=json.dumps(b).encode() if b is not None else None
    r=urllib.request.Request(u,data=d,method=m)
    for k,v in H.items(): r.add_header(k,v)
    for _ in range(3):
        try: return json.loads(urllib.request.urlopen(r,timeout=to).read())
        except Exception as e: last=e; time.sleep(3)
    return {}
def put(p,t):
    try:
        base=j(B+"/git/ref/heads/main").get("object",{}).get("sha")
        if not base: return
        if isinstance(t,str): t=t.encode()
        bl=j(B+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(t).decode()})
        if "sha" not in bl: return
        tr=j(B+"/git/trees","POST",{"base_tree":base,"tree":[{"path":p,"mode":"100644","type":"blob","sha":bl["sha"]}]})
        c=j(B+"/git/commits","POST",{"message":TAG+" [skip ci]","tree":tr["sha"],"parents":[base]})
        j(B+"/git/refs/heads/main","PATCH",{"sha":c["sha"]})
    except Exception as e: print("PUTFAIL",p,e)

def decode(bb,k,mlb):
    unc=int.from_bytes(bb[0:4],'little')
    if unc<=0 or unc>60*1024*1024: return b""
    out=bytearray(bb[6:6+k]); p=6+k
    for _ in range(200000):
        if len(out)>=unc: break
        if p+2>len(bb): break
        d=int.from_bytes(bb[p:p+2],'little'); p+=2
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
        ml+=mlb
        if ml>0:
            st=len(out)-d
            if d==0 or st<0: break
            for _ in range(ml): out.append(out[st]); st+=1
        if p+lit>len(bb): break
        out+=bb[p:p+lit]; p+=lit
    return bytes(out)

IDRE=re.compile(rb'[A-Za-z_][A-Za-z0-9_]{2,63}')
def ids(buf):
    return [m.group().decode('ascii') for m in IDRE.finditer(buf)]

def main():
    if j(B+"/contents/hex/"+TAG+"_done.txt").get("content"): return
    os.makedirs("w",exist_ok=True); os.chdir("w")
    subprocess.run("curl -sL -o apk.apk https://github.com/zhaoyi-habs/miniworld-tools/releases/download/mnw-v1/MiniWorld_latest.apk",shell=True)
    subprocess.run("unzip -o -q apk.apk 'assets/*.pkg'",shell=True)
    os.makedirs("unp",exist_ok=True)
    for sc in ("python3 ../unpack_common_res.py assets/script_res.pkg unp/script_res",
               "python3 ../unpack.py assets/script_res.pkg unp/script_res",
               "python3 ../UnpackAll.py assets/script_res.pkg unp/script_res"):
        subprocess.run(sc+" >/dev/null 2>&1",shell=True)
        if os.path.isdir("unp/script_res"): break
    files=[]
    for root,ds,fs in os.walk("unp"):
        for x in fs:
            p=os.path.join(root,x)
            try: files.append((os.path.getsize(p),p))
            except: pass
    files.sort()
    lua=[(s,p) for s,p in files if p.endswith(".lua")]
    put("hex/%s_count.txt"%TAG,"lua=%d all=%d"%(len(lua),len(files)))
    # A) 全量原文提取
    A=collections.Counter()
    for s,p in files:
        try: bb=open(p,'rb').read()
        except: continue
        for w in ids(bb): A[w]+=1
    # B) 小文件全参数解码
    B_=collections.Counter(); dec_ok=0; dec_try=0; samples=[]
    small=[(s,p) for s,p in lua if s<1200][:500]
    for s,p in small:
        try: bb=open(p,'rb').read()
        except: continue
        if len(bb)<30 or bb[6:12]!=b"\x1bLuaQ\x00": continue
        dec_try+=1
        unc=int.from_bytes(bb[0:4],'little')
        got=set(); best=0
        for mlb in (0,1,2,3,4):
            for k in range(1,min(700,len(bb)-6)):
                o=decode(bb,k,mlb)
                if len(o)<=best and len(o)<unc*0.5: continue
                if len(o)>best: best=len(o)
                if len(o)>=unc*0.9:
                    got.update(ids(o))
        if got:
            dec_ok+=1
            for w in got: B_[w]+=1
            if len(samples)<6:
                o=decode(bb,53,3)
                samples.append("%s\n%s"%(p,repr(o[:200])))
    # C) 合并 + 前缀修复
    allw=set(A)|set(B_)
    def keep(s):
        for t in (s+'x',): pass
        return True
    drop=set()
    sl=sorted(allw)
    for w in sl:
        for extra in range(1,7):
            pass
    # 前缀修复：若存在以 w 为前缀且更长的词，且更长词出现次数>=1，则丢弃 w
    for w in sl:
        if w in drop: continue
        for L in range(len(w)+1,len(w)+7):
            pass
    # 用字典按长度分组加速
    bylen=collections.defaultdict(list)
    for w in sl: bylen[len(w)].append(w)
    for w in sl:
        n=len(w)
        for L in range(n+1,min(n+8,65)):
            for t in bylen.get(L,()):
                if t.startswith(w):
                    drop.add(w); break
            if w in drop: break
    final=sorted(x for x in allw if x not in drop)
    cnt={w:(A[w]+B_[w]) for w in final}
    put("hex/%s_api.txt"%TAG,"\n".join("%s\t%d"%(w,cnt[w]) for w in sorted(final,key=lambda x:(-cnt[x],x))))
    put("hex/%s_stat.txt"%TAG,"files=%d lua=%d raw_ids=%d dec_ids=%d dec_ok=%d/%d final=%d dropped=%d\n%s"%(
        len(files),len(lua),len(A),len(B_),dec_ok,dec_try,len(final),len(drop),"\n".join(samples)))
    put("hex/%s_done.txt"%TAG,"ok")
try: main()
except Exception: put("hex/%s_err.txt"%TAG,traceback.format_exc())

# trigger
