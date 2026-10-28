# ============================================================
# GRASS LITE NODE - RENDER FREE (Docker, headless, khong VNC)
# Luồng: extension tu Web Store (CRX) -> Chrome --headless=new
#   + --load-extension -> nap cookie (+localStorage) tu Drive
#   -> mo app.grass.io -> vong lap giu phien song.
# Flask /health + self-ping: chong Render free sleep (15 phut).
# ============================================================
import io
import json
import os
import re
import shutil
import struct
import subprocess
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import urllib.request

# ---------- 0) CONFIG (env override duoc) ----------
GRASS_URL = os.environ.get("GRASS_URL", "https://app.grass.io")
COOKIES_URL = os.environ.get("COOKIES_URL", "")   # link Drive/GitHub/Pastebin file cookie JSON
STORAGE_URL = os.environ.get("STORAGE_URL", "")   # (tuy chon) link file localStorage JSON
EXT_ID = os.environ.get("EXT_ID", "ilehaonighjijnmpnagapkhpcdbhclfg")  # Grass Lite Node
CHROME_MILESTONE = os.environ.get("CHROME_MILESTONE", "131")
BASE = os.environ.get("BASE_DIR", "/app/data")
DATA_DIR = os.path.join(BASE, "data")
PROFILE_DIR = os.path.join(BASE, "profile")
EXT_DIR = os.path.join(BASE, "grass_ext")
PORT = int(os.environ.get("PORT", "10000"))
SLEEP_SECONDS = int(os.environ.get("SLEEP_SECONDS", "300"))  # chu ky refresh trang
PING_SECONDS = int(os.environ.get("PING_SECONDS", "600"))    # chu ky self-ping
RUN_MODE = os.environ.get("RUN_MODE", "1") == "1"

os.makedirs(DATA_DIR, exist_ok=True)
COOKIES_FILE = os.path.join(DATA_DIR, "cookies.json")
STORAGE_FILE = os.path.join(DATA_DIR, "localStorage.json")

# ---------- 1) HEALTH SERVER (Render health check + pinger) ----------
STATE = {"status": "starting", "detail": "boot", "loops": 0, "page_state": "-", "started": time.time()}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/"):
            body = json.dumps(STATE).encode()
            code = 200 if STATE["status"] in ("starting", "running") else 503
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


def start_health_server():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"[health] listening :{PORT}")


def self_ping():
    """Ping chinh minh qua URL public cua Render -> giu service khong bi sleep."""
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        print("[ping] khong co RENDER_EXTERNAL_URL (build local?) -> bo qua self-ping")
        return
    while True:
        time.sleep(PING_SECONDS)
        try:
            urllib.request.urlopen(url.rstrip("/") + "/health", timeout=15)
            print("[ping] OK", url)
        except Exception as e:
            print("[ping] loi:", e)


# ---------- 2) NETWORK HELPERS ----------
def _direct_url(u):
    u = u.strip()
    m = re.search(r"drive\.google\.com/file/d/([\w-]+)", u) or re.search(r"drive\.google\.com/.*[?&]id=([\w-]+)", u)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    if "dropbox.com" in u:
        u = re.sub(r"[?&]dl=0", "", u)
        return u + ("&" if "?" in u else "?") + "dl=1"
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/(.+)", u)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    m = re.match(r"https://pastebin\.com/(?!raw/)(\w+)$", u)
    if m:
        return f"https://pastebin.com/raw/{m.group(1)}"
    return u


def download_json(url, dest):
    req = urllib.request.Request(_direct_url(url), headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=90).read()
    txt = data.decode("utf-8", "ignore").lstrip()
    if txt[:1] not in ("[", "{"):
        raise RuntimeError("noi dung khong phai JSON (link can dang nhap/quyen truy cap?)")
    json.loads(txt)
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def download_session_files():
    for label, url, dest in (("cookie", COOKIES_URL, COOKIES_FILE), ("localStorage", STORAGE_URL, STORAGE_FILE)):
        if not url:
            continue
        ok = False
        for attempt in range(3):
            try:
                n = download_json(url, dest)
                print(f"[dl] {label}: {n} bytes -> {dest}")
                ok = True
                break
            except Exception as e:
                print(f"[dl] {label} lan {attempt + 1} loi: {e}")
                time.sleep(5)
        if not ok:
            print(f"[dl] CANH BAO: khong tai duoc file {label}")


# ---------- 3) EXTENSION ----------
def fetch_extension(ext_id=EXT_ID, dest=EXT_DIR):
    if os.path.exists(os.path.join(dest, "manifest.json")):
        print("[ext] extension da co san:", dest)
        return dest
    url = ("https://clients2.google.com/service/update2/crx?response=redirect"
           f"&prodversion={CHROME_MILESTONE}.0.0.0&acceptformat=crx2,crx3"
           f"&x=id%3D{ext_id}%26uc")
    print("[ext] tai CRX tu Web Store ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=90).read()
    if data[:4] != b"Cr24":
        raise RuntimeError("file khong phai CRX")
    ver = struct.unpack("<I", data[4:8])[0]
    if ver == 3:
        start = 12 + struct.unpack("<I", data[8:12])[0]
    elif ver == 2:
        pk, sg = struct.unpack("<II", data[8:16])
        start = 16 + pk + sg
    else:
        raise RuntimeError(f"CRX version la: {ver}")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data[start:])) as z:
        z.extractall(dest)
    m = json.load(open(os.path.join(dest, "manifest.json"), encoding="utf-8"))
    print(f"[ext] OK: {m.get('name')} v{m.get('version')}")
    return dest



# ---------- 4) CHROME / SELENIUM ----------
# Uu tien env (SnapDeploy chay ARM64 -> chromium tu apt la dung arch),
# roi fallback sang Chrome for Testing trong /opt.
CHROME_BIN = os.environ.get("CHROME_BIN")
DRIVER_BIN = os.environ.get("DRIVER_BIN")
if not CHROME_BIN or not DRIVER_BIN:
    for _root, _dirs, _files in os.walk("/opt/chrome-for-testing"):
        for _f in _files:
            p = os.path.join(_root, _f)
            if _f == "chrome" and os.access(p, os.X_OK):
                CHROME_BIN = p
            if _f == "chromedriver" and os.access(p, os.X_OK):
                DRIVER_BIN = p
if not CHROME_BIN:
    CHROME_BIN = "/usr/bin/chromium" if os.path.exists("/usr/bin/chromium") else None
if not DRIVER_BIN:
    DRIVER_BIN = "/usr/bin/chromedriver" if os.path.exists("/usr/bin/chromedriver") else None
print(f"[chrome] bin={CHROME_BIN} driver={DRIVER_BIN}")

from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.service import Service  # noqa: E402
from selenium.webdriver.chrome.options import Options  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.common.exceptions import TimeoutException, NoSuchElementException  # noqa: E402

_SS = {"strict": "Strict", "lax": "Lax", "none": "None", "no_restriction": "None"}


def _norm_cookie(c):
    o = {"name": c["name"], "value": c["value"], "path": c.get("path", "/"),
         "secure": bool(c.get("secure", False)), "httpOnly": bool(c.get("httpOnly", False))}
    if c.get("domain"):
        o["domain"] = c["domain"]
    else:
        o["url"] = GRASS_URL
    exp = c.get("expiry", c.get("expirationDate"))
    if exp and not c.get("session"):
        o["expires"] = float(exp)
    ss = _SS.get(str(c.get("sameSite", "")).lower())
    if ss:
        o["sameSite"] = ss
        if ss == "None":
            o["secure"] = True
    return o


def _profile_dir():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    import glob
    for f in glob.glob(os.path.join(PROFILE_DIR, "Singleton*")):
        try:
            os.remove(f)
        except Exception:
            pass
    return PROFILE_DIR


def create_driver():
    subprocess.run("pkill -9 -f chromedriver; pkill -9 -f chrome", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    o = Options()
    o.add_argument("--headless=new")  # new headless van chay duoc extension
    for a in ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--use-gl=swiftshader",
              "--window-size=1024,700", "--disable-blink-features=AutomationControlled",
              "--no-first-run", "--no-default-browser-check", "--disable-plugins",
              "--mute-audio", f"--user-data-dir={_profile_dir()}",
              # hanh trang cho may 512MB: giam so process renderer, chan OOM kill tab
              "--renderer-process-limit=1", "--process-per-site",
              "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
              "--disable-hang-monitor", "--disable-features=Translate",
              "--disable-background-networking", "--disable-component-update",
              "--disable-sync", "--metrics-recording-only"]:
        o.add_argument(a)
    if os.path.isdir(EXT_DIR):
        o.add_argument(f"--disable-extensions-except={EXT_DIR}")
        o.add_argument(f"--load-extension={EXT_DIR}")
        o.add_argument("--disable-features=DisableLoadExtensionCommandLineSwitch")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    o.add_experimental_option("useAutomationExtension", False)
    if CHROME_BIN:
        o.binary_location = CHROME_BIN
    svc = Service(DRIVER_BIN, log_output="/tmp/chromedriver.log")
    try:
        return webdriver.Chrome(service=svc, options=o)
    except Exception:
        if os.path.exists("/tmp/chromedriver.log"):
            print("".join(open("/tmp/chromedriver.log").readlines()[-30:]))
        raise


# ---------- 5) LOGIN / STATE ----------
GUEST_MARKERS = ["hello, guest", "sign up to save your progress"]


def page_state(drv):
    html, url = drv.page_source.lower(), drv.current_url.lower()
    caps = ["g-recaptcha", "hcaptcha", "cf-turnstile", "challenge-platform",
            "verify you are human", "just a moment"]
    if any(m in html for m in caps) and "dashboard" not in html:
        return "captcha"
    try:
        body = drv.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        return "loading"
    if any(m in body for m in GUEST_MARKERS):
        return "guest"
    try:
        drv.find_element(By.CSS_SELECTOR, "input[type=email], input[name*=email], input[id*=email]")
        return "login_form"
    except NoSuchElementException:
        pass
    if "dashboard" in body and not any(x in url for x in ("login", "signin", "sign-in")):
        return "logged_in"
    return "loading"


def wait_state(drv, timeout=25):
    end, st = time.time() + timeout, "loading"
    while time.time() < end:
        time.sleep(2)
        st = page_state(drv)
        if st in ("logged_in", "captcha"):
            break
    return st


def inject_local_storage_early(drv):
    if not os.path.exists(STORAGE_FILE):
        return False
    try:
        data = json.load(open(STORAGE_FILE, encoding="utf-8"))
    except Exception as e:
        print("[ls] doc localStorage loi:", e)
        return False
    from urllib.parse import urlparse
    u = urlparse(GRASS_URL)
    origin = f"{u.scheme}://{u.netloc}"
    src = ("(function(){try{if(location.origin!==%s)return;"
           "if(sessionStorage.getItem('__ls_injected')||localStorage.getItem('accessToken'))return;"
           "var d=%s;for(var k in d){localStorage.setItem(k,typeof d[k]==='string'?d[k]:JSON.stringify(d[k]));}"
           "sessionStorage.setItem('__ls_injected','1');}catch(e){}})();") % (json.dumps(origin), json.dumps(data))
    drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": src})
    print(f"[ls] se chen {len(data)} muc localStorage")
    return True


def load_cookies(drv):
    if not os.path.exists(COOKIES_FILE):
        print("[cookie] khong co file cookie!")
        return False
    try:
        raw = json.load(open(COOKIES_FILE, encoding="utf-8"))
    except Exception as e:
        print("[cookie] doc loi:", e)
        return False
    if isinstance(raw, dict):
        raw = raw.get("cookies", [])
    drv.execute_cdp_cmd("Network.enable", {})
    ok = 0
    for c in raw:
        try:
            r = drv.execute_cdp_cmd("Network.setCookie", _norm_cookie(c))
            ok += 1 if r.get("success", True) else 0
        except Exception as e:
            print(f"[cookie] bo qua {c.get('name')}: {e}")
    print(f"[cookie] nap {ok}/{len(raw)}")
    return ok > 0


def save_session(drv):
    try:
        cs = drv.execute_cdp_cmd("Network.getAllCookies", {})["cookies"]
        json.dump(cs, open(COOKIES_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        data = drv.execute_script("return Object.fromEntries(Object.entries(localStorage));")
        json.dump(data, open(STORAGE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("[session] da luu cookie+localStorage vao", DATA_DIR)
    except Exception as e:
        print("[session] luu loi:", e)


def _ext_popup_url():
    return f"chrome-extension://{EXT_ID}/index.html"


def login(drv):
    drv.execute_cdp_cmd("Network.enable", {})
    load_cookies(drv)
    inject_local_storage_early(drv)
    # 1) Thu mo trang web (de app tu refresh token); SPA nang -> renderer co the OOM
    st = "crash"
    try:
        drv.get(GRASS_URL)
        st = wait_state(drv, 35)
        print("[login] page_state =", st)
        if st == "logged_in":
            save_session(drv)
            STATE["page_state"] = "logged_in"
    except Exception as e:
        print("[login] web tab crash (SPA qua nang voi 512MB):", str(e)[:80])
    # 2) Giai phong RAM: dua tab ve about:blank TRUOC khi mo popup (512MB)
    try:
        drv.get("about:blank")
        time.sleep(2)
    except Exception:
        pass
    # 3) Mo popup cua extension - nhe hon SPA nhieu; service worker chay voi cookie trong profile
    try:
        drv.get(_ext_popup_url())
        time.sleep(6)
        st2 = page_state(drv)
        print("[login] popup extension mo OK, state =", st2, "| url =", drv.current_url[:70])
        if st2 == "login_form":
            print("[login] EXTENSION CHUA DANG NHAP -> cookie het han! Cap nhat COOKIES_URL roi restart.")
            STATE["page_state"] = "ext_not_logged_in"
            return False
        STATE["page_state"] = "ext_popup"
        save_session(drv)
        return True
    except Exception as e:
        print("[login] khong mo duoc popup extension:", str(e)[:120])
        STATE["page_state"] = "ext_popup_fail"
        return False


# ---------- 6) VONG LAP CHINH ----------
driver = None
_lock = threading.Lock()


def node_loop():
    global driver
    try:
        fetch_extension()
    except Exception as e:
        print("[ext] LOI tai extension:", e)
        STATE["status"] = "error"
        STATE["detail"] = f"extension: {e}"
        return
    download_session_files()
    i = 0
    while RUN_MODE:
        i += 1
        STATE["loops"] = i
        print(f"\n===== Vong #{i} @ {time.strftime('%H:%M:%S')} =====")
        try:
            with _lock:
                if driver is None:
                    driver = create_driver()
                    STATE["status"] = "running"
                    STATE["detail"] = "chrome up"
                if not login(driver):
                    print("[loop] login chua thanh cong - tai lai driver moi")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = None
                    time.sleep(10)
                else:
                    time.sleep(5)
                    try:
                        ts = driver.execute_cdp_cmd("Target.getTargets", {})["targetInfos"]
                        ext = [t for t in ts if t.get("url", "").startswith("chrome-extension://")]
                        for t in ext:
                            print("   [ext]", t["type"], t["url"][:90])
                    except Exception:
                        pass
                # moi 6 vong (~30 phut): ghe web 1 lan de app refresh accessToken
                if i % 6 == 0:
                    print("[loop] ghe web refresh token...")
                    try:
                        driver.get(GRASS_URL)
                        st = wait_state(driver, 20)
                        print("[loop] web:", st)
                        if st == "logged_in":
                            save_session(driver)
                    except Exception as e:
                        print("[loop] web crash (bo qua):", str(e)[:60])
                    try:
                        driver.get("about:blank")
                        time.sleep(2)
                        driver.get(_ext_popup_url())
                    except Exception:
                        pass
                # refresh giu phien
                time.sleep(SLEEP_SECONDS)
                try:
                    driver.refresh()
                    time.sleep(3)
                    print("[loop] da refresh trang hien tai")
                except Exception as e:
                    print("[loop] refresh loi, tao lai driver:", e)
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = None
        except Exception as e:
            print("[loop] LOI ngoai le:", e)
            STATE["detail"] = str(e)[:200]
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            driver = None
            time.sleep(30)


def main():
    start_health_server()
    threading.Thread(target=self_ping, daemon=True).start()
    threading.Thread(target=node_loop, daemon=True).start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
