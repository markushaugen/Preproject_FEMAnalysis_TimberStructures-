# main.py
import argparse, json, csv, os
from ec5.design_values import TimberDesign, ServiceClass, LoadDuration, Action, uls_basic, AnsysExporter
from ec5.materials import get_timber, list_classes
from ec5.geometry import Geometry
from ec5.connection import FastenerSetup, eym_single_shear_design


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="EC5 parameters + simple geometry")
    p.add_argument("--class", dest="cls", default="C24",
                   help=f"Timber class (options: {', '.join(list_classes())})")
    p.add_argument("--sc", dest="sc", type=int, default=1, choices=[1,2,3],
                   help="Service class 1/2/3")
    p.add_argument("--duration", dest="dur", default="short",
                   choices=["permanent","long","medium","short","instant"],
                   help="Load duration for k_mod")
    p.add_argument("--out", dest="out", choices=["table","json","csv"], default="table",
                   help="Output format")
    p.add_argument("--export-ansys", dest="ansys", action="store_true",
                   help="Also export Engineering Data CSV for Ansys")

    # Geometry (mm)
    p.add_argument("--L", type=float, default=4000, help="Beam length")
    p.add_argument("--H", type=float, default=400, help="Beam height")
    p.add_argument("--B", type=float, default=140, help="Beam width (thickness)")
    p.add_argument("--t_plate", type=float, default=8, help="Steel plate thickness")
    p.add_argument("--slot_depth", type=float, default=20, help="Slot depth")
    p.add_argument("--n_dowels", type=int, default=4, help="Number of dowels")
    p.add_argument("--d_dowel", type=float, default=12, help="Dowel diameter")
    p.add_argument("--s_dowel", type=float, default=120, help="Dowel spacing")
    p.add_argument("--a_edge", type=float, default=60, help="Edge distance")
    return p.parse_args()


def sc_enum(n):
    return {1: ServiceClass.SC1, 2: ServiceClass.SC2, 3: ServiceClass.SC3}[n]

def dur_enum(s):
    m = {
        "permanent": LoadDuration.PERMANENT,
        "long": LoadDuration.LONG,
        "medium": LoadDuration.MEDIUM,
        "short": LoadDuration.SHORT,
        "instant": LoadDuration.INSTANTANEOUS,
    }
    return m[s]

if __name__ == "__main__":
    args = parse_args()
    elastic, strength = get_timber(args.cls)
    timber = TimberDesign(elastic=elastic, strength_char=strength, service_class=sc_enum(args.sc))
    fd = timber.strengths_design(duration=dur_enum(args.dur))

    # --- Output ---
    if args.out == "table":
        print(f"[{args.cls}] SC{args.sc} duration={args.dur}")
        for k,v in fd.items():
            print(f"  {k:>6}: {v:,.2f} Pa")
    elif args.out == "json":
        print(json.dumps({"class": args.cls, "service_class": args.sc, "duration": args.dur,
                          "design_strengths_Pa": fd}, indent=2))
    else:  # csv
        fname = f"design_{args.cls}_SC{args.sc}_{args.dur}.csv"
        with open(fname, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["key","value_Pa"])
            for k,v in fd.items(): w.writerow([k, v])
        print(f"Wrote {fname}")
    
    # Geometry (mm) 
    geo = Geometry(
        beam_length=args.L, beam_height=args.H, beam_width=args.B,
        plate_thickness=args.t_plate, slot_depth=args.slot_depth,
        num_dowels=args.n_dowels, dowel_diameter=args.d_dowel,
        dowel_spacing=args.s_dowel, edge_distance=args.a_edge
    )
    try:
        geo.validate()
    except AssertionError as e:
        print(f"[GEOMETRY ERROR] {e}")
        raise
    coords = geo.dowel_positions()
    print("\nGeometry (mm): "
        f"L={geo.beam_length}, H={geo.beam_height}, B={geo.beam_width}, "
        f"t_plate={geo.plate_thickness}, slot={geo.slot_depth}, "
        f"n={geo.num_dowels}, d={geo.dowel_diameter}, s={geo.dowel_spacing}, a_edge={geo.edge_distance}")
    print("Dowel positions (x,z) mm:", coords)

        # --- EC5 EYM connection design (Step 2) ---
    rho_k = 420.0  # characteristic density [kg/m3] for C24 (approx.)

    setup = FastenerSetup(
        d_mm=args.d_dowel,
        t_wood_mm=args.B,     # timber thickness per shear plane (slotted plate -> beam width)
        n=args.n_dowels
    )

    eym = eym_single_shear_design(
        timber=timber,
        duration=dur_enum(args.dur),
        setup=setup,
        rho_k=rho_k
    )

    print("\nEC5 EYM design capacities (single shear):")
    print(f"  Rd_mode_a (bearing) [N]: {eym['Rd_mode_a_N']:.1f}")
    print(f"  Rd_mode_b (1 hinge) [N]:  {eym['Rd_mode_b_N']:.1f}")
    print(f"  Rd_mode_c (2 hinges) [N]: {eym['Rd_mode_c_N']:.1f}")
    print(f"  Governing per fastener [N]: {eym['Rd_governing_per_fastener_N']:.1f}")
    print(f"  Total for n={args.n_dowels} [N]: {eym['Rd_total_N']:.1f}")


    # Write combined params for later use 
    os.makedirs("out", exist_ok=True)
    with open("out/model_params.json", "w") as fjson:
        json.dump({
            "class": args.cls, "service_class": args.sc, "duration": args.dur,
            "design_strengths_Pa": fd,
            "geometry_mm": {
                "L": geo.beam_length, "H": geo.beam_height, "B": geo.beam_width,
                "t_plate": geo.plate_thickness, "slot_depth": geo.slot_depth,
                "n_dowels": geo.num_dowels, "d_dowel": geo.dowel_diameter,
                "s_dowel": geo.dowel_spacing, "a_edge": geo.edge_distance,
                "dowel_positions": coords
            }
        }, fjson, indent=2)
    print("Wrote out/model_params.json")

    # Example: ULS factors (optional demo)
    G = [Action("G_dead", is_permanent=True)]
    Q = [Action("Q_snow", psi0=0.7), Action("Q_wind", psi0=0.6)]
    combo = uls_basic(G, Q)
    print("ULS combo factors:", combo)

        # Ansys export (optional)
    if args.ansys:
        exporter = AnsysExporter()
        mat_dict = exporter.export_material(f"{args.cls}_SC{args.sc}", timber.elastic)
        exporter.write_csv(f"material_{args.cls}_SC{args.sc}.csv", mat_dict)
        print(f"Wrote material_{args.cls}_SC{args.sc}.csv")

