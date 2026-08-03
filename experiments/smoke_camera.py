"""Force real camera movement while keeping object identity locked.

Key idea: don't say "move the camera". Describe the TARGET FRAME explicitly --
where the camera stands, what it faces, what is behind it (not visible), and
where each visible object sits in the frame.
"""
import base64, json, os, sys, time, urllib.request

KEY = os.environ["GOOGLE_API_KEY"]
MODEL = "gemini-3-pro-image"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"

INVENTORY = (
    "Object inventory (identity is fixed, must not change):\n"
    "- grey 3-seat fabric sofa with 3 cushions, dark wood legs\n"
    "- round white marble coffee table, thin black cross legs\n"
    "- mustard-yellow velvet armchair, black splayed legs\n"
    "- tall black metal open bookshelf with books, vases, a glass dome\n"
    "- large beige woven jute rug\n"
    "- fiddle-leaf fig in a terracotta pot\n"
    "- black cylindrical pendant lamp on a long cord\n"
    "- two abstract framed prints in thin black frames\n"
    "- white radiator under the window, sheer white curtains\n"
    "Room: light oak herringbone floor, white walls, one large window.\n"
)

# Each view states camera position, facing, what is BEHIND the camera, and framing.
VIEWS = {
    "A_from_window": (
        "CAMERA POSITION: standing directly in front of the window, at the window, "
        "looking SOUTH into the room, away from the window.\n"
        "BEHIND THE CAMERA (must NOT appear): the window, the curtains, the radiator.\n"
        "FRAMING: the back of the grey sofa is on the LEFT of frame seen from behind and "
        "side-on. The black bookshelf is on the RIGHT of frame. The jute rug and marble "
        "coffee table fill the lower centre. The far wall with the two framed prints is "
        "visible in the background. The pendant lamp hangs into the top of frame. "
        "The fiddle-leaf fig is at the far left edge."
    ),
    "B_corner_behind_shelf": (
        "CAMERA POSITION: standing in the far corner beside the black bookshelf, "
        "looking WEST across the room toward the sofa wall.\n"
        "BEHIND THE CAMERA (must NOT appear): the bookshelf.\n"
        "FRAMING: the grey sofa is seen head-on across the room, centred, with the two "
        "framed prints on the wall directly above it. The fiddle-leaf fig is to the right "
        "of the sofa. The mustard armchair is in the near foreground on the right, seen "
        "from behind. The coffee table and jute rug are in the centre of the floor. "
        "The window is at the right edge of frame."
    ),
    "C_low_detail": (
        "CAMERA POSITION: low, close to the coffee table, about 60cm above the floor, "
        "looking WEST toward the sofa.\n"
        "FRAMING: tight three-quarter detail shot. The marble coffee table fills the "
        "foreground with the small glass vase on it. The grey sofa and its cushions fill "
        "the middle of frame behind the table. The jute rug texture is prominent in the "
        "lower frame. Shallow depth of field, background softly blurred."
    ),
}

def call(parts, tag):
    body = json.dumps({"contents": [{"parts": parts}]}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    for p in data["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            raw = base64.b64decode(p["inlineData"]["data"])
            fn = f"cam_{tag}.png"
            open(fn, "wb").write(raw)
            print(f"  {tag:22s} OK {time.time()-t0:5.1f}s -> {fn}")
            return raw
    print(f"  {tag:22s} NO IMAGE")
    return None

canon = open("consist_canonical.png", "rb").read()
b64 = base64.b64encode(canon).decode()

for tag, view in VIEWS.items():
    call([
        {"inlineData": {"mimeType": "image/png", "data": b64}},
        {"text": (
            "The attached photograph shows a room you must re-photograph from a NEW "
            "camera position. It is a reference for OBJECT IDENTITY ONLY, not for "
            "composition. Do NOT reproduce its framing.\n\n"
            + INVENTORY +
            "\nEvery object keeps its exact identity, colour, material and place in the "
            "room. Nothing is added, removed, resized or re-coloured. The architecture is "
            "unchanged. What changes is ONLY where the photographer stands.\n\n"
            + view +
            "\n\nProduce a photorealistic architectural interior photograph from this new "
            "camera position. It must look like a genuinely different photo of the same room."
        )},
    ], tag)
