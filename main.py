import argparse
import json
from math import isfinite
from pathlib import Path

from projects.brutalist import model as brutalist
from projects.bridge import model as bridge
from projects.canopy import model as canopy
from projects.extension import model as extension
from projects.gable import model as gable
from projects.house import model as house
from projects.observatory import model as observatory
from projects.shelter import model as shelter
from projects.hypar import model as hypar
from projects.terrace import model as terrace
from projects.atrium import model as atrium
from projects.cabin import model as cabin
from projects.auditorium import model as auditorium
from projects.facade import model as facade
from projects.slab import model as slab
from projects.vierendeel import model as vierendeel

PROJECTS = {
    "auditorium_acoustics": auditorium,
    "historic_facade": facade,
    "slab_opening": slab,
    "vierendeel_cantilever": vierendeel,
    "shell": shelter,
    "gable": gable,
    "observatory": observatory,
    "glass_house": house,
    "canopy_anchor": canopy,
    "steel_hypar": hypar,
    "concrete_arch_bridge": bridge,
    "roof_extension": extension,
    "brutalist_housing": brutalist,
    "concrete_terrace": terrace,
    "atrium_walkway": atrium,
    "thermal_cabin": cabin,
}

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate drawings, model geometry and analysis results.")
    parser.add_argument("input_json", type=Path, help="Path to the case parameters.")
    parser.add_argument("--plans-only", action="store_true", help="Generate SVG drawings only.")
    args = parser.parse_args()
    path = args.input_json
    with path.open(encoding="utf-8") as file:
        case = json.load(file)
    if not isinstance(case, dict):
        parser.error("The JSON input must be an object.")

    model = case["structural_model"]["model"]
    if model not in PROJECTS:
        parser.error(f"Unknown structural model: {model}")
    stem = path.with_suffix("")
    project = PROJECTS[model]
    if "reinforcement" in case and model != "concrete_terrace":
        parser.error("These cases use homogeneous concrete without reinforcement.")
    if "mesh" in case:
        size = case["mesh"]["element_size_m"]
        if not isfinite(size) or size <= 0:
            parser.error("The mesh size must be finite and positive.")

    if args.plans_only:
        project.draw_case(stem, case)
        return
    step = path.with_name(stem.name + "-model.step")
    mesh = path.with_name(stem.name + "-mesh.msh")
    result_suffix = {
        "thermal_cabin": "-temperature.vtu",
        "auditorium_acoustics": "-acoustic-results.json",
    }.get(model, "-displacements.vtu")
    result = path.with_name(stem.name + result_suffix)
    project.run_case(stem, step, mesh, result, case)
    outputs = (step, mesh, result) if mesh.exists() else (step, result)
    print("Wrote " + ", ".join(map(str, outputs)))

if __name__ == "__main__":
    main()
