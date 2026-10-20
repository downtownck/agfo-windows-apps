"""AGFO TTS Service sözlük testleri (EMA modeli yerine sahte model). Çalıştırma: python3 tests/test_server.py
Gerekenler: fastapi httpx soundfile numpy"""
import os, sys, json, tempfile, shutil, importlib, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "stub"))
shutil.copy(os.path.join(ROOT, "server.py"), tmp); shutil.copy(os.path.join(ROOT, "lexicon.json"), tmp)
sys.path.insert(0, tmp)
os.environ.update(AGFO_TTS_TOKEN="t", AGFO_TTS_CACHE_DIR=os.path.join(tmp, "cache"))
import server
from fastapi.testclient import TestClient
import ema_lightning
c = TestClient(server.app); H = {"X-AGFO-Token": "t"}
ok = fail = 0
def chk(n, cond, x=""):
    global ok, fail
    print(("PASS " if cond else "FAIL ") + n + ("" if cond else "  " + str(x)[:300])); ok += bool(cond); fail += (not cond)
r = c.get("/lexicon"); chk("401 without token", c.get("/lexicon").status_code == 401 if False else c.get("/lexicon", headers={"X-AGFO-Token": "x"}).status_code == 401)
d = r.json() if r.status_code == 200 else c.get("/lexicon", headers=H).json()
d = c.get("/lexicon", headers=H).json()
chk("list base", d["base"] > 2000 and d["custom"] == 0 and d["active"] == d["base"])
chk("HACCP hasip shipped", any(e["word"] == "HACCP" and e["reading"] == "hasip" for e in d["entries"]))
r = c.post("/lexicon/entry", headers=H, json={"word": "Kaya Gıda", "reading": "Kaya Gıda"})
chk("add new word", r.status_code == 200, r.text)
r = c.post("/lexicon/entry", headers=H, json={"word": "O'Connor", "reading": "O'Konır"}); chk("add O'Connor", r.status_code == 200)
r = c.post("/lexicon/entry", headers=H, json={"word": "HACCP", "reading": "haçep"}); chk("edit shipped", r.status_code == 200)
chk("custom file written", json.load(open(os.path.join(tmp, "data", "lexicon.custom.json"), encoding="utf-8")).get("HACCP") == "haçep")
a = c.post("/lexicon/apply", headers=H, json={"text": "HACCP ve O'Connor, Chicago'da."}).json()["text"]
chk("apply uses edits immediately", a == "haçep ve O'Konır, Şikago'da.", a)
r = c.post("/lexicon/delete", headers=H, json={"word": "Chicago"}); chk("delete shipped -> masked", r.status_code == 200)
a = c.post("/lexicon/apply", headers=H, json={"text": "Chicago"}).json()["text"]; chk("masked word not replaced", a == "Chicago", a)
rows = {e["word"]: e for e in c.get("/lexicon", headers=H).json()["entries"]}
chk("sources", rows["Chicago"]["source"] == "removed" and rows["HACCP"]["source"] == "edited" and rows["O'Connor"]["source"] == "added" and rows["BRCGS"]["source"] == "base", {k: rows[k]["source"] for k in ["Chicago","HACCP","O'Connor","BRCGS"]})
c.post("/lexicon/delete", headers=H, json={"word": "Chicago", "reading": "__restore__"})
chk("restore", c.post("/lexicon/apply", headers=H, json={"text": "Chicago"}).json()["text"] == "Şikago")
c.post("/lexicon/entry", headers=H, json={"word": "HACCP", "reading": "hasip"})
chk("setting shipped reading drops override", "HACCP" not in json.load(open(os.path.join(tmp, "data", "lexicon.custom.json"), encoding="utf-8")))
r = c.post("/lexicon/delete", headers=H, json={"word": "O'Connor"}); chk("delete added", r.status_code == 200 and "O'Connor" not in json.load(open(os.path.join(tmp,"data","lexicon.custom.json"),encoding="utf-8")))
chk("delete unknown 404", c.post("/lexicon/delete", headers=H, json={"word": "Yokkelime"}).status_code == 404)
chk("empty reading 400", c.post("/lexicon/entry", headers=H, json={"word": "X1", "reading": "  "}).status_code == 400)
r = c.post("/lexicon/entry", headers=H, json={"word": "a\nb", "reading": "c"}); chk("newline in word normalised to space", r.status_code == 200 and r.json()["word"] == "a b", r.text); c.post("/lexicon/delete", headers=H, json={"word": "a b"})
# shipped update keeps custom edits
c.post("/lexicon/entry", headers=H, json={"word": "Gugenheim", "reading": "Gugınhaym"})
time.sleep(0.01); open(os.path.join(tmp, "lexicon.json"), "w", encoding="utf-8").write(json.dumps({"BRCGS": "bi ar si ci es"}))
os.utime(os.path.join(tmp, "lexicon.json"), (time.time()+5, time.time()+5))
a = c.post("/lexicon/apply", headers=H, json={"text": "BRCGS Gugenheim Chicago"}).json()["text"]
chk("lexicon.json replaced: custom kept, base reloaded", a == "bi ar si ci es Gugınhaym Chicago", a)
# tts cache invalidates on lexicon edit
ema_lightning.SAID.clear()
c.post("/tts", headers=H, json={"text": "Gugenheim."})
c.post("/lexicon/entry", headers=H, json={"word": "Gugenheim", "reading": "Guggenhaym"})
r = c.post("/tts", headers=H, json={"text": "Gugenheim."})
chk("tts not served stale after edit", r.headers.get("X-AGFO-Cached") == "0" and ema_lightning.SAID[-1].startswith("Guggenhaym"), ema_lightning.SAID)
r = c.post("/tts", headers=H, json={"text": "Gugenheim.", "apply_lexicon": False}); chk("apply_lexicon false honoured", ema_lightning.SAID[-1].startswith("Gugenheim"))
print("TOTAL", ok, "pass /", fail, "fail")
