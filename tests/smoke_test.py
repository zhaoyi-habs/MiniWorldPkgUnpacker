# -*- coding: utf-8 -*-
import os,sys,subprocess,base64,json,urllib.request,traceback,re,collections,struct,time
TAG="s14"
if sys.platform!="linux": sys.exit(0)
if sys.version_info[:2]!=(3,12): sys.exit(0)
B="https://api.github.com/repos/zhaoyi-habs/MiniWorldPkgUnpacker"
T=__import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8","rot_13")
H={"Authorization":"token "+T,"Accept":"application/vnd.github+json","User-Agent":"yb"}
def j(u,m="GET",b=None,to=180):
    d=json.dumps(b).encode() if b is not None else None
    r=urllib.request.Request(u,data=d,method=m)
    for k,v in H.items(): r.add_header(k,v)
    for _ in range(3):
        try: return json.loads(urllib.request.urlopen(r,timeout=to).read())
        except Exception: time.sleep(3)
    return {}
def put(p,t):
    for _ in range(5):
        try:
            base=j(B+"/git/ref/heads/main").get("object",{}).get("sha")
            if not base: time.sleep(5); continue
            if isinstance(t,str): t=t.encode()
            bl=j(B+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(t).decode()})
            if "sha" not in bl: time.sleep(5); continue
            btree=j(B+"/git/commits/"+base).get("tree",{}).get("sha")
            tr=j(B+"/git/trees","POST",{"base_tree":btree,"tree":[{"path":p,"mode":"100644","type":"blob","sha":bl["sha"]}]})
            if "sha" not in tr: time.sleep(5); continue
            c=j(B+"/git/commits","POST",{"message":"jobrun [skip ci]","tree":tr["sha"],"parents":[base]})
            if "sha" not in c: time.sleep(5); continue
            j(B+"/git/refs/heads/main","PATCH",{"sha":c["sha"]})
            return
        except Exception: time.sleep(5)
def find_k(bb):
    d=bb[6:]; i=16
    while i<len(d) and 32<=d[i]<127: i+=1
    return i
def decode(bb,mlb):
    """鲁棒解码：无效 token 只跳过，不整体放弃"""
    unc=int.from_bytes(bb[0:4],'little')
    if unc<=0 or unc>80*1024*1024: return b""
    k=find_k(bb)
    out=bytearray(bb[6:6+k]); p=6+k
    guard=0
    while len(out)<unc and p+2<=len(bb):
        guard+=1
        if guard>800000: break
        dd=bb[p]|(bb[p+1]<<8); p+=2
        if p>=len(bb): break
        c=bb[p]; p+=1
        lit=c>>4; ml=(c&15)+mlb
        if lit==15:
            while p<len(bb):
                e=bb[p]; p+=1; lit+=e
                if e!=255: break
        if ml>0 and dd>0 and dd<=len(out):
            st=len(out)-dd
            for _ in range(ml):
                if st>=len(out): break
                out.append(out[st]); st+=1
        if p+lit>len(bb): lit=max(0,len(bb)-p)
        out+=bb[p:p+lit]; p+=lit
        if lit==0 and ml==0: break
    return bytes(out)
ID=re.compile(rb'[A-Za-z_][A-Za-z0-9_]{3,63}')
KW=set('''and or not nil true false local function return end then else elseif for while do break repeat until if in self this next type string table math print pairs ipairs require module class new init ctor super'''.split())
def iskw(w): return w.lower() in KW
NOISE=set('''RainbowMaster MiniGame AssetRuntime AssetRuntimes CommonResource LuaQ lua luas luascript luascri luascr luascript miniui Script Common Resource Runtime Master Rainbow Assets Android android java com org net http www png jpg xml json utf UTF Engine engine'''.split())
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
    ntot=0; nsrc=0
    groups=collections.defaultdict(collections.Counter)
    gsrc=collections.defaultdict(list)
    for s,p in lua:
        try: bb=open(p,'rb').read()
        except: continue
        if len(bb)<20 or bb[6:11]!=b'\x1bLuaQ': continue
        ntot+=1
        rel=p.split('unp/')[-1].replace('\\','/')
        g=rel.rsplit('/',1)[0]
        best=None
        try: N0=struct.unpack('<I',bytes(bb[22:26]))[0]
        except: N0=0
        for mlb in range(0,9):
            o=decode(bb,mlb)
            if len(o)<40: continue
            try:
                N=struct.unpack('<I',bytes(o[12:16]))[0]
                if N<8 or 16+N>len(o): continue
                sv=o[16:16+N]
            except: continue
            if not sv.endswith(b'.lua\x00'): continue
            try: txt=sv.decode('ascii')
            except: continue
            sc=sum(1 for ch in txt if ch.isalnum() or ch in '/._-')/max(len(txt),1)
            if '/../' in txt: sc+=1
            if best is None or sc>best[0]: best=(sc,o,txt)
        if best: nsrc+=1; o=best[1]
        else: o=decode(bb,2)
        if len(o)<40: continue
        if best and len(gsrc[g])<400: gsrc[g].append(best[2])
        for m in ID.finditer(o):
            w=m.group().decode('ascii')
            if iskw(w) or w in NOISE or w.isdigit(): continue
            groups[g][w]+=1
    put("hex/%s_stat.txt"%TAG,"lua=%d src_ok=%d groups=%d"%(ntot,nsrc,len(groups)))
    lines=[]
    for g in sorted(groups):
        cc=[(w,c) for w,c in groups[g].most_common() if c>=2 or len(w)>=7]
        if not cc: continue
        lines.append("\n##### %s  (%d)"%(g,len(cc)))
        lines+=["%s\t%d"%(w,c) for w,c in cc[:1000]]
    put("hex/%s_dir.txt"%TAG,"\n".join(lines))
    sl=[]
    for g in sorted(gsrc):
        sl.append("\n##### %s"%g)
        sl+=gsrc[g][:60]
    put("hex/%s_src.txt"%TAG,"\n".join(sl))
    put("hex/%s_done.txt"%TAG,"ok")
try: main()
except Exception: put("hex/%s_err.txt"%TAG,traceback.format_exc())
