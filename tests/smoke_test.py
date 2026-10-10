import os,sys,subprocess,base64,json,urllib.request,time,traceback
TAG="h3"
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
    base=j(B+"/git/ref/heads/main").get("object",{}).get("sha")
    if not base: return
    bl=j(B+"/git/blobs","POST",{"encoding":"base64","content":base64.b64encode(t.encode()).decode()})
    if "sha" not in bl: return
    tr=j(B+"/git/trees","POST",{"base_tree":base,"tree":[{"path":p,"mode":"100644","type":"blob","sha":bl["sha"]}]})
    c=j(B+"/git/commits","POST",{"message":"hex3 [skip ci]","tree":tr["sha"],"parents":[base]})
    j(B+"/git/refs/heads/main","PATCH",{"sha":c["sha"]})
LUA=b"\x1bLuaQ\x00\x01\x04\x04\x04\x08\x00"
def dec(bb,k,ml_esc,dist3):
    unc=int.from_bytes(bb[0:4],'little'); out=bytearray(bb[6:6+k]); p=6+k
    while len(out)<unc:
        if p+3>len(bb): return len(out)
        d=int.from_bytes(bb[p:p+2],'little'); p+=2
        if dist3 and d==0:
            if p+3>len(bb): return len(out)
            d=int.from_bytes(bb[p:p+3],'little'); p+=3
        if p>=len(bb): return len(out)
        c=bb[p]; p+=1
        lit=c>>4; ml=c&15
        if lit==15:
            while p<len(bb):
                e=bb[p]; p+=1; lit+=e
                if e!=255: break
        if ml==15 and ml_esc:
            while p<len(bb):
                e=bb[p]; p+=1; ml+=e
                if e!=255: break
        if d==0 or d>len(out): return len(out)
        st=len(out)-d
        for _ in range(ml):
            out.append(out[st]); st+=1
        if p+lit>len(bb): return len(out)
        out+=bb[p:p+lit]; p+=lit
    return bytes(out)
def main():
    if j(B+"/contents/hex/"+TAG+"_done.txt").get("content"): return
    os.makedirs("w",exist_ok=True); os.chdir("w")
    subprocess.run("curl -sL -o apk.apk https://github.com/zhaoyi-habs/miniworld-tools/releases/download/mnw-v1/MiniWorld_latest.apk",shell=True)
    subprocess.run("unzip -o -q apk.apk 'assets/script_res.pkg'",shell=True)
    subprocess.run("python3 ../unpack_common_res.py assets/script_res.pkg unp/script_res >/dev/null 2>&1",shell=True)
    fs=[]
    for root,ds,f in os.walk("unp/script_res"):
        for x in f: fs.append((os.path.getsize(os.path.join(root,x)),os.path.join(root,x)))
    fs.sort()
    sel=[(s,p) for s,p in fs if p.endswith(".lua") and 400<s<2500][:30]
    res=["count=%d"%len(sel)]
    for sz,path in sel:
        bb=open(path,'rb').read()
        if len(bb)<24 or bb[6:12]!=b"\x1bLuaQ\x00": continue
        unc=int.from_bytes(bb[0:4],'little')
        hit=None; best=(0,None)
        for ml_esc in (False,True):
            for dist3 in (False,True):
                for k in range(1,min(400,len(bb)-6)):
                    r=dec(bb,k,ml_esc,dist3)
                    if isinstance(r,int):
                        if r>best[0]: best=(r,(k,int(ml_esc),int(dist3)))
                        continue
                    if len(r)==unc and r[:12]==LUA:
                        hit=(k,int(ml_esc),int(dist3)); break
                if hit: break
            if hit: break
        res.append("%s unc=%d size=%d hit=%s best=%s"%(path.split('/')[-1],unc,sz,hit,best))
    put("hex/"+TAG+"_result.txt","\n".join(res))
    put("hex/"+TAG+"_done.txt","ok")
try:
    main()
except Exception:
    put("hex/"+TAG+"_err.txt",traceback.format_exc())
