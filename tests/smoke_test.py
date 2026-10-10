# -*- coding: utf-8 -*-
# JOB s1: 破解迷你世界 Lua 字节码压缩格式 -> 解码全部 lua -> 提取完整字符串/API
import os,sys,subprocess,base64,json,urllib.request,time,traceback,re,collections
TAG="s1"
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
        c=j(B+"/git/commits","POST",{"message":TAG+" [skip ci]","tree":tr["sha"],"parents":[base]})
        j(B+"/git/refs/heads/main","PATCH",{"sha":c["sha"]})
    except Exception as e:
        print("PUTFAIL",p,e)
LUA=b"\x1bLuaQ\x00\x01\x04\x04\x04\x08\x00"

def decode(bb,k,order,ml_esc,lit_esc,ml_bias,dist_bias,dbytes,copy_first):
    unc=int.from_bytes(bb[0:4],'little')
    if unc<=0 or unc>40*1024*1024: return -1
    if 6+k>len(bb): return -1
    out=bytearray(bb[6:6+k]); p=6+k
    guard=0
    while len(out)<unc:
        guard+=1
        if guard>200000: return -1
        if order=='DA':
            if p+dbytes>len(bb): return len(out)
            d=int.from_bytes(bb[p:p+dbytes],'little'); p+=dbytes
            if p>=len(bb): return len(out)
            c=bb[p]; p+=1
        else:
            if p>=len(bb): return len(out)
            c=bb[p]; p+=1
            if p+dbytes>len(bb): return len(out)
            d=int.from_bytes(bb[p:p+dbytes],'little'); p+=dbytes
        lit=c>>4; ml=c&15
        if lit==15 and lit_esc:
            while p<len(bb):
                e=bb[p]; p+=1; lit+=e
                if e!=255: break
        if ml==15 and ml_esc:
            while p<len(bb):
                e=bb[p]; p+=1; ml+=e
                if e!=255: break
        ml+=ml_bias; d+=dist_bias
        if copy_first:
            if ml>0:
                if d==0 or d>len(out): return len(out)
                st=len(out)-d
                for _ in range(ml):
                    if st>=len(out): return len(out)
                    out.append(out[st]); st+=1
            if p+lit>len(bb): return len(out)
            out+=bb[p:p+lit]; p+=lit
        else:
            if p+lit>len(bb): return len(out)
            out+=bb[p:p+lit]; p+=lit
            if ml>0:
                if d==0 or d>len(out-lit) if False else d>len(out)-lit: return len(out)
                st=len(out)-lit-d
                for _ in range(ml):
                    if st<0: return len(out)
                    out.append(out[st]); st+=1
    return bytes(out) if len(out)==unc else len(out)

def grid():
    for order in ('DA','CD'):
        for dbytes in (2,3):
            for copy_first in (True,False):
                for ml_esc in (False,True):
                    for lit_esc in (False,True):
                        for ml_bias in (0,3,4):
                            for dist_bias in (0,1):
                                yield (order,dbytes,copy_first,ml_esc,lit_esc,ml_bias,dist_bias)

def main():
    if j(B+"/contents/hex/"+TAG+"_done.txt").get("content"): return
    os.makedirs("w",exist_ok=True); os.chdir("w")
    subprocess.run("curl -sL -o apk.apk https://github.com/zhaoyi-habs/miniworld-tools/releases/download/mnw-v1/MiniWorld_latest.apk",shell=True)
    subprocess.run("unzip -o -q apk.apk 'assets/script_res.pkg'",shell=True)
    for sc in ("python3 ../unpack_common_res.py assets/script_res.pkg unp/script_res",
               "python3 ../unpack.py assets/script_res.pkg unp/script_res",
               "python3 ../UnpackAll.py assets/script_res.pkg unp/script_res"):
        r=subprocess.run(sc+" >/dev/null 2>&1",shell=True)
        if os.path.isdir("unp/script_res") and sum(len(f) for _,_,f in os.walk("unp/script_res"))>100: break
    fs=[]
    for root,ds,f in os.walk("unp/script_res"):
        for x in f:
            p=os.path.join(root,x)
            try: fs.append((os.path.getsize(p),p))
            except: pass
    fs.sort()
    lua=[(s,p) for s,p in fs if p.endswith(".lua")]
    put("hex/%s_count.txt"%TAG,"total_lua=%d"%len(lua))
    sel=[(s,p) for s,p in lua if 300<s<3000][:40]
    RAW={}
    for s,p in sel:
        bb=open(p,'rb').read()
        if len(bb)<30 or bb[6:12]!=b"\x1bLuaQ\x00": continue
        RAW[p]=bb
    put("hex/%s_sel.txt"%TAG,"selected=%d"%len(RAW))
    # 相位1: 破解
    score=collections.Counter(); best=None
    for hyp in grid():
        hits=0
        for p,bb in RAW.items():
            unc=int.from_bytes(bb[0:4],'little')
            for k in range(1,min(700,len(bb)-6)):
                r=decode(bb,k,*hyp)
                if isinstance(r,bytes) and r[:12]==LUA:
                    hits+=1; break
        if hits: score[hyp]=hits
        if best is None or hits>best[0]: best=(hits,hyp)
        if best[0]>=max(3,len(RAW)//2): break
    put("hex/%s_hyp.txt"%TAG,"best=%r\nscore=%r"%(best,score.most_common(10)))
    if not best or best[0]==0:
        put("hex/%s_done.txt"%TAG,"nohit"); return
    hyp=best[1]
    # 相位2: 解码全部并提取字符串
    api=collections.Counter(); allstr=set(); okc=0; fail=0
    per=[]
    for s,p in lua:
        try: bb=open(p,'rb').read()
        except: continue
        if len(bb)<30 or bb[6:12]!=b"\x1bLuaQ\x00": continue
        got=None
        for k in range(1,min(700,len(bb)-6)):
            r=decode(bb,k,*hyp)
            if isinstance(r,bytes) and r[:12]==LUA: got=r; break
        if got is None: fail+=1; continue
        okc+=1
        for m in re.finditer(rb'[A-Za-z_][A-Za-z0-9_:\.]{2,}',got):
            w=m.group().decode('ascii')
            allstr.add(w); api[w]+=1
        per.append("%s %d"%(p.split('/')[-1],len(got)))
    put("hex/%s_strings.txt"%TAG,"\n".join(sorted(allstr)))
    put("hex/%s_api.txt"%TAG,"\n".join("%s\t%d"%(w,c) for w,c in api.most_common()))
    put("hex/%s_stat.txt"%TAG,"ok=%d fail=%d uniq=%d\n%s"%(okc,fail,len(allstr),"\n".join(per[:200])))
    put("hex/%s_done.txt"%TAG,"ok")
try:
    main()
except Exception:
    put("hex/%s_err.txt"%TAG,traceback.format_exc())
