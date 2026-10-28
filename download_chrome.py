"""Tải Chrome for Testing (ghim milestone 131 - hỗ trợ --load-extension) lúc BUILD."""
import json, os, struct, sys, urllib.request, zipfile

CFT_DIR = "/opt/chrome-for-testing"
MILESTONE = os.environ.get("CHROME_MILESTONE", "131")


def main():
    url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read().decode())
    cands = [v for v in data["versions"] if v["version"].split(".")[0] == MILESTONE]
    if not cands:
        sys.exit(f"Khong co milestone {MILESTONE}")
    e = cands[-1]
    ver = e["version"]

    def find(comp):
        for d in e["downloads"].get(comp, []):
            if d["platform"] == "linux64":
                return d["url"]

    vd = os.path.join(CFT_DIR, ver)
    cb = os.path.join(vd, "chrome-linux64", "chrome")
    db = os.path.join(vd, "chromedriver-linux64", "chromedriver")
    if os.path.exists(cb) and os.path.exists(db):
        print("Chrome for Testing da co san:", ver)
    else:
        os.makedirs(vd, exist_ok=True)
        print("Tai Chrome for Testing", ver)
        for comp in ("chrome", "chromedriver"):
            z = os.path.join(vd, comp + ".zip")
            urllib.request.urlretrieve(find(comp), z)
            with zipfile.ZipFile(z) as zf:
                zf.extractall(vd)
            os.remove(z)
    for dp, _, fns in os.walk(CFT_DIR):
        for fn in fns:
            try:
                os.chmod(os.path.join(dp, fn), 0o755)
            except Exception:
                pass
    print("CHROME_BIN=" + cb)
    print("DRIVER_BIN=" + db)


if __name__ == "__main__":
    main()
