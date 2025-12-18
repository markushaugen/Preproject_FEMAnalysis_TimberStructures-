# ec5/materials.py
import csv
import pathlib
from typing import Dict, Tuple, List

from .design_values import OrthoElastic, TimberStrength


# Fallback materials used if CSV is missing or incomplete
MATERIALS_FALLBACK: Dict[str, Dict[str, object]] = {
    "C24": {
        "elastic": OrthoElastic(
            EX=11_000e6, EY=370e6, EZ=370e6,
            PRXY=0.35, PRYZ=0.35, PRXZ=0.35,
            GXY=690e6, GYZ=550e6, GXZ=550e6,
        ),
        "strength": TimberStrength(
            fc0k=21e6, ft0k=14e6, ft90k=0.4e6,
            fc90k=2.5e6, fmk=24e6, frk=4.0e6,
        ),
    }
}


def _from_row(r: Dict[str, str]) -> Tuple[OrthoElastic, TimberStrength]:
    elastic = OrthoElastic(
        EX=float(r["E0mean"]),
        EY=float(r["E90mean"]),
        EZ=float(r["E90mean"]),
        PRXY=float(r["nu"]),
        PRYZ=float(r["nu"]),
        PRXZ=float(r["nu"]),
        GXY=float(r["Gmean"]),
        GYZ=float(r["Gmean"]) * 0.8,
        GXZ=float(r["Gmean"]) * 0.8,
    )
    strength = TimberStrength(
        fc0k=float(r["fc0k"]),
        ft0k=float(r["ft0k"]),
        ft90k=float(r["ft90k"]),
        fc90k=float(r["fc90k"]),
        fmk=float(r["fmk"]),
        frk=float(r["frk"]),
    )
    return elastic, strength


def load_catalog(csv_path: str = "data/timber_classes.csv") -> Dict[str, Tuple[OrthoElastic, TimberStrength]]:
    db: Dict[str, Tuple[OrthoElastic, TimberStrength]] = {}

    path = pathlib.Path(csv_path)
    if not path.is_absolute():
        base = pathlib.Path(__file__).resolve().parents[1]
        path = base / path

    if path.exists():
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                db[r["class"]] = _from_row(r)

    for name, v in MATERIALS_FALLBACK.items():
        db.setdefault(name, (v["elastic"], v["strength"]))

    return db


_CATALOG: Dict[str, Tuple[OrthoElastic, TimberStrength]] = load_catalog()


def list_classes() -> List[str]:
    return sorted(_CATALOG.keys())


def get_timber(class_name: str) -> Tuple[OrthoElastic, TimberStrength]:
    try:
        return _CATALOG[class_name]
    except KeyError:
        raise ValueError(f"Unknown class '{class_name}'. Options: {', '.join(list_classes())}")
