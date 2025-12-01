# ec5/materials.py
import csv, pathlib
from .design_values import OrthoElastic, TimberStrength

# Fallback (used if CSV not found)
MATERIALS_FALLBACK = {
    "C24": {
        "elastic": OrthoElastic(EX=11_000e6, EY=370e6, EZ=370e6,
                                PRXY=0.35, PRYZ=0.35, PRXZ=0.35,
                                GXY=690e6, GYZ=550e6, GXZ=550e6),
        "strength": TimberStrength(fc0k=21e6, ft0k=14e6, ft90k=0.4e6,
                                   fc90k=2.5e6, fmk=24e6, frk=4.0e6),
    }
}

def _from_row(r):
    elastic = OrthoElastic(
        EX=float(r["E0mean"]), EY=float(r["E90mean"]), EZ=float(r["E90mean"]),
        PRXY=float(r["nu"]), PRYZ=float(r["nu"]), PRXZ=float(r["nu"]),
        GXY=float(r["Gmean"]), GYZ=float(r["Gmean"])*0.8, GXZ=float(r["Gmean"])*0.8
    )
    strength = TimberStrength(
        fc0k=float(r["fc0k"]), ft0k=float(r["ft0k"]), ft90k=float(r["ft90k"]),
        fc90k=float(r["fc90k"]), fmk=float(r["fmk"]), frk=float(r["frk"])
    )
    return elastic, strength

def load_catalog(csv_path: str = "data/timber_classes.csv"):
    path = pathlib.Path(csv_path)
    db = {}
    if path.exists():
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                db[r["class"]] = _from_row(r)
    # fallback merge
    for k,v in MATERIALS_FALLBACK.items():
        db.setdefault(k, (v["elastic"], v["strength"]))
    return db

_CATALOG = load_catalog()

def list_classes():
    return sorted(_CATALOG.keys())

def get_timber(class_name: str):
    try:
        return _CATALOG[class_name]
    except KeyError:
        raise ValueError(f"Unknown class '{class_name}'. Options: {', '.join(list_classes())}")
