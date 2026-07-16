#!/usr/bin/env python3
"""cubicasa_runner — optional high-accuracy floorplan model backend for `import pdf`.

This is ORIGINAL code that drives the CubiCasa5k model, which it does NOT ship. CubiCasa5k
is CC BY-NC 4.0 (non-commercial) — you must supply it yourself:

    git clone https://github.com/CubiCasa/CubiCasa5k
    # download model_best_val_loss_var.pkl into that checkout (see its README)
    python -m venv .venv-cc && .venv-cc/bin/pip install torch torchvision numpy pillow \
        scikit-image scipy lmdb svgpathtools

Then point pdf_import's model backend at it, e.g.:

    export CUBICASA_HOME=/path/to/CubiCasa5k
    sweethome3d import pdf plan.pdf --plan "Ground Floor - Proposed" -o out.sh3d \
        --backend model \
        --model-cmd "/path/CubiCasa5k/.venv-cc/bin/python -m cli_anything.sweethome3d.tools.cubicasa_runner {in} {out}"

It reads a floorplan PNG and writes a polygons JSON:
    {"w","h","walls":[{"points","class"}],"openings":[{"points","class"}],"rooms":[{"points","name"}]}
class: openings 1=window 2=door. NB: loads the model's .pkl (a pickle) — only run weights you trust.
"""
import os, sys, json, re


def _sanitise_path(p, name):
    """Validate a filesystem path received from argv/env before use.

    The runner is invoked as a subprocess by ``pdf_import.run_model`` with
    ``{in}``/``{out}`` placeholders substituted from user-supplied paths.
    Although the caller uses ``shell=False`` (list argv), we defensively
    reject null bytes (which truncate C strings and can fool argument
    parsing) and shell metacharacters so that a future refactor that
    accidentally enables ``shell=True`` cannot turn a filename into a
    command-injection vector.
    """
    if not isinstance(p, str) or not p:
        raise ValueError(f"{name} must be a non-empty string")
    if "\x00" in p:
        raise ValueError(f"{name} contains a null byte")
    if any(ch in p for ch in "\n\r\t"):
        raise ValueError(f"{name} contains a control character")
    if re.search(r"[|;&`$()<>]", p):
        raise ValueError(f"{name} contains a shell metacharacter")
    return p


def main(inp, out):
    inp = _sanitise_path(inp, "input path")
    out = _sanitise_path(out, "output path")
    home = os.environ.get("CUBICASA_HOME")
    if not home or not os.path.isdir(home):
        sys.exit("set $CUBICASA_HOME to your CubiCasa5k checkout")
    os.chdir(home)          # the model's init loads a backbone via a relative path
    sys.path.insert(0, home)

    import numpy as np
    import torch, torch.nn.functional as F
    from PIL import Image
    # CubiCasa post-processing predates scipy's mode(keepdims) change
    import scipy.stats as _ss
    _o = _ss.mode
    _ss.mode = lambda *a, **k: _o(*a, **{**k, "keepdims": True})
    from floortrans.models import get_model
    from floortrans.post_prosessing import split_prediction, get_polygons
    from floortrans.loaders.augmentations import RotateNTurns

    weights = _sanitise_path(os.environ.get("CUBICASA_WEIGHTS", os.path.join(home, "model_best_val_loss_var.pkl")), "CUBICASA_WEIGHTS")
    model = get_model("hg_furukawa_original", 51)
    model.conv4_ = torch.nn.Conv2d(256, 44, bias=True, kernel_size=1)
    model.upsample = torch.nn.ConvTranspose2d(44, 44, kernel_size=4, stride=4)
    model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=False)["model_state"])
    model.eval()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(dev)
    rot = RotateNTurns()

    arr = np.asarray(Image.open(inp).convert("RGB"), dtype=np.float32) / 255.0 * 2 - 1
    H, W = arr.shape[0], arr.shape[1]
    t = torch.from_numpy(np.moveaxis(arr, -1, 0)).unsqueeze(0).to(dev)
    pred = torch.zeros([4, 44, H, W])
    with torch.no_grad():
        for i, (f, b) in enumerate([(0, 0), (1, -1), (2, 2), (-1, 1)]):
            p = model(rot(t, "tensor", f))
            p = rot(p, "tensor", b)
            p = rot(p, "points", b)
            pred[i] = F.interpolate(p, size=(H, W), mode="bilinear", align_corners=True)[0].cpu()
    pred = torch.mean(pred, 0, True)
    heatmaps, rooms, icons = split_prediction(pred, (H, W), [21, 12, 11])
    thr = float(os.environ.get("CUBICASA_THRESHOLD", "0.2"))
    polygons, types, room_polygons, room_types = get_polygons((heatmaps, rooms, icons), thr, [1, 2])

    ROOM = ["Background", "Outdoor", "Wall", "Kitchen", "Living Room", "Bed Room", "Bath",
            "Entry", "Railing", "Storage", "Garage", "Undefined"]
    walls, openings = [], []
    for poly, ty in zip(polygons, types):
        pts = [[float(p[0]), float(p[1])] for p in np.array(poly).reshape(-1, 2)]
        (walls if ty["type"] == "wall" else openings).append(
            {"points": pts, "class": int(ty["class"])})
    rooms_out = []
    for poly, rt in zip(room_polygons, room_types):
        pts = None
        try:
            geom = max(poly.geoms, key=lambda g: g.area) if hasattr(poly, "geoms") else poly
            if hasattr(geom, "exterior"):
                pts = [[float(x), float(y)] for x, y in geom.exterior.coords]
        except Exception:
            pts = None
        if not pts or len(pts) < 3:
            continue
        cls = int(rt["class"]) if isinstance(rt, dict) else int(rt)
        rooms_out.append({"points": pts, "name": ROOM[cls] if 0 <= cls < len(ROOM) else None})
    json.dump({"w": W, "h": H, "walls": walls, "openings": openings, "rooms": rooms_out}, open(out, "w"))
    print(f"{os.path.basename(out)}: walls={len(walls)} openings={len(openings)} rooms={len(rooms_out)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: cubicasa_runner.py INPUT.png OUT.json")
    main(sys.argv[1], sys.argv[2])
