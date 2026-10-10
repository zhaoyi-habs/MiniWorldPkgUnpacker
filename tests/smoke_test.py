# -*- coding: utf-8 -*-
import os,sys,subprocess,base64,json,urllib.request,traceback,re,collections
TAG="s11"
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

ID=re.compile(rb'[A-Za-z_][A-Za-z0-9_]{3,63}')
KW={'and','or','not','nil','true','false','local','function','return','end','then','else','elseif','for','while','do','break','repeat','until','if','in','self','this','next','type','string','table','math','print','pairs','ipairs','require','module','class','new','init','ctor','super','tostring','tonumber','unpack','select','setmetatable','getmetatable','rawget','rawset','error','assert','pcall','xpcall','loadstring','load','dofile','loadfile','__index','__newindex','__add','__call','__tostring','__gc','__mode','__metatable','__len','__eq','__lt','__le','__concat','__unm','__div','__mul','__sub','__pow','__mod'}
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
    ncomp=0; nplain=[]; ncsv=0; nother=0
    for s,p in lua:
        try: h=open(p,'rb').read(12)
        except: continue
        if h[6:11]==b'\x1bLuaQ' or h[0:5]==b'\x1bLuaQ': ncomp+=1
        else: nplain.append((s,p))
    allf=[]
    for root,ds,fs in os.walk("unp"):
        for x in fs: allf.append(os.path.join(root,x))
    put("hex/%s_stat.txt"%TAG,"lua=%d comp=%d plain=%d all=%d"%(len(lua),ncomp,len(nplain),len(allf)))
    # A) 原始样本回传：最小几个压缩 lua + 非压缩 lua
    out=[]
    for s,p in lua[:4]:
        try: b=open(p,'rb').read()
        except: continue
        out.append("##### RAW %s size=%d"%(p.split('unp/')[-1],len(b)))
        out.append(b[:4096].hex())
    for s,p in nplain[:4]:
        try: b=open(p,'rb').read()
        except: continue
        out.append("##### PLAIN %s size=%d"%(p.split('unp/')[-1],len(b)))
        out.append(b[:1500].hex())
    put("hex/%s_raw.txt"%TAG,"\n".join(out))
    # B) 关键脚本目录原始流直读字符串
    KEY=('luascript/ugc/','sandboxengine/','miniui/module/ugc/','scriptsupport/','luascript/')
    groups=collections.defaultdict(collections.Counter)
    glob=collections.Counter()
    for s,p in lua:
        rel=p.split('unp/')[-1].replace('\\','/')
        low=rel.lower()
        if not any(k in low for k in KEY): continue
        try: b=open(p,'rb').read()
        except: continue
        g=rel.rsplit('/',1)[0]
        ws=set()
        for m in ID.finditer(b):
            w=m.group().decode('ascii')
            ws.add(w)
        for w in ws:
            if iskw(w) or w.isdigit(): continue
            groups[g][w]+=1
            glob[w]+=1
    lines=[]
    for g in sorted(groups):
        cc=[(w,c) for w,c in groups[g].most_common() if c>=2 or len(w)>=6]
        if not cc: continue
        lines.append("\n##### %s  (%d ids)"%(g,len(cc)))
        lines+=["%s\t%d"%(w,c) for w,c in cc[:1200]]
    put("hex/%s_dir.txt"%TAG,"\n".join(lines))
    put("hex/%s_all.txt"%TAG,"\n".join("%s\t%d"%(w,c) for w,c in glob.most_common() if c>=3 or len(w)>=7))
    put("hex/%s_done.txt"%TAG,"ok")
try: main()
except Exception: put("hex/%s_err.txt"%TAG,traceback.format_exc())
