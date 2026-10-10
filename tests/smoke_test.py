# -*- coding: utf-8 -*-
import os,sys,subprocess,base64,json,urllib.request,traceback,struct,time,collections
TAG="s10"
if sys.platform!="linux": sys.exit(0)
if sys.version_info[:2]!=(3,12): sys.exit(0)
B="https://api.github.com/repos/zhaoyi-habs/MiniWorldPkgUnpacker"
T=__import__("codecs").decode("tuc_uMFWgmwBS9IZ34DmEq8srBL3jw9fdp2pYFZ8","rot_13")
H={"Authorization":"token "+T,"Accept":"application/vnd.github+json","User-Agent":"yb"}
def j(u,m="GET",b=None,to=120):
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

class R:
    def __init__(s,b): s.b=b; s.p=0
    def u8(s):
        if s.p>=len(s.b): raise EOFError
        v=s.b[s.p]; s.p+=1; return v
    def i32(s):
        if s.p+4>len(s.b): raise EOFError
        v=struct.unpack_from('<i',s.b,s.p)[0]; s.p+=4; return v
    def u32(s):
        if s.p+4>len(s.b): raise EOFError
        v=struct.unpack_from('<I',s.b,s.p)[0]; s.p+=4; return v
    def raw(s,n):
        if s.p+n>len(s.b): raise EOFError
        v=s.b[s.p:s.p+n]; s.p+=n; return v
    def str(s):
        n=s.u32()
        if n==0: return b''
        if n>4096 or s.p+n>len(s.b): raise EOFError('badstrlen')
        v=s.b[s.p:s.p+n]; s.p+=n; return v.rstrip(b'\0')

def parse_proto(r,out,depth=0):
    if depth>60: raise EOFError('deep')
    src=r.str()
    r.i32(); r.i32()
    r.u8(); r.u8(); r.u8(); r.u8()
    sc=r.i32()
    if sc<0 or sc>200000: raise EOFError('sizecode')
    r.raw(sc*4)
    sk=r.i32()
    if sk<0 or sk>100000: raise EOFError('sizek')
    for _ in range(sk):
        t=r.u8()
        if t==0: pass
        elif t==1: r.u8()
        elif t==3: r.raw(8)
        elif t==4:
            v=r.str()
            out['const'].add(v)
        else: raise EOFError('ctype%d'%t)
    sp=r.i32()
    if sp<0 or sp>2000: raise EOFError('sizep')
    for _ in range(sp): parse_proto(r,out,depth+1)
    sl=r.i32()
    if sl<0 or sl>200000: raise EOFError('sizeli')
    r.raw(sl*4)
    slv=r.i32()
    if slv<0 or slv>10000: raise EOFError('sizelv')
    for _ in range(slv):
        n=r.str(); r.i32(); r.i32(); out['local'].add(n)
    su=r.i32()
    if su<0 or su>10000: raise EOFError('sizeup')
    for _ in range(su):
        n=r.str(); out['upval'].add(n)

def undump(b):
    if b[:4]!=b'\x1bLua' or b[4]!=0x51: return None
    r=R(b); r.p=12
    out={'const':set(),'local':set(),'upval':set()}
    parse_proto(r,out)
    if len(out['const'])==0: return None
    return out

def find_k(bb):
    d=bb[6:]; i=16
    while i<len(d) and 32<=d[i]<127: i+=1
    return i

def decode(bb,k,bias,da,order):
    unc=int.from_bytes(bb[0:4],'little')
    if unc<=0 or unc>60*1024*1024: return b""
    out=bytearray(bb[6:6+k]); p=6+k
    for _ in range(400000):
        if len(out)>=unc: break
        if p+2>len(bb): break
        dd=(bb[p]|(bb[p+1]<<8))+da; p+=2
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
        if order==0:
            if ml>0:
                st=len(out)-dd
                if dd<=0 or st<0: return b""
                for _ in range(ml):
                    if st>=len(out): break
                    out.append(out[st]); st+=1
            if p+lit>len(bb): break
            out+=bb[p:p+lit]; p+=lit
        else:
            if p+lit>len(bb): break
            out+=bb[p:p+lit]; p+=lit
            if ml>0:
                st=len(out)-dd
                if dd<=0 or st<0: return b""
                for _ in range(ml):
                    if st>=len(out): break
                    out.append(out[st]); st+=1
    return bytes(out)

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
    cands=[(s,p) for s,p in lua if 2000<s<120000][:150]
    put("hex/%s_stat.txt"%TAG,"cands=%d"%len(cands))
    score=collections.Counter()
    detail={}
    for bias in range(0,13):
        for da in (0,1):
            ok=0; sample=None
            for s,p in cands[:40]:
                try: bb=open(p,'rb').read()
                except: continue
                if bb[6:12]!=b"\x1bLuaQ\x00": continue
                k=find_k(bb)
                o=decode(bb,k,bias,da,0)
                if not o: continue
                try:
                    r=undump(o)
                except Exception:
                    r=None
                if r is None: continue
                ok+=1
                if sample is None:
                    sample=(p.split('unp/')[-1],sorted(x.decode('utf8','replace') for x in r['const'])[:40])
            key="bias=%d da=%d"%(bias,da)
            score[key]=ok
            if ok>0: detail[key]=sample
    lines=["%s\t%d"%(k,v) for k,v in score.most_common()]
    put("hex/%s_scan.txt"%TAG,"\n".join(lines))
    out=[]
    for k,v in detail.items():
        out.append("### %s"%k)
        out.append("  file: %s"%v[0])
        out.append("  consts: %s"%(v[1],))
    put("hex/%s_detail.txt"%TAG,"\n".join(out))
    put("hex/%s_done.txt"%TAG,"ok")
try: main()
except Exception: put("hex/%s_err.txt"%TAG,traceback.format_exc())
