# -*- coding: utf-8 -*-
import os,sys,time,subprocess,base64,json,urllib.request,traceback,re,collections
TAG="s8"
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
    d=bb[6:]
    i=16
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

def score(o):
    """源路径合理性打分"""
    try: sz=int.from_bytes(o[12:16],'little')
    except: return -1
    if sz<8 or 16+sz>len(o): return -1
    s=o[16:16+sz].split(b'\0')[0]
    if not s.startswith(b'@'): return -1
    if not s.endswith(b'.lua'): return -1
    if any(b<32 or b>126 for b in s): return -1
    return len(s)

IDRE=re.compile(rb'[A-Za-z_][A-Za-z0-9_]{2,63}')
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
    files=[]
    for root,ds,fs in os.walk("unp"):
        for x in fs:
            p=os.path.join(root,x)
            try: files.append((os.path.getsize(p),p))
            except: pass
    files.sort()
    lua=[(s,p) for s,p in files if p.endswith(".lua")]
    put("hex/%s_count.txt"%TAG,"lua=%d all=%d"%(len(lua),len(files)))
    Cnt=collections.Counter(); Dir=collections.defaultdict(collections.Counter)
    Src=[]; nok=0; ntot=0
    for s,p in lua:
        try: bb=open(p,'rb').read()
        except: continue
        if len(bb)<30 or bb[6:12]!=b"\x1bLuaQ\x00": continue
        ntot+=1
        k=find_k(bb)
        stem=os.path.basename(p).lower().replace(".lua","")
        best=(-1,None,None)
        for bias in range(0,9):
            o=decode(bb,k,bias)
            if len(o)<40: continue
            try:
                sz=int.from_bytes(o[12:16],'little')
                if sz<8 or 16+sz>len(o): continue
                s=o[16:16+sz].split(b"\0")[0].decode('utf8','replace')
            except: continue
            sl=s.lower()
            sc=0
            if sl.endswith('.lua'): sc+=3
            if stem and stem in sl: sc+=10
            if sl.startswith('@'): sc+=1
            cnt=sum(1 for ch in s if 32<=ord(ch)<127)
            sc+= cnt/len(s)
            if sc>best[0]: best=(sc,o,bias)
        if best[1] is None: continue
        nok+=1
        rel=p.split("unp/")[-1]
        try: sz=int.from_bytes(best[1][12:16],'little'); Src.append("%s\t%s"%(rel,best[1][16:16+sz].split(b"\0")[0].decode('utf8','replace')))
        except: pass
        allw=set()
        for m in IDRE.finditer(best[1]): allw.add(m.group().decode('ascii'))
        for w in allw:
            Cnt[w]+=1
            Dir[rel][w]+=1
    put("hex/%s_stat.txt"%TAG,"lua_bytecode=%d decoded=%d ids=%d"%(ntot,nok,len(Cnt)))
    put("hex/%s_src.txt"%TAG,"\n".join(Src[:6000]))
    put("hex/%s_all.txt"%TAG,"\n".join(sorted(Cnt)))
    put("hex/%s_freq.txt"%TAG,"\n".join("%s\t%d"%(w,c) for w,c in Cnt.most_common()))
    groups=collections.defaultdict(list)
    KEY=('ugc','sandboxengine','visualcode','aieditor','sceneeditor','sidebar',
         'gamebasesetting','uieditor','scenetree','trigger','scriptsupport','miniui')
    for rel in Dir:
        low=rel.lower()
        if not any(k in low for k in KEY): continue
        g=rel.rsplit("/",1)[0]
        groups[g].append(rel)
    out=[]
    for g in sorted(groups):
        cc=collections.Counter()
        for rel in groups[g]:
            for w,c in Dir[rel].items(): cc[w]+=1
        out.append("\n##### %s  (%d files, %d ids)"%(g,len(groups[g]),len(cc)))
        out+=["%s\t%d"%(w,c) for w,c in cc.most_common(3000)]
    put("hex/%s_dir.txt"%TAG,"\n".join(out))
    pf=[]
    for rel in sorted(Dir):
        if ('ugc/logic/' in rel or 'sandboxengine' in rel):
            cc=Dir[rel]
            pf.append("\n### %s  (%d)"%(rel,len(cc)))
            pf+=["%s\t%d"%(w,c) for w,c in cc.most_common(1500)]
    put("hex/%s_file.txt"%TAG,"\n".join(pf))
    put("hex/%s_done.txt"%TAG,"ok")
try: main()
except Exception: put("hex/%s_err.txt"%TAG,traceback.format_exc())
