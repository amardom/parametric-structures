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

PROJECTS = {
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
    parser = argparse.ArgumentParser(description="Generate plans, a STEP model and an Elmer result.")
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
    if "reinforcement" in case and model != "concrete_terrace":
        parser.error("These cases use homogeneous concrete without reinforcement.")
    size = case["mesh"]["element_size_m"]
    if not isfinite(size) or size <= 0:
        parser.error("The mesh size must be finite and positive.")

    stem = path.with_suffix("")
    if args.plans_only:
        PROJECTS[model].draw_case(stem, case)
        return
    step = path.with_name(stem.name + "-model.step")
    mesh = path.with_name(stem.name + "-mesh.msh")
    result_suffix = "-temperature.vtu" if model == "thermal_cabin" else "-displacements.vtu"
    result = path.with_name(stem.name + result_suffix)
    PROJECTS[model].run_case(stem, step, mesh, result, case)
    print(f"Wrote {step}, {mesh} and {result}")

if __name__ == "__main__":
    main()
