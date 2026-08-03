"""Does reference-conditioning hold the scene when only the camera moves?

Renders a furnished canonical view, then two alternate viewpoints that each get
the SAME scene description plus the canonical image as reference.
"""
import base64, json, os, time, urllib.request

KEY = os.environ["GOOGLE_API_KEY"]
MODEL = "gemini-3-pro-image"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"

SCENE = (
    "A 25 square meter Scandinavian living room. "
    "Light oak herringbone floor. White walls. One large window on the north wall with "
    "sheer white curtains. "
    "FURNITURE, fixed positions: a grey 3-seat fabric sofa against the west wall facing east; "
    "a round white marble coffee table with black legs centred in front of the sofa; "
    "a mustard-yellow armchair in the north-east corner angled toward the coffee table; "
    "a tall black metal bookshelf against the east wall; "
    "a large beige jute rug under the coffee table; "
    "a fiddle-leaf fig plant in a terracotta pot in the south-west corner; "
    "a black cylindrical pendant lamp hanging above the coffee table; "
    "two abstract framed prints on the west wall above the sofa."
)

def call(parts, tag):
    body = json.dumps({"contents": [{"parts": parts}]}).encode()
    req = urllib.request.Request(URL, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    for p in data["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            raw = base64.b64decode(p["inlineData"]["data"])
            fn = f"consist_{tag}.png"
            open(fn, "wb").write(raw)
            print(f"  {tag:12s} OK {time.time()-t0:5.1f}s -> {fn}")
            return raw
    print(f"  {tag:12s} NO IMAGE")
    return None

# 1. canonical
canon = call([{"text": SCENE + " Photorealistic interior photograph, wide-angle view from "
                              "the south-east corner showing the sofa and window."}], "canonical")
b64 = base64.b64encode(canon).decode()

# 2/3. alternate viewpoints, each anchored to the canonical image
VIEWS = {
    "view_north": "from the south wall looking north directly at the window",
    "view_west":  "from the east side looking west directly at the sofa wall",
}
for tag, cam in VIEWS.items():
    call([
        {"inlineData": {"mimeType": "image/png", "data": b64}},
        {"text": (
            "The attached photograph is the ground truth for this room.\n" + SCENE +
            "\n\nRe-photograph this EXACT same room from a different camera position: "
            f"{cam}. "
            "Every object must keep its identity, colour, material, size and position. "
            "Do not add, remove, move, rotate or resize anything. "
            "Walls, floor, window and ceiling stay identical. Only the camera moves. "
            "Photorealistic interior photograph."
        )},
    ], tag)
