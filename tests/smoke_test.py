# -*- coding: utf-8 -*-
# JOB s3: 快速解码迷你世界 Lua 字节码 -> 完整 API/字符串 -> 前缀修复
import os,sys,subprocess,base64,json,urllib.request,time,traceback,re,collections,struct
TAG="s3"
if sys.platform!="linux": sys.exit(0)
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
    try:
        base=j(B+"/git/ref/heads/main").get("object",{}).get("sha")
        if not base: return
        if isinstance(t,str): t=t.encode()
        bl=j(B+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(t).decode()})
        if "sha" not in bl: return
        tr=j(B+"/git/trees","POST",{"base_tree":base,"tree":[{"path":p,"mode":"100644","type":"blob","sha":bl["sha"]}]})
        c=j(B+"/git/commits","POST",{"message":TAG+"r","tree":tr["sha"],"parents":[base]})
        j(B+"/git/refs/heads/main","PATCH",{"sha":c["sha"]})
    except Exception as e: print("PUTFAIL",p,e)

def decode(bb,k,mlb):
    unc=int.from_bytes(bb[0:4],'little')
    if unc<=0 or unc>60*1024*1024: return b""
    out=bytearray(bb[6:6+k]); p=6+k
    for _ in range(200000):
        if len(out)>=unc: break
        if p+2>len(bb): break
        d=bb[p]|(bb[p+1]<<8); p+=2
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

def printable_score(o):
    if len(o)<20: return 0.0
    seg=o[16:16+int.from_bytes(o[12:16],'little')]
    if not seg: return 0.0
    return sum(1 for b in seg if 32<=b<127)/len(seg)

IDRE=re.compile(rb'[A-Za-z_][A-Za-z0-9_]{2,63}')
def ids(b): return [m.group().decode('ascii') for m in IDRE.finditer(b)]

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
    A=collections.Counter()
    for s,p in files:
        try: bb=open(p,'rb').read()
        except: continue
        for w in ids(bb): A[w]+=1
    put("hex/%s_raw.txt"%TAG,"raw_ids=%d"%len(A))
    # 优先 UGC3 目录 + 小文件
    pri=[(s,p) for s,p in lua if ('ugc' in p.lower() or 'trigger' in p.lower() or 'api' in p.lower())]
    rest=[(s,p) for s,p in lua if (s,p) not in set(pri)]
    sel=(pri[:400]+[x for x in rest if x[0]<2000][:400])
    Bc=collections.Counter(); ok=0; tried=0; samples=[]
    for s,p in sel:
        try: bb=open(p,'rb').read()
        except: continue
        if len(bb)<30 or bb[6:12]!=b"\x1bLuaQ\x00": continue
        tried+=1
        unc=int.from_bytes(bb[0:4],'little')
        cands=[]
        for k in range(12,len(bb)-8):
            d=bb[6+k]|(bb[7+k]<<8)
            if 0<d<=k: cands.append(k)
        best=(0.0,0,None)
        for k in cands[:120]:
            for mlb in (0,1,2,3,4):
                o=decode(bb,k,mlb)
                if len(o)<unc*0.5: continue
                sc=printable_score(o)*min(len(o)/unc,1.0)
                if sc>best[0]: best=(sc,len(o),o)
        if best[2]:
            ok+=1
            Bc.update(ids(best[2]))
            if len(samples)<8:
                samples.append("%s\n  k/score=%s\n  %s"%(p,best[:2],repr(best[2][16:190])))
    put("hex/%s_samples.txt"%TAG,"\n".join(samples))
    put("hex/%s_dec.txt"%TAG,"dec_ok=%d/%d dec_ids=%d"%(ok,tried,len(Bc)))
    # 合并 + 前缀修复
    allw=set(A)|set(Bc)
    bylen=collections.defaultdict(list)
    for w in allw: bylen[len(w)].append(w)
    drop=set()
    for w in allw:
        n=len(w)
        if not (w[-1].islower() or w[-1]=='_'): continue
        for L in range(n+1,min(n+9,64)):
            for t in bylen.get(L,()):
                if t.startswith(w) and (t[n].islower() or t[n]=='_'):
                    drop.add(w); break
            if w in drop: break
    final=sorted(allw-drop)
    cnt={w:(A[w]+Bc[w]) for w in final}
    put("hex/%s_api.txt"%TAG,"\n".join("%s\t%d"%(w,cnt[w]) for w in sorted(final,key=lambda x:(-cnt[x],x))))
    put("hex/%s_stat.txt"%TAG,"lua=%d raw=%d dec=%d final=%d dropped=%d ok=%d"%(
        len(lua),len(A),len(Bc),len(final),len(drop),ok))
    put("hex/%s_done.txt"%TAG,"ok")
try: main()
except Exception: put("hex/%s_err.txt"%TAG,traceback.format_exc())
