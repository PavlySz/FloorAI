"""Smoke-test Gemini image generation: does the key actually have generation quota?"""
import base64, json, os, sys, time, urllib.request

KEY = os.environ["GOOGLE_API_KEY"]
PROMPT = ("Photorealistic interior photo of a small empty Scandinavian living room, "
          "light oak floor, white walls, large window, natural daylight, wide angle.")

def gen(model):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={KEY}")
    body = json.dumps({"contents": [{"parts": [{"text": PROMPT}]}]}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:300]
        return f"HTTP {e.code}: {msg}", None
    dt = time.time() - t0
    for part in data["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            raw = base64.b64decode(part["inlineData"]["data"])
            fn = f"smoke_{model.replace('.','_')}.png"
            open(fn, "wb").write(raw)
            return f"OK {dt:.1f}s  {len(raw)/1024:.0f} KB -> {fn}", fn
    return f"no image in response ({dt:.1f}s)", None

for m in ["gemini-2.5-flash-image", "gemini-3-pro-image"]:
    status, _ = gen(m)
    print(f"{m:26s} {status}")
