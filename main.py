# main.py
import argparse, json, csv, os
from ec5.design_values import TimberDesign, ServiceClass, LoadDuration, Action, uls_basic, AnsysExporter
from ec5.materials import get_timber, list_classes
from ec5.geometry import Geometry
from ec5.connection import FastenerSetup, eym_single_shear_design
from ec5.exporter import MapdlExporter


def parse_args():
    p = argparse.ArgumentParser(description="EC5 parameters + simple geometry")
    p.add_argument("--class", dest="cls", default="C24",
                help=f"Timber class (options: {', '.join(list_classes())})")
    p.add_argument("--sc", dest="sc", type=int, default=1, choices=[1, 2, 3])
    p.add_argument("--duration", dest="dur", default="short",
                choices=["permanent", "long", "medium", "short", "instant"])

    p.add_argument("--out", dest="out", choices=["table", "json", "csv"], default="table")
    p.add_argument("--export-ansys", dest="ansys", action="store_true")
    p.add_argument("--export-mapdl", dest="mapdl", action="store_true",
            help="Export MAPDL .mac file for the generated model")


    # Geometry (mm)
    p.add_argument("--L", type=float, default=4000)
    p.add_argument("--H", type=float, default=400)
    p.add_argument("--B", type=float, default=140)
    p.add_argument("--t_plate", type=float, default=8)
    p.add_argument("--slot_depth", type=float, default=20)
    p.add_argument("--n_dowels", type=int, default=4)
    p.add_argument("--d_dowel", type=float, default=12)
    p.add_argument("--s_dowel", type=float, default=120)
    p.add_argument("--a_edge", type=float, default=60)

    return p.parse_args()


def sc_enum(n):
    return {1: ServiceClass.SC1, 2: ServiceClass.SC2, 3: ServiceClass.SC3}[n]


def dur_enum(s):
    return {
        "permanent": LoadDuration.PERMANENT,
        "long": LoadDuration.LONG,
        "medium": LoadDuration.MEDIUM,
        "short": LoadDuration.SHORT,
        "instant": LoadDuration.INSTANTANEOUS,
    }[s]


if __name__ == "__main__":
    args = parse_args()

    # Material setup 
    elastic, strength = get_timber(args.cls)
    timber = TimberDesign(elastic=elastic, strength_char=strength,
                        service_class=sc_enum(args.sc))
    fd = timber.strengths_design(duration=dur_enum(args.dur))

    # Output strengths
    if args.out == "table":
        print(f"[{args.cls}] SC{args.sc} duration={args.dur}")
        for k, v in fd.items():
            print(f"  {k:>6}: {v:,.2f} Pa")
    elif args.out == "json":
        print(json.dumps({
            "class": args.cls,
            "service_class": args.sc,
            "duration": args.dur,
            "design_strengths_Pa": fd
        }, indent=2))
    else:
        fname = f"design_{args.cls}_SC{args.sc}_{args.dur}.csv"
        with open(fname, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["key", "value_Pa"])
            for k, v in fd.items():
                w.writerow([k, v])
        print(f"Wrote {fname}")

    # Geometry 
    geo = Geometry(
        beam_length=args.L, beam_height=args.H, beam_width=args.B,
        plate_thickness=args.t_plate, slot_x1=600, slot_x2=args.L, slot_y1=30, slot_y2=args.H - 30, clearance_y=2.0,
        num_dowels=args.n_dowels, dowel_diameter=args.d_dowel,
        dowel_spacing=args.s_dowel, edge_distance=args.a_edge
    )

    try:
        geo.validate()
    except AssertionError as e:
        print(f"[GEOMETRY ERROR] {e}")
        raise

    coords = geo.dowel_positions()
    print("\nGeometry (mm): L={}, H={}, B={}, t_plate={}, slot={}, n={}, d={}, s={}, a_edge={}"
        .format(args.L, args.H, args.B, args.t_plate, args.slot_depth,
                args.n_dowels, args.d_dowel, args.s_dowel, args.a_edge))
    print("Dowel positions (x,z) mm:", coords)

    # EC5 EYM connection design 
    rho_k = 420.0  # C24 density
    setup = FastenerSetup(
        d_mm=args.d_dowel,
        t_wood_mm=args.B,
        n=args.n_dowels
    )

    eym = eym_single_shear_design(
        timber=timber,
        duration=dur_enum(args.dur),
        setup=setup,
        rho_k=rho_k
    )

    print("\nEC5 EYM design capacities (single shear):")
    print(f"  Rd_mode_a [N]: {eym['Rd_mode_a_N']:.1f}")
    print(f"  Rd_mode_b [N]: {eym['Rd_mode_b_N']:.1f}")
    print(f"  Rd_mode_c [N]: {eym['Rd_mode_c_N']:.1f}")
    print(f"  Governing per fastener [N]: {eym['Rd_governing_per_fastener_N']:.1f}")
    print(f"  Total for n={args.n_dowels} [N]: {eym['Rd_total_N']:.1f}")

    # Save model parameters
    os.makedirs("out", exist_ok=True)
    with open("out/model_params.json", "w") as fjson:
        json.dump({
            "class": args.cls,
            "service_class": args.sc,
            "duration": args.dur,
            "design_strengths_Pa": fd,
            "geometry_mm": {
                "L": args.L, "H": args.H, "B": args.B,
                "t_plate": args.t_plate, "slot_depth": args.slot_depth,
                "n_dowels": args.n_dowels, "d_dowel": args.d_dowel,
                "s_dowel": args.s_dowel, "a_edge": args.a_edge,
                "dowel_positions": coords
            }
        }, fjson, indent=2)
    print("Wrote out/model_params.json")

    # Example ULS combinations 
    G = [Action("G_dead", nominal=1.0, is_permanent=True)]
    Q = [Action("Q_snow", nominal=1.0, psi0=0.7),
        Action("Q_wind", nominal=1.0, psi0=0.6)]
    combo = uls_basic(G, Q)
    print("ULS combo factors:", combo)

    # Optional Ansys export 
    if args.ansys:
        exporter = AnsysExporter()
        mat_dict = exporter.export_material(f"{args.cls}_SC{args.sc}", timber.elastic)
        exporter.write_csv(f"material_{args.cls}_SC{args.sc}.csv", mat_dict)
        print(f"Wrote material_{args.cls}_SC{args.sc}.csv")

    if args.mapdl:
        os.makedirs("out", exist_ok=True)
        exporter = MapdlExporter(element_size_mm=100.0)
        mapdl_path = os.path.join("out", "mapdl_model.mac")
        exporter.export_mapdl_model(
            path=mapdl_path,
            timber=timber,
            geo=geo,
            setup=setup,
            model_name="timber_conn",
        )
        print(f"Wrote MAPDL script: {mapdl_path}")


