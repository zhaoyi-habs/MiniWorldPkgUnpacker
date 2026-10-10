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
