
import os,io,base64,json,urllib.request
from PIL import Image
TK=os.environ.get("GH_TOKEN"); REP=os.environ.get("GITHUB_REPOSITORY")
def api(m,p,d=None):
    h={"Authorization":"Bearer "+TK,"User-Agent":"mw","Content-Type":"application/json"}
    r=urllib.request.Request("https://api.github.com/repos/%s/contents/%s"%(REP,p),data=json.dumps(d).encode() if d else None,method=m,headers=h)
    try:
        return json.load(urllib.request.urlopen(r,timeout=60))
    except Exception:
        return {}
def put(p,s):
    j=api("GET",p)
    d={"message":"hi","content":base64.b64encode(s.encode()).decode()}
    if "sha" in j: d["sha"]=j["sha"]
    return api("PUT",p,d)
ADB="/home/runner/android-sdk/platform-tools/adb"
os.system(ADB+" exec-out screencap -p > /tmp/hi.png")
im=Image.open("/tmp/hi.png").convert("RGB")
w,h=im.size
if w>1280: im=im.resize((1280,int(h*1280/w)))
b=io.BytesIO(); im.save(b,"JPEG",quality=72)
data=base64.b64encode(b.getvalue()).decode()
CH=250000
n=(len(data)+CH-1)//CH
for i in range(n):
    put("relay/hi_%d.b64"%i, data[i*CH:(i+1)*CH])
put("relay/hi_meta.json", json.dumps({"chunks":n,"size":str(im.size)}))
print("OK chunks=%d size=%s"%(n,im.size))
