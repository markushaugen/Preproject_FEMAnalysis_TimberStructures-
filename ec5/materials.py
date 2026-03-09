# ec5/materials.py
import csv
import pathlib
from typing import Dict, Tuple, List

from .design_values import OrthoElastic, TimberStrength


# Fallback materials used if CSV is missing or incomplete
MATERIALS_FALLBACK: Dict[str, Dict[str, object]] = {
    "C24": {
        "elastic": OrthoElastic(
            EX=11000, EY=370, EZ=370,
            PRXY=0.35, PRYZ=0.35, PRXZ=0.35,
            GXY=690, GYZ=550, GXZ=550,
        ),
        "strength": TimberStrength(
            fc0k=21, ft0k=14, ft90k=0.4,
            fc90k=2.5, fmk=24, frk=4.0,
        ),
    }
}


def _from_row(r: Dict[str, str]) -> Tuple[OrthoElastic, TimberStrength]:
    # Convert from Pa (N/m^2) to N/mm^2 (MPa) for mm-N unit system
    PA_TO_MPA = 1e-6

    elastic = OrthoElastic(
        EX=float(r["E0mean"]) * PA_TO_MPA,
        EY=float(r["E90mean"]) * PA_TO_MPA,
        EZ=float(r["E90mean"]) * PA_TO_MPA,
        PRXY=float(r["nu"]),
        PRYZ=float(r["nu"]),
        PRXZ=float(r["nu"]),
        GXY=float(r["Gmean"]) * PA_TO_MPA,
        GYZ=float(r["Gmean"]) * 0.8 * PA_TO_MPA,
        GXZ=float(r["Gmean"]) * 0.8 * PA_TO_MPA,
    )

    strength = TimberStrength(
        fc0k=float(r["fc0k"]) * PA_TO_MPA,
        ft0k=float(r["ft0k"]) * PA_TO_MPA,
        ft90k=float(r["ft90k"]) * PA_TO_MPA,
        fc90k=float(r["fc90k"]) * PA_TO_MPA,
        fmk=float(r["fmk"]) * PA_TO_MPA,
        frk=float(r["frk"]) * PA_TO_MPA,
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
            print("CSV fieldnames:", reader.fieldnames)

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
