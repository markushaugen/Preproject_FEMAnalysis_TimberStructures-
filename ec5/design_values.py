# ec5/design_values.py
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple

# --- EC5 enums ---
class ServiceClass(Enum):
    SC1 = 1
    SC2 = 2
    SC3 = 3

class LoadDuration(Enum):
    PERMANENT = "permanent"
    LONG = "long"
    MEDIUM = "medium"
    SHORT = "short"
    INSTANTANEOUS = "instant"

# EC5 k_mod table (completed for SC1/SC2/SC3) 
K_MOD_TABLE = {
    # Service Class 1
    (ServiceClass.SC1, LoadDuration.PERMANENT): 0.60,
    (ServiceClass.SC1, LoadDuration.LONG)      : 0.70,
    (ServiceClass.SC1, LoadDuration.MEDIUM)    : 0.80,
    (ServiceClass.SC1, LoadDuration.SHORT)     : 0.90,
    (ServiceClass.SC1, LoadDuration.INSTANTANEOUS): 1.10,

    # Service Class 2 (typical)
    (ServiceClass.SC2, LoadDuration.PERMANENT): 0.60,
    (ServiceClass.SC2, LoadDuration.LONG)      : 0.70,
    (ServiceClass.SC2, LoadDuration.MEDIUM)    : 0.80,
    (ServiceClass.SC2, LoadDuration.SHORT)     : 0.90,
    (ServiceClass.SC2, LoadDuration.INSTANTANEOUS): 1.10,

    # Service Class 3 (more conservative)
    (ServiceClass.SC3, LoadDuration.PERMANENT): 0.50,
    (ServiceClass.SC3, LoadDuration.LONG)      : 0.55,
    (ServiceClass.SC3, LoadDuration.MEDIUM)    : 0.65,
    (ServiceClass.SC3, LoadDuration.SHORT)     : 0.70,
    (ServiceClass.SC3, LoadDuration.INSTANTANEOUS): 0.90,

}
GAMMA_M_TIMBER = 1.3
GAMMA_M_CONN = 1.3

# Material properties and design values  
@dataclass
class OrthoElastic:
    EX: float; EY: float; EZ: float
    PRXY: float; PRYZ: float; PRXZ: float
    GXY: float; GYZ: float; GXZ: float

@dataclass
class TimberStrength:
    fc0k: float; ft0k: float; ft90k: float
    fc90k: float; fmk: float; frk: float

@dataclass
class TimberDesign:
    elastic: OrthoElastic
    strength_char: TimberStrength
    service_class: ServiceClass

    def k_mod(self, duration: LoadDuration) -> float:
        return K_MOD_TABLE[(self.service_class, duration)]

    def design_value(self, fk: float, duration: LoadDuration, gamma_m: float = GAMMA_M_TIMBER) -> float:
        return self.k_mod(duration) * fk / gamma_m

    def strengths_design(self, duration: LoadDuration) -> Dict[str, float]:
        s = self.strength_char
        return {
            "fc0d": self.design_value(s.fc0k, duration),
            "ft0d": self.design_value(s.ft0k, duration),
            "ft90d": self.design_value(s.ft90k, duration),
            "fc90d": self.design_value(s.fc90k, duration),
            "fmd": self.design_value(s.fmk, duration),
            "frd": self.design_value(s.frk, duration),
        }

# Load and combination
@dataclass
class Action:
    name: str
    gamma_G: float = 1.35
    gamma_Q: float = 1.5
    psi0: float = 0.7
    is_permanent: bool = False
    nominal: float = 0.0  

def uls_basic(permanent: List[Action], variable: List[Action]) -> List[Tuple[str, float]]:
    combos: List[Tuple[str, float]] = []
    for lead_idx, Qlead in enumerate(variable):
        terms = [(G.name, G.gamma_G) for G in permanent]
        terms.append((Qlead.name, Qlead.gamma_Q))
        for i, Qi in enumerate(variable):
            if i == lead_idx:
                continue
            terms.append((Qi.name, Qi.gamma_Q * Qi.psi0))
        combos.extend(terms)
    return combos

# --- Ansys eksport (stub) ---
class AnsysExporter:
    def __init__(self, backend: str = "MAPDL"):
        self.backend = backend

    def export_material(self, name: str, o: OrthoElastic) -> Dict[str, float]:
        return {"NAME": name, "EX": o.EX, "EY": o.EY, "EZ": o.EZ,
                "PRXY": o.PP if False else o.PRXY, "PRYZ": o.PRYZ, "PRXZ": o.PRXZ,
                "GXY": o.GXY, "GYZ": o.GYZ, "GXZ": o.GXZ}

    def write_csv(self, path: str, data: Dict[str, float]) -> None:
        import csv
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data.keys()))
            w.writeheader(); w.writerow(data)
