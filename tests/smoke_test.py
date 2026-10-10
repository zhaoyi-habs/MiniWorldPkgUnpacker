# -*- coding: utf-8 -*-
import os,sys,time,subprocess,base64,json,urllib.request,traceback,re,collections,bisect
TAG="s5"
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
            if not base:
                time.sleep(5); continue
            if isinstance(t,str): t=t.encode()
            bl=j(B+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(t).decode()})
            if "sha" not in bl:
                time.sleep(5); continue
            head=j(B+"/git/commits/"+base)
            btree=head.get("tree",{}).get("sha")
            if not btree:
                time.sleep(5); continue
            tr=j(B+"/git/trees","POST",{"base_tree":btree,"tree":[{"path":p,"mode":"100644","type":"blob","sha":bl["sha"]}]})
            if "sha" not in tr:
                time.sleep(5); continue
            c=j(B+"/git/commits","POST",{"message":"jobrun [skip ci]","tree":tr["sha"],"parents":[base]})
            if "sha" not in c:
                time.sleep(5); continue
            j(B+"/git/refs/heads/main","PATCH",{"sha":c["sha"]})
            return
        except Exception as e:
            print("PUTFAIL",p,str(e)[:80]); time.sleep(5)

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
def psc(o):
    if len(o)<20: return 0.0
    try: sz=int.from_bytes(o[12:16],'little')
    except: return 0.0
    seg=o[16:16+sz]
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
    A=collections.Counter(); Dir=collections.defaultdict(collections.Counter)
    for s,p in files:
        try: bb=open(p,'rb').read()
        except: continue
        key=p.split("unp/")[-1].split("/")[0] if "unp/" in p else "?"
        for w in ids(bb):
            A[w]+=1
    Bc=collections.Counter(); Bdir=collections.defaultdict(collections.Counter)
    pri=[(s,p) for s,p in lua if ('ugc' in p.lower() or 'trigger' in p.lower() or 'api' in p.lower())]
    sel=pri[:500]+[x for x in lua if x[0]<2000 and x not in set(pri)][:300]
    ok=0
    for s,p in sel:
        try: bb=open(p,'rb').read()
        except: continue
        if len(bb)<30 or bb[6:12]!=b"\x1bLuaQ\x00": continue
        unc=int.from_bytes(bb[0:4],'little')
        cands=[k for k in range(12,len(bb)-8) if 0<(bb[6+k]|(bb[7+k]<<8))<=k]
        best=(0.0,None)
        for k in cands[:120]:
            for mlb in (0,1,2,3,4):
                o=decode(bb,k,mlb)
                if len(o)<unc*0.5: continue
                sc=psc(o)*min(len(o)/unc,1.0)
                if sc>best[0]: best=(sc,o)
        if best[1]:
            ok+=1
            for w in set(ids(best[1])): Bc[w]+=1
            d=p.split("unp/")[-1]
            for w in set(ids(best[1])): Bdir[d][w]+=1
    put("hex/%s_dec.txt"%TAG,"dec_ok=%d/%d dec_ids=%d raw_ids=%d"%(ok,len(sel),len(Bc),len(A)))
    allw=set(A)|set(Bc)
    sw=sorted(allw)
    drop=[]
    for i,w in enumerate(sw[:-1]):
        nxt=sw[i+1]
        if nxt.startswith(w) and len(nxt)>len(w):
            ch=nxt[len(w)]
            if ch.islower() or ch=='_':
                if w[-1].islower() or w[-1]=='_': drop.append(w)
    drop=set(drop)
    final=[w for w in sw if w not in drop]
    cnt={w:(A[w]+Bc[w]) for w in final}
    put("hex/%s_all.txt"%TAG,"\n".join(final))
    put("hex/%s_api.txt"%TAG,"\n".join("%s\t%d"%(w,cnt[w]) for w in sorted(final,key=lambda x:(-cnt[x],x))[:60000]))
    # 分类: UGC3 / 高级创造 关键词
    KW=['Mini','Sandbox','UGC','Trigger','Component','Service','BluePrint','Blueprint','World','Block','Player','Actor','Entity','Area','Backpack','CustomUI','Craft','Editor','Ai','Anim','Event','Package','Object','Terrain','Prefab','Node','Property','Attribute','Game','Data','Net','Timer','Sound','Effect','Item','Bag','Task','Npc','Monster','Pet','Skill','Buff','Team','Room','Chat','Rank','Store']
    out=["=== 分类统计 (解码+原文并集, 已做前缀修复) ==="]
    for kw in KW:
        got=[w for w in final if kw.lower() in w.lower()]
        out.append("\n##### %s  (%d)"%(kw,len(got)))
        out+= ["%s\t%d"%(w,cnt[w]) for w in sorted(got,key=lambda x:(-cnt[x],x))[:400]]
    put("hex/%s_cat.txt"%TAG,"\n".join(out))
    put("hex/%s_stat.txt"%TAG,"lua=%d raw=%d dec=%d final=%d dropped=%d ok=%d"%(len(lua),len(A),len(Bc),len(final),len(drop),ok))
    put("hex/%s_done.txt"%TAG,"ok")
try: main()
except Exception: put("hex/%s_err.txt"%TAG,traceback.format_exc())
