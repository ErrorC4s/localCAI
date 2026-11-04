"""After `pip install localcai` in a clean environment: the bundled extension is there and
"Set up the extension" prepares Chrome/Edge and Firefox folders (run from outside the source tree)."""
import json, os, sys, tempfile, threading, urllib.request
from pathlib import Path
os.environ["LOCALCAI_HOME"] = tempfile.mkdtemp(prefix="lcai-pip-")
import localcai
from localcai.webui.server import create_server, extension_source
assert "site-packages" in localcai.__file__, localcai.__file__
src = extension_source()
assert src and (src / "manifest.json").exists() and (src / "src" / "bridge.js").exists(), src
httpd = create_server(8823)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
for browser, keeps_ff in (("chromium", False), ("firefox", True)):
    req = urllib.request.Request("http://127.0.0.1:8823/api/extractor/setup", data=json.dumps({"browser": browser}).encode(),
                                 headers={"Content-Type": "application/json", "X-LocalCAI": "1", "Host": "127.0.0.1:8823"})
    r = json.load(urllib.request.urlopen(req))
    m = json.loads(Path(r["manifest"]).read_text())
    assert ("browser_specific_settings" in m) == keeps_ff and Path(r["path"], "popup", "popup.html").exists(), r
    print(browser, "ok:", r["path"])
httpd.shutdown()
print("PIP INSTALL EXTRACTOR PASS")
