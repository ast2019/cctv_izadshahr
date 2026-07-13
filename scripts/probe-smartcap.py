#!/usr/bin/env python3
import base64, urllib.request, re, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
AUTH = base64.b64encode(b"admin:admin123").decode()

IPS = ["192.168.51.4","192.168.51.5","192.168.51.6","192.168.51.9","192.168.51.13","192.168.51.41","192.168.51.30","192.168.51.84"]

def get(ip, path):
    req = urllib.request.Request(f"http://{ip}{path}", headers={"Authorization": f"Basic {AUTH}"})
    with urllib.request.urlopen(req, timeout=4) as r:
        return r.read().decode("utf-8", errors="ignore")

keys = [
    "isSupportFaceDetect","isSupportIntelliTrace","isSupportFieldDetection",
    "isSupportLineDetection","isSupportRegionEntrance","isSupportRegionExiting",
    "isSupportLoitering","isSupportGroup","isSupportRapidMove","isSupportParking",
    "isSupportUnattendedBaggage","isSupportAttendedBaggage","isSupportPersonDensityDetection",
    "isSupportHeatMap","isSupportPeopleCounting","isSupportCounting","isSupportANPR",
    "isSupportIntersectionAnalysis","isSupportRoadDetection","isSupportFaceSnap",
    "isSupportAudioDetection","isSupportDefocus","isSupportSceneChangeDetection",
    "isSupportROI","isSupportVMD","isSupportMotion",
]

for ip in IPS:
    try:
        info = get(ip, "/ISAPI/System/deviceInfo")
        model = re.search(r"<model>(.*?)</model>", info)
        fw = re.search(r"<firmwareVersion>(.*?)</firmwareVersion>", info)
        smart = get(ip, "/ISAPI/Smart/capabilities")
        yes = []
        no = []
        for k in keys:
            m = re.search(rf"<{k}>(true|false)</{k}>", smart, re.I)
            if m:
                (yes if m.group(1).lower()=="true" else no).append(k.replace("isSupport",""))
        # also dump any *true* tags we might have missed
        extra = re.findall(r"<isSupport(\w+)>true</isSupport\1>", smart, re.I)
        for e in extra:
            if e not in yes and f"isSupport{e}" not in [f"isSupport{x}" for x in yes]:
                if e not in yes:
                    yes.append(e)
        print(f"{ip} model={model.group(1) if model else '?'} fw={fw.group(1) if fw else '?'}")
        print(f"  YES: {', '.join(yes) if yes else '(none)'}")
        print(f"  NO : {', '.join(no[:12])}...")
    except Exception as e:
        print(f"{ip} FAIL {e}")
