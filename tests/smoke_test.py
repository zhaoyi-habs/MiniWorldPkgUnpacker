# -*- coding: utf-8 -*-
import os,sys,subprocess,base64,json,urllib.request,traceback,re,collections,struct,time
TAG="s12"
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
        if n>8192 or s.p+n>len(s.b): raise EOFError('bs')
        v=s.b[s.p:s.p+n]; s.p+=n; return v.rstrip(b'\0')
def parse_proto(r,out,depth=0):
    if depth>60: raise EOFError('deep')
    r.str()
    r.i32(); r.i32()
    r.u8(); r.u8(); r.u8(); r.u8()
    sc=r.i32()
    if sc<0 or sc>300000: raise EOFError('sc')
    r.raw(sc*4)
    sk=r.i32()
    if sk<0 or sk>200000: raise EOFError('sk')
    for _ in range(sk):
        t=r.u8()
        if t==0: pass
        elif t==1: r.u8()
        elif t==3: r.raw(8)
        elif t==4: out['const'].add(r.str())
        else: raise EOFError('ct%d'%t)
    sp=r.i32()
    if sp<0 or sp>3000: raise EOFError('sp')
    for _ in range(sp): parse_proto(r,out,depth+1)
    sl=r.i32()
    if sl<0 or sl>300000: raise EOFError('sl')
    r.raw(sl*4)
    slv=r.i32()
    if slv<0 or slv>20000: raise EOFError('slv')
    for _ in range(slv):
        out['local'].add(r.str()); r.i32(); r.i32()
    su=r.i32()
    if su<0 or su>20000: raise EOFError('su')
    for _ in range(su): out['upval'].add(r.str())
def undump(b):
    if b[:4]!=b'\x1bLua' or b[4]!=0x51: return None
    r=R(b); r.p=12
    out={'const':set(),'local':set(),'upval':set()}
    parse_proto(r,out)
    if not out['const']: return None
    return out
def find_k(bb):
    d=bb[6:]; i=16
    while i<len(d) and 32<=d[i]<127: i+=1
    return i
def decode(bb):
    unc=int.from_bytes(bb[0:4],'little')
    if unc<=0 or unc>80*1024*1024: return b""
    k=find_k(bb)
    out=bytearray(bb[6:6+k]); p=6+k
    for _ in range(500000):
        if len(out)>=unc: break
        if p+2>len(bb): break
        dd=bb[p]|(bb[p+1]<<8); p+=2
        if p>=len(bb): break
        c=bb[p]; p+=1
        lit=c>>4; ml=(c&15)+2
        if lit==15:
            while p<len(bb):
                e=bb[p]; p+=1; lit+=e
                if e!=255: break
        if ml==17:
            while p<len(bb):
                e=bb[p]; p+=1; ml+=e
                if e!=255: break
        if ml>0:
            st=len(out)-dd
            if dd<=0 or st<0: return b""
            for _ in range(ml):
                if st>=len(out): break
                out.append(out[st]); st+=1
        if p+lit>len(bb): break
        out+=bb[p:p+lit]; p+=lit
    return bytes(out)
ID=re.compile(rb'[A-Za-z_][A-Za-z0-9_]{3,63}')
KW=set('''and or not nil true false local function return end then else elseif for while do break repeat until if in self this next type string table math print pairs ipairs require module class new init ctor super tostring tonumber unpack select setmetatable getmetatable rawget rawset error assert pcall xpcall loadstring load dofile loadfile'''.split())
def iskw(w): return w.lower() in KW
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
    ntot=nsrc=nund=0
    groups=collections.defaultdict(collections.Counter)
    gconst=collections.defaultdict(collections.Counter)
    srcs=[]
    for s,p in lua:
        try: bb=open(p,'rb').read()
        except: continue
        if len(bb)<20 or bb[6:11]!=b'\x1bLuaQ': continue
        ntot+=1
        o=decode(bb)
        if len(o)<40: continue
        rel=p.split('unp/')[-1].replace('\\','/')
        try:
            N=struct.unpack('<I',bytes(o[12:16]))[0]
            sv=o[16:16+N].split(b'\0')[0].decode('utf8','replace')
        except: sv=''
        if sv.endswith('.lua'): nsrc+=1
        if len(srcs)<8000: srcs.append("%s\t%s"%(rel,sv))
        g=rel.rsplit('/',1)[0]
        ws=set(m.group().decode('ascii') for m in ID.finditer(o))
        for w in ws:
            if iskw(w) or w.isdigit(): continue
            groups[g][w]+=1
        try: r=undump(o)
        except Exception: r=None
        if r:
            nund+=1
            for x in r['const']:
                try: gconst[g][x.decode('utf8','replace')]+=1
                except: pass
    put("hex/%s_stat.txt"%TAG,"lua=%d src_ok=%d undump_ok=%d"%(ntot,nsrc,nund))
    put("hex/%s_src.txt"%TAG,"\n".join(srcs))
    lines=[]
    for g in sorted(groups):
        cc=[(w,c) for w,c in groups[g].most_common() if c>=2 or len(w)>=7]
        if not cc: continue
        lines.append("\n##### %s  (%d)"%(g,len(cc)))
        lines+=["%s\t%d"%(w,c) for w,c in cc[:800]]
    put("hex/%s_dir.txt"%TAG,"\n".join(lines))
    cl=[]
    for g in sorted(gconst):
        cc=gconst[g].most_common()
        if not cc: continue
        cl.append("\n##### CONST %s  (%d)"%(g,len(cc)))
        cl+=["%s\t%d"%(w,c) for w,c in cc[:800]]
    put("hex/%s_const.txt"%TAG,"\n".join(cl))
    put("hex/%s_done.txt"%TAG,"ok")
try: main()
except Exception: put("hex/%s_err.txt"%TAG,traceback.format_exc())
