import argparse
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
import json
from itertools import combinations, product
from math import atan2, dist, isclose, pi
from pathlib import Path
from shutil import copyfile
import subprocess
import sys
from tempfile import TemporaryDirectory

import cadquery as cq
import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader

WEBSITE = Path(__file__).resolve().parent
ROOT = WEBSITE.parent
PROJECTS = ROOT / 'projects'

def run_variant(path, project, variant, plans_only):
    command = [sys.executable, "-B", str(ROOT / "main.py"), str(path)]
    if plans_only:
        command.append("--plans-only")
    subprocess.run(command, check=True)
    destination = WEBSITE / "plans" / project
    destination.mkdir(parents=True, exist_ok=True)
    for drawing in ("plan", "elevation", "section"):
        copyfile(path.with_name(f"{path.stem}-{drawing}.svg"),
                 destination / f"{variant}-{drawing}.svg")

def add_mass(masses, shape, material, settings):
    densities = {
        "Concrete": settings.get("concrete_density_kg_m3", settings.get("density_kg_m3", 2500)),
        "Steel": settings.get("steel_density_kg_m3", 7850),
        "Glass": settings.get("glass_density_kg_m3", 2500),
    }
    masses[material] = masses.get(material, 0) + shape.Volume() * densities[material] / 1e9

def step_geometry(path, settings):
    solids = cq.importers.importStep(str(path)).solids().vals()
    parts, masses = [], {}
    for solid in solids:
        points, faces = solid.tessellate(0.5)
        bounds = solid.BoundingBox()
        if abs(bounds.ylen - 12) < 0.001:
            material = "glass"
        else:
            material = "roof" if bounds.zmin > 0.001 else "wall"
        add_mass(masses, solid, "Glass" if material == "glass" else "Concrete", settings)
        parts.append({
            "material": material,
            "points": [round(coordinate / 1000, 5) for point in points for coordinate in point.toTuple()],
            "faces": [list(face) for face in faces],
        })
    return parts, masses

def shell_result(path, model, roof_level):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    mesh = reader.GetOutput()
    points = vtk_to_numpy(mesh.GetPoints().GetData())
    data = mesh.GetPointData()
    displacement = [vtk_to_numpy(data.GetArray(f"deflection {axis}")) for axis in (1, 2, 3)]
    faces = []
    for index in range(mesh.GetNumberOfCells()):
        kind = mesh.GetCellType(index)
        if kind == 9 or (model == "gable" and kind == 3):
            cell = mesh.GetCell(index)
            faces.append([cell.GetPointId(node) for node in range(cell.GetNumberOfPoints())])
    if model == "gable":
        sample = [i for i, (_, _, z) in enumerate(points) if z >= roof_level - 1e-6]
    else:
        sample = [i for i, (_, y, z) in enumerate(points)
                  if abs(y) < 1e-6 and abs(z - roof_level) < 1e-6]
    assert faces and sample
    if model == "gable":
        assert any(len(face) == 2 for face in faces)
    return {
        "points": points.round(5).ravel().tolist(),
        "displacement": [round(float(v) * 1000, 7 if model == "gable" else 4) for row in zip(*displacement, strict=True) for v in row],
        "faces": faces,
        "front_mm": round(-1000 * float(min(displacement[2][i] for i in sample)), 2),
    }

def shelter_metrics(path, case):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    mesh = reader.GetOutput()
    points = vtk_to_numpy(mesh.GetPoints().GetData())
    data = mesh.GetPointData()
    vertical = vtk_to_numpy(data.GetArray("deflection 3"))
    forces = vtk_to_numpy(data.GetArray("deflection loads 3"))
    geometry, settings = case["geometry"], case["structural_model"]
    width, depth, height, wall, roof = (geometry[key] for key in
        ("width_m", "depth_m", "clear_height_m", "wall_thickness_m", "roof_thickness_m"))
    window = geometry["rear_window"]
    left = (width-window["width_m"])/2 + window["offset_m"]
    right = left + window["width_m"]
    rear, top = depth-wall/2, height+roof/2
    x,y,z = points.T
    over_window = (np.isclose(y,rear) & np.isclose(z,top)
                   & (x >= left-1e-6) & (x <= right+1e-6))
    bases = np.isclose(z,0)
    rear_base = np.isclose(y[bases],rear)
    side_bases = (np.isclose(x[bases],wall/2),np.isclose(x[bases],width-wall/2))
    corner = rear_base & (side_bases[0] | side_bases[1])
    reactions = forces[bases] / 1000
    by_wall = [float(np.dot(reactions,mask*(1-0.5*corner))) for mask in (*side_bases,rear_base)]
    roof_area = (width-wall)*rear
    walls_area = (width-wall+2*rear)*top - (right-left)*(top-window["sill_height_m"])
    expected = ((roof_area*roof + walls_area*wall)*settings["density_kg_m3"]*settings["gravity_m_s2"]
                + roof_area*case["loads"]["roof_pressure_pa"])/1000
    if (not over_window.any() or not np.isfinite(by_wall).all()
            or not isclose(sum(by_wall),expected,rel_tol=0.002)):
        raise ValueError(f"Shelter base reactions do not balance the applied loads: {by_wall} vs {expected:.2f} kN.")
    return {"window_mm": float(-1000*vertical[over_window].min()), "wall_reactions_kn": by_wall}

def build_shelter(plans_only):
    baseline = json.loads((PROJECTS / "shelter" / "concrete-shelter.json").read_text())

    def solve(parameters):
        width, thickness, window = parameters
        key = f"{width}-{thickness}-{window}"
        config = {**baseline, "geometry": {**baseline["geometry"]}}
        geometry = config["geometry"]
        opening = 4.8 if window == "original" else 7.2
        offset = .75-(width-opening)/2 if window == "shifted" else 0
        geometry.update(width_m=width,roof_thickness_m=thickness/100,
                        rear_window={**geometry["rear_window"],"width_m":opening,"offset_m":offset})
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"shelter-{key}.json"
            path.write_text(json.dumps(config))
            run_variant(path,"shelter",key,plans_only)
            if plans_only:
                return key,None
            stem = path.with_suffix("")
            roof_level = geometry["clear_height_m"] + geometry["roof_thickness_m"] / 2
            vtu = stem.with_name(stem.name+"-displacements.vtu")
            result = shell_result(vtu,"shelter",roof_level)
            result.update(shelter_metrics(vtu,config))
            cad,masses = step_geometry(stem.with_name(stem.name+"-model.step"),config["structural_model"])
            print("shelter",key,result["window_mm"],result["wall_reactions_kn"],flush=True)
            return key,{"cad":cad,"result":result,"material_masses_kg":masses}

    with ThreadPoolExecutor(max_workers=2) as workers:
        cases = dict(workers.map(solve,product((12,15),(30,40),("original","wide","shifted"))))
    if not plans_only:
        (WEBSITE / "cases.js").write_text(
            "window.shelterCases = " + json.dumps(cases,separators=(",",":"),allow_nan=False) + ";\n",
            encoding="utf-8",
        )

def gable_metrics(result, case):
    g, loads, settings = (case[key] for key in ("geometry", "loads", "structural_model"))
    width, depth, eave, projection = (g[k] for k in ("width_m", "depth_m", "eave_height_m", "projection_m"))
    points = np.asarray(result["points"]).reshape(-1, 3)
    movement = np.asarray(result["displacement"]).reshape(-1, 3) / 1000
    tips = []
    for x in (0, width):
        mask = np.all(np.isclose(points,(x,-projection,eave)),axis=1)
        if mask.sum() != 1:
            raise ValueError("Expected one node at each free roof corner.")
        tips.append(float(1000 * movement[mask,2][0]))
    reactions = []
    area = g["column_side_m"]**2
    weight = settings["density_kg_m3"] * settings["gravity_m_s2"]
    for face in result["faces"]:
        if len(face) != 2:
            continue
        a,b = sorted(face, key=lambda j: points[j,2])
        if points[a,2] == 0:
            length = points[b,2]
            reaction = settings["young_modulus_pa"] * area * (movement[a,2]-movement[b,2]) / length
            reaction += weight * area * length / 2
            reactions.append((points[a,1], points[a,0], reaction/1000))
    slope_length = (width**2/4 + g["rise_m"]**2)**.5
    expected = (2*slope_length*(depth+projection)*weight*g["roof_thickness_m"]
                + 4*area*eave*weight - slope_length*projection*loads["corner_uplift_pa"]) / 1000
    if len(reactions) != 4 or abs(sum(v for _,_,v in reactions)-expected) > .15:
        raise ValueError(f"Gable base reactions do not balance the applied loads: {reactions} vs {expected:.2f} kN.")
    result.update(tip_mm=tips, reactions_kn=[round(v,2) for _,_,v in sorted(reactions)],
                  max_abs_mm=float(1000*np.abs(movement[:,2]).max()))
    return result

def build_gable(plans_only):
    baseline = json.loads((PROJECTS / "gable" / "gable-roof.json").read_text())

    def solve(parameters):
        width,rise,projection = parameters
        key = f"{width}-{rise}-{projection}"
        g = {**baseline["geometry"], "width_m":width, "rise_m":rise/100, "projection_m":projection}
        gravity = {**baseline, "geometry":g, "loads":{"corner_uplift_pa":0}}
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"gable-{key}.json"
            path.write_text(json.dumps(gravity))
            run_variant(path,"gable",key,plans_only)
            if plans_only:
                return key,None
            stem = path.with_suffix("")
            cad,masses = step_geometry(str(stem)+"-model.step",baseline["structural_model"])
            result = gable_metrics(shell_result(str(stem)+"-displacements.vtu","gable",g["eave_height_m"]),gravity)
            wind_result = None
            if projection:
                wind = {**gravity,"loads":baseline["loads"]}
                wind_path = Path(directory) / "wind.json"
                wind_path.write_text(json.dumps(wind))
                subprocess.run([sys.executable,"-B",str(ROOT/"main.py"),str(wind_path)],check=True)
                wind_result = gable_metrics(shell_result(wind_path.with_name("wind-displacements.vtu"),"gable",g["eave_height_m"]),wind)
                for shared in ("points","faces"):
                    if wind_result.pop(shared) != result[shared]:
                        raise ValueError("Gable load cases must share the same mesh.")
            print("gable",key,result["tip_mm"],wind_result and wind_result["tip_mm"],flush=True)
            return key,{"cad":cad,"result":result,"wind":wind_result,"material_masses_kg":masses,
                        "depth_m":g["depth_m"],"uplift_pa":baseline["loads"]["corner_uplift_pa"]}

    with ThreadPoolExecutor(max_workers=3) as workers:
        cases = dict(workers.map(solve,product((6,8),(80,120),(0,1,2))))
    if not plans_only:
        (WEBSITE/"gable-cases.js").write_text(
            "window.gableCases = "+json.dumps(cases,separators=(",",":"),allow_nan=False)+";\n",
            encoding="utf-8",
        )

def observatory_result(path, geometry, steel_density):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    mesh = reader.GetOutput()
    points = vtk_to_numpy(mesh.GetPoints().GetData())
    moves = vtk_to_numpy(mesh.GetPointData().GetArray("displacement"))
    if not np.isfinite(moves).all():
        raise ValueError("Non-finite observatory displacement.")
    height = geometry["wall_height_m"]
    shell, ribs, ring = [], [], []
    for i in range(mesh.GetNumberOfCells()):
        cell = mesh.GetCell(i)
        ids = [cell.GetPointId(j) for j in range(cell.GetNumberOfPoints())]
        if cell.GetCellType() == 9:
            shell.append(ids)
        elif cell.GetCellType() == 3:
            (ring if all(isclose(points[j, 2], height, abs_tol=1e-6) for j in ids) else ribs).append(ids)

    border = [{}, {}]
    half = geometry["opening_width_m"] / 2
    stop = geometry["opening_end_deg"] * pi / 180
    for i, (x, y, z) in enumerate(points):
        if abs(abs(x) - half) < 1e-6 and z >= height and atan2(z-height, y) <= stop + 1e-5:
            border[int(x > 0)][(round(float(y), 5), round(float(z), 5))] = i
    samples = sorted(border[0].keys() & border[1].keys())
    assert shell and ribs and ring and len(samples) > 3
    left = [border[0][key] for key in samples]
    right = [border[1][key] for key in samples]
    gaps = [dist(points[a] + moves[a], points[b] + moves[b]) - dist(points[a], points[b])
            for a, b in zip(left, right, strict=True)]
    mass = 0.0
    for part, members in (("rib", ribs), ("ring", ring)):
        diameter, wall = (geometry[f"{part}_{key}_m"] for key in ("diameter", "wall"))
        mass += sum(dist(points[a], points[b]) for a, b in members) * pi * wall * (diameter - wall) * steel_density
    return {
        "points": points.round(5).ravel().tolist(),
        "displacement": (1000 * moves).round(5).ravel().tolist(),
        "shell": shell, "ribs": ribs, "ring": ring,
        "front_mm": round(float(-1000 * moves[:, 2].min()), 4),
        "gap_mm": round(1000 * max(gaps, key=abs), 4),
        "mass_kg": round(mass, 3),
    }

def build_observatory(plans_only):
    baseline = json.loads((PROJECTS / "observatory" / "observatory.json").read_text())
    output = {"baseline": "12-60-14", "geometry": [], "variants": {}}

    def solve(parameters):
        count, diameter, transverse = parameters
        key = f"{count}-{diameter}-{transverse}"
        geometry = {**baseline["geometry"], "interior_arches": count,
                    "rib_diameter_m": diameter / 1000, "transverse_arches": transverse}
        case = {**baseline, "geometry": geometry}
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"observatory-{key}.json"
            path.write_text(json.dumps(case))
            run_variant(path, "observatory", key, plans_only)
            if plans_only:
                return key, None, [], {}
            stem = path.with_suffix("")
            parts, masses = [], {}
            if key == output["baseline"]:
                for shape, name, _, _ in cq.Assembly.load(str(stem) + "-model.step"):
                    material = {"Concrete_base": "wall", "Glazing": "glass"}.get(name.rsplit("/", 1)[-1])
                    if material:
                        add_mass(masses, shape, "Glass" if material == "glass" else "Concrete",
                                 baseline["structural_model"])
                        points, faces = shape.tessellate(12, 0.23)
                        parts.append({
                            "material": material,
                            "points": [round(v / 1000, 5) for point in points for v in point.toTuple()],
                            "faces": faces,
                        })
                assert len(parts) == 2
            result = observatory_result(str(stem) + "-displacements.vtu", geometry,
                                        baseline["structural_model"]["steel_density_kg_m3"])
            print("observatory", key, result["mass_kg"], result["gap_mm"], result["front_mm"], flush=True)
            return key, result, parts, masses

    with ThreadPoolExecutor(max_workers=3) as workers:
        variants = list(workers.map(solve, product((12, 8, 4), (60, 45, 35), (14, 10, 6))))
    if not plans_only:
        _, _, output["geometry"], fixed_masses = variants[0]
        for key, result, _, _ in variants:
            output["variants"][key] = {"result": result,
                                       "material_masses_kg": {"Steel": result["mass_kg"], **fixed_masses}}
    if plans_only:
        return
    (WEBSITE / "observatory-cases.js").write_text(
        "window.observatoryCases = " + json.dumps(output, separators=(",", ":"), allow_nan=False) + ";\n",
        encoding="utf-8",
    )

def house_result(path, g):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    mesh = reader.GetOutput()
    points = vtk_to_numpy(mesh.GetPoints().GetData())
    movements = vtk_to_numpy(mesh.GetPointData().GetArray("displacement"))
    w, d, h = (g[name] for name in ("width_m", "depth_m", "storey_height_m"))

    def drop(x, y, z):
        matches = np.flatnonzero(np.all(np.isclose(points, (x, y, z), atol=1e-6, rtol=0), axis=1))
        if len(matches) != 1:
            raise ValueError(f"Expected one node at {(x, y, z)}, got {len(matches)}")
        return round(-1000 * float(movements[matches[0], 2]), 4)

    faces = []
    for index in range(mesh.GetNumberOfCells()):
        cell = mesh.GetCell(index)
        if cell.GetCellType() in (3, 9):
            faces.append([cell.GetPointId(i) for i in range(cell.GetNumberOfPoints())])
    assert np.isfinite(movements).all() and any(len(face) == 2 for face in faces)
    assert np.all(movements[points[:, 2] == 0] == 0)
    return {
        "points": points.round(5).ravel().tolist(),
        "displacement": (1000 * movements).round(5).ravel().tolist(),
        "faces": faces,
        "front_mm": round(-1000 * float(movements[:, 2].min()), 4),
        "floor_corner_mm": drop(w, d, h),
        "roof_corner_mm": drop(w, d, 2*h),
        "door_mm": drop(g["door_center_m"], d, h),
    }

def build_house(plans_only):
    case = json.loads((PROJECTS / "house" / "glass-house.json").read_text())
    variants = {}
    with TemporaryDirectory() as directory:
        for cm in (160, 240, 320):
            path = Path(directory) / f"glass-house-{cm}.json"
            g = case["geometry"]
            g["column_setback_m"] = cm / 100
            path.write_text(json.dumps(case))
            run_variant(path, "house", cm, plans_only)
            if plans_only:
                continue
            stem = str(path.with_suffix(""))
            result = house_result(stem + "-displacements.vtu", g)
            cad, masses = [], {}
            for shape, name, _, _ in cq.Assembly.load(stem + "-model.step"):
                name = name.rsplit("/", 1)[-1]
                material = "door" if name == "Door_glass" else "glass" if name.startswith("Glass_") else "wall"
                add_mass(masses, shape, "Glass" if material in ("glass", "door") else "Concrete",
                         case["structural_model"])
                points, faces = shape.tessellate(0.5)
                cad.append({
                    "material": material,
                    "points": [round(v/1000, 5) for point in points for v in point.toTuple()],
                    "faces": faces,
                })
            variants[str(cm)] = {"cad": cad, "result": result, "material_masses_kg": masses}
            print("house", cm, result["floor_corner_mm"], result["roof_corner_mm"], result["door_mm"], flush=True)
    if plans_only:
        return
    (WEBSITE / "house-cases.js").write_text(
        "window.houseCases = " + json.dumps(variants, separators=(",", ":"), allow_nan=False) + ";\n",
        encoding="utf-8",
    )

def canopy_result(path, metrics):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    grid = reader.GetOutput()
    points = vtk_to_numpy(grid.GetPoints().GetData())
    moves = vtk_to_numpy(grid.GetPointData().GetArray("displacement"))
    materials = vtk_to_numpy(grid.GetCellData().GetArray("anchor_body"))
    connectivity = vtk_to_numpy(grid.GetCells().GetConnectivityArray())
    offsets = vtk_to_numpy(grid.GetCells().GetOffsetsArray())
    surfaces = {}
    for i in np.flatnonzero(materials):
        material = int(materials[i])
        tet = connectivity[offsets[i]:offsets[i+1]]
        faces = surfaces.setdefault(material, set())
        for face in combinations(tet, 3):
            key = tuple(sorted(map(int, face)))
            if key in faces:
                faces.remove(key)
            else:
                faces.add(key)
    assert 1 in surfaces and 2 in surfaces and len(surfaces) == len(metrics["bolts"]) + 2
    used = sorted({i for faces in surfaces.values() for face in faces for i in face})
    indices = {old: new for new, old in enumerate(used)}
    return {
        "points": points[used].round(6).ravel().tolist(),
        "displacement": (1000 * moves[used]).round(6).ravel().tolist(),
        "surfaces": {k: [[indices[i] for i in face] for face in sorted(v)] for k, v in surfaces.items()},
        "front_mm": metrics["max_displacement_mm"],
        **metrics,
    }

def build_canopy(plans_only):
    baseline = json.loads((PROJECTS / "canopy" / "canopy.json").read_text())
    def solve(path):
        key = path.stem.removeprefix("canopy-")
        run_variant(path, "canopy", key, plans_only)
        if plans_only:
            return key, None
        stem = str(path.with_suffix(""))
        metrics = json.loads(Path(stem + "-anchor-results.json").read_text())
        result = canopy_result(stem + "-displacements.vtu", metrics)
        cad, masses = [], {}
        for shape, name, _, _ in cq.Assembly.load(stem + "-model.step"):
            name = name.rsplit("/", 1)[-1]
            material = "wall" if name == "Concrete" else "glass" if name.startswith("Glass_") else "anchor"
            add_mass(masses, shape, {"wall": "Concrete", "glass": "Glass", "anchor": "Steel"}[material],
                     baseline["structural_model"])
            points, faces = shape.tessellate(0.8)
            cad.append({
                "material": material,
                "points": [round(v/1000, 6) for point in points for v in point.toTuple()],
                "faces": faces,
            })
        print("canopy", key, result["opening_mm"], result["bolts"], flush=True)
        return key, {"cad": cad, "result": result, "material_masses_kg": masses}

    with TemporaryDirectory() as directory:
        paths = []
        for count, force in product((4, 6), (20, 40)):
            path = Path(directory) / f"canopy-{count}-{force}.json"
            baseline["geometry"]["bolts"] = count
            baseline["loads"]["tie_force_kn"] = force
            path.write_text(json.dumps(baseline))
            paths.append(path)
        with ThreadPoolExecutor(2) as workers:
            cases = dict(workers.map(solve, paths))
    if plans_only:
        return
    dataset = {"tie_angle_deg": baseline["loads"]["tie_angle_deg"], "variants": cases}
    (WEBSITE / "canopy-cases.js").write_text(
        "window.canopyCases = " + json.dumps(dataset, separators=(",", ":"), allow_nan=False) + ";\n",
        encoding="utf-8",
    )

def hypar_result(path, case):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    mesh = reader.GetOutput()
    points = vtk_to_numpy(mesh.GetPoints().GetData())
    movement = vtk_to_numpy(mesh.GetPointData().GetArray("displacement"))
    faces = []
    for index in range(mesh.GetNumberOfCells()):
        cell = mesh.GetCell(index)
        if cell.GetCellType() in (3, 9):
            faces.append([cell.GetPointId(i) for i in range(cell.GetNumberOfPoints())])
    fixed = np.isclose(points[:, 0], 0)
    if not faces or not fixed.any() or not np.isfinite(movement).all() or not np.allclose(movement[fixed], 0):
        raise ValueError("Invalid hypar displacements or wall restraints.")
    g = case["geometry"]
    tips = []
    for sign in (-1, 1):
        coordinates = (g["projection_m"], sign*g["width_m"]/2, sign*g["tip_rise_m"])
        indices = np.flatnonzero(np.all(np.isclose(points, coordinates, atol=1e-6), axis=1))
        if len(indices) != 1:
            raise ValueError(f"Expected one node at the free tip {coordinates}.")
        tips.append(float(1000 * movement[indices[0], 2]))
    return {
        "points": points.round(5).ravel().tolist(),
        "displacement": (1000 * movement).round(5).ravel().tolist(),
        "faces": faces,
        "front_mm": float(1000 * np.abs(movement[:, 2]).max()),
        "tips_mm": tips,
    }

def hypar_step_geometry(path, steel_density):
    cad, masses = [], {}
    settings = {"steel_density_kg_m3": steel_density}
    materials = {"Skin": "roof", "Wall_context": "wall", "Door_context": "hyparDoor"}
    for shape, name, _, _ in cq.Assembly.load(str(path)):
        material = materials.get(name.rsplit("/", 1)[-1], "steel")
        if material in ("roof", "steel"):
            add_mass(masses, shape, "Steel", settings)
        points, faces = shape.tessellate(0.5)
        cad.append({"material": material,
                    "points": [round(v/1000, 6) for point in points for v in point.toTuple()],
                    "faces": faces})
    return cad, masses

def build_hypar(plans_only):
    sys.path.insert(0, str(ROOT))
    from projects.hypar.model import wall_moment

    case = json.loads((PROJECTS / "hypar" / "steel-hypar.json").read_text())

    def solve(parameters):
        rise, projection = parameters
        key = f"{rise}-{projection}"
        geometry = {**case["geometry"], "tip_rise_m": rise/100, "projection_m": projection}
        variant = {**case, "geometry": geometry}
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"steel-hypar-{key}.json"
            path.write_text(json.dumps(variant))
            run_variant(path, "hypar", key, plans_only)
            if plans_only:
                return key, None
            stem = str(path.with_suffix(""))
            wind = hypar_result(stem + "-displacements.vtu", variant)
            wind["wall_moment_knm"] = wall_moment(variant)

            gravity = {**variant, "loads": dict.fromkeys(variant["loads"], 0)}
            gravity_path = path.with_name("gravity.json")
            gravity_path.write_text(json.dumps(gravity))
            subprocess.run([sys.executable, "-B", str(ROOT / "main.py"), str(gravity_path)], check=True)
            self_weight = hypar_result(gravity_path.with_name("gravity-displacements.vtu"), gravity)
            self_weight["wall_moment_knm"] = wall_moment(gravity)
            for key_to_share in ("points", "faces"):
                if self_weight.pop(key_to_share) != wind[key_to_share]:
                    raise ValueError("Hypar load cases must share the same mesh and node order.")

            cad, masses = hypar_step_geometry(stem + "-model.step", case["structural_model"]["density_kg_m3"])
            print("hypar", key, "self-weight", self_weight["tips_mm"], "wind", wind["tips_mm"], flush=True)
            return key, {"cad": cad, "result": wind, "gravity": self_weight,
                         "material_masses_kg": masses, "geometry": geometry,
                         "uplift_pa": [variant["loads"][f"{side}_uplift_pa"] for side in ("left", "right")]}

    with ThreadPoolExecutor(max_workers=2) as workers:
        variants = dict(workers.map(solve, product((30, 60), (3, 6))))
    if not plans_only:
        (WEBSITE / "hypar-cases.js").write_text(
            "window.hyparCases = " + json.dumps(variants, separators=(",", ":"), allow_nan=False) + ";\n",
            encoding="utf-8",
        )

def bridge_result(path, case, *, removed=False):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    mesh = reader.GetOutput()
    points = vtk_to_numpy(mesh.GetPoints().GetData())
    movement = vtk_to_numpy(mesh.GetPointData().GetArray("displacement"))
    g, h = case["geometry"], case["hangers"]
    faces, hangers = [], {}
    area = pi * (h["diameter_mm"]/1000)**2 / 4
    for index in range(mesh.GetNumberOfCells()):
        cell = mesh.GetCell(index)
        if cell.GetCellType() not in (3, 9):
            continue
        ids = [cell.GetPointId(i) for i in range(cell.GetNumberOfPoints())]
        faces.append(ids)
        if len(ids) == 2:
            a, b = ids
            axis = points[b] - points[a]
            length = np.linalg.norm(axis)
            strain = float(np.dot(movement[b]-movement[a], axis) / length**2)
            location = tuple(round(float(value),5) for value in points[a,:2])
            hangers[location] = strain * h["young_modulus_pa"] * area / 1000
    deck = np.isclose(points[:, 2], 0)
    fixed = np.isclose(points[:, 2], -g["abutment_height_m"])
    if not (len(hangers) == 2*h["count_per_side"]-int(removed) and min(hangers.values()) > 0
            and deck.any() and fixed.any() and np.isfinite(movement).all()
            and np.allclose(movement[fixed], 0)):
        raise ValueError("Invalid bridge solution, foundation restraints or hanger tension.")
    midspan = np.isclose(points[:,0],g["span_m"]/2) & deck
    edge_deflection = []
    for y in (-g["deck_width_m"]/2,g["deck_width_m"]/2):
        mask = midspan & np.isclose(points[:,1],y)
        if mask.sum() != 1:
            raise ValueError("Expected one deck edge node at each side of midspan.")
        edge_deflection.append(float(1000*movement[mask,2][0]))
    return {
        "points": points.round(5).ravel().tolist(),
        "displacement": (1000 * movement).round(5).ravel().tolist(),
        "faces": faces,
        "front_mm": float(1000 * np.abs(movement[:, 2]).max()),
        "deck_mm": float(-1000 * movement[deck, 2].min()),
        "hanger_kn": max(hangers.values()),
        "edge_difference_mm": abs(edge_deflection[0]-edge_deflection[1]),
    }, hangers

def build_bridge(plans_only):
    sys.path.insert(0, str(ROOT))
    from projects.bridge.model import solve_bridge

    case = json.loads((PROJECTS / "bridge" / "concrete-arch-bridge.json").read_text())

    def solve(parameters):
        count, diameter = parameters
        key = f"{count}-{diameter}"
        hangers = {**case["hangers"], "count_per_side": count, "diameter_mm": diameter}
        variant = {**case, "hangers": hangers}
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"bridge-{key}.json"
            path.write_text(json.dumps(variant))
            run_variant(path, "bridge", key, plans_only)
            if plans_only:
                return key, None
            stem = str(path.with_suffix(""))
            result, intact_hangers = bridge_result(stem + "-displacements.vtu", variant)
            loss_path = path.with_name("hanger-loss.vtu")
            solve_bridge(path.with_name("hanger-loss.msh"),loss_path,variant,remove_midspan_hanger=True)
            loss, remaining = bridge_result(loss_path,variant,removed=True)
            removed_hanger = (case["geometry"]["span_m"]/2,-case["geometry"]["deck_width_m"]/2)
            if set(intact_hangers)-set(remaining) != {removed_hanger}:
                raise ValueError("The damaged bridge must omit only the selected midspan hanger.")
            changes = {location: force-intact_hangers[location] for location,force in remaining.items()}
            loss.update(hanger_changes_kn=list(changes.values()),
                        removed_hanger_kn=intact_hangers[removed_hanger],
                        opposite_arch_change_kn=sum(value for (_,y),value in changes.items() if y > 0))
            if loss["points"] == result["points"]:
                del loss["points"]
            cad, masses = [], {}
            settings = {**case["structural_model"], "steel_density_kg_m3": hangers["density_kg_m3"]}
            for shape, name, _, _ in cq.Assembly.load(stem + "-model.step"):
                name = name.rsplit("/", 1)[-1]
                steel = name.startswith("Hanger_")
                add_mass(masses, shape, "Steel" if steel else "Concrete", settings)
                points, faces = shape.tessellate(0.5)
                cad.append({"material": "steel" if steel else "wall" if name.startswith("Abutment_") else "roof",
                            "points": [round(v/1000, 6) for point in points for v in point.toTuple()],
                            "faces": faces})
            print("bridge", key, result["deck_mm"], result["hanger_kn"], "hanger loss", loss["edge_difference_mm"], max(changes.values()), flush=True)
            return key, {"cad": cad, "result": result, "loss": loss, "material_masses_kg": masses,
                         "geometry": case["geometry"]}

    with ThreadPoolExecutor(max_workers=2) as workers:
        variants = dict(workers.map(solve, product((5, 9), (24, 40))))
    if not plans_only:
        (WEBSITE / "bridge-cases.js").write_text(
            "window.bridgeCases = " + json.dumps(variants, separators=(",", ":"), allow_nan=False) + ";\n",
            encoding="utf-8",
        )

def extension_result(path, case):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    mesh = reader.GetOutput()
    points = vtk_to_numpy(mesh.GetPoints().GetData())
    movement = vtk_to_numpy(mesh.GetPointData().GetArray("displacement"))
    g, settings = case["geometry"], case["structural_model"]
    faces, reactions = [], []
    area = g["wall_thickness_m"] * g["wall_effective_width_m"]
    for index in range(mesh.GetNumberOfCells()):
        cell = mesh.GetCell(index)
        ids = [cell.GetPointId(i) for i in range(cell.GetNumberOfPoints())]
        if cell.GetCellType() == 9:
            faces.append(ids)
        elif cell.GetCellType() == 3:
            a, b = sorted(ids, key=lambda i: points[i, 2])
            if not np.allclose(movement[a], 0):
                raise ValueError("The equivalent wall base must be fixed.")
            length = points[b, 2] - points[a, 2]
            force = settings["wall_modulus_pa"] * area * (movement[a, 2]-movement[b, 2]) / length
            reactions.append((float(points[a, 0]), float(force / 1000)))
    reactions = [force for _, force in sorted(reactions)]
    flange = g["flange_thickness_m"]
    steel_area = 2*flange*g["flange_width_m"] + (g["beam_depth_m"]-flange)*g["web_thickness_m"]
    weight = steel_area * (g["span_m"]+g["wall_thickness_m"]) * settings["density_kg_m3"] * settings["gravity_m_s2"]
    expected_kn = case["loads"]["column_force_kn"] + weight/1000
    if not (faces and np.isfinite(movement).all() and len(reactions) == 2
            and isclose(sum(reactions), expected_kn, rel_tol=0.002)):
        raise ValueError(f"Invalid extension solution or out-of-balance wall reactions: {reactions} vs {expected_kn:.2f} kN.")
    sample = np.isclose(points[:, 0], g["column_offset_m"]) & np.isclose(points[:, 1], 0)
    sample &= np.isclose(points[:, 2], g["beam_depth_m"]-flange/2)
    if np.count_nonzero(sample) != 1:
        raise ValueError("Expected one node at the column seat.")
    return {
        "points": points.round(6).ravel().tolist(),
        "displacement": (1000 * movement).round(5).ravel().tolist(),
        "faces": faces,
        "front_mm": float(1000 * np.abs(movement[:, 2]).max()),
        "seat_mm": float(-1000 * movement[sample, 2][0]),
        "wall_reactions_kn": reactions,
    }

def build_extension(plans_only):
    case = json.loads((PROJECTS / "extension" / "roof-extension.json").read_text())

    def solve(parameters):
        offset, depth = parameters
        key = f"{offset}-{depth}"
        geometry = {**case["geometry"], "column_offset_m": offset/100, "beam_depth_m": depth/1000}
        variant = {**case, "geometry": geometry}
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"roof-extension-{key}.json"
            path.write_text(json.dumps(variant))
            run_variant(path, "extension", key, plans_only)
            if plans_only:
                return key, None
            stem = str(path.with_suffix(""))
            result = extension_result(stem + "-displacements.vtu", variant)
            cad, masses = [], {}
            settings = {"steel_density_kg_m3": case["structural_model"]["density_kg_m3"]}
            for shape, name, _, _ in cq.Assembly.load(stem + "-model.step"):
                name = name.rsplit("/", 1)[-1]
                if name.startswith("Upper_"):
                    material = "timber"
                elif name.endswith("_wall"):
                    material = "wall"
                else:
                    material = "steel"
                    add_mass(masses, shape, "Steel", settings)
                points, faces = shape.tessellate(0.5)
                cad.append({"material": material,
                            "points": [round(v/1000, 6) for point in points for v in point.toTuple()],
                            "faces": faces})
            print("extension", key, result["seat_mm"], result["wall_reactions_kn"], flush=True)
            return key, {"cad": cad, "result": result, "material_masses_kg": masses, "geometry": geometry,
                         "column_force_kn": case["loads"]["column_force_kn"]}

    with ThreadPoolExecutor(max_workers=2) as workers:
        variants = dict(workers.map(solve, product((150, 300), (450, 650))))
    if not plans_only:
        sys.path.insert(0, str(ROOT))
        from projects.extension.model import draw_comparison

        draw_comparison(WEBSITE / "plans" / "extension" / "comparison.svg", variants)
        (WEBSITE / "extension-cases.js").write_text(
            "window.extensionCases = " + json.dumps(variants, separators=(",", ":"), allow_nan=False) + ";\n",
            encoding="utf-8",
        )

def extension_detail_result(path, case):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    mesh = reader.GetOutput()
    points = vtk_to_numpy(mesh.GetPoints().GetData())
    movement = vtk_to_numpy(mesh.GetPointData().GetArray("displacement"))
    if not np.isfinite(movement).all():
        raise ValueError("Invalid transfer beam detail displacement.")
    g, material = case["geometry"], case["structural_model"]
    seat = g["column_offset_m"]
    young, poisson = material["young_modulus_pa"], material["poisson_ratio"]
    used, faces, stress = set(), {"web": [], "flanges": [], "plate": [], "stiffeners": []}, []
    for i in range(mesh.GetNumberOfCells()):
        cell = mesh.GetCell(i)
        if cell.GetCellType() != 9:
            continue
        ids = [cell.GetPointId(j) for j in range(4)]
        x, y, z = points[ids].T
        if np.max(np.abs(x-seat)) > .551:
            continue
        if np.ptp(z) < 1e-8:
            loaded = z[0] > g["beam_depth_m"]/2 and np.max(np.abs(x-seat)) <= g["column_side_m"]/2+1e-8
            group = "plate" if loaded else "flanges"
        elif np.ptp(y) < 1e-8:
            group = "web"
            def strain(position, translation):
                mid = (min(position)+max(position))/2
                return (translation[position > mid].mean()-translation[position < mid].mean())/np.ptp(position)
            eps_x = strain(x, movement[ids, 0])
            eps_z = strain(z, movement[ids, 2])
            stress.append(float(-young/(1-poisson**2)*(eps_z+poisson*eps_x)/1e6))
        else:
            group = "stiffeners"
        faces[group].append(ids)
        used.update(ids)

    def displacement_at(z):
        sample = np.all(np.isclose(points,(seat,0,z),atol=1e-8,rtol=0),axis=1)
        if np.count_nonzero(sample) != 1:
            raise ValueError("Expected a single node at the flange centre.")
        return float(movement[sample,2][0])

    half = g["flange_thickness_m"]/2
    used = sorted(used)
    local = {node: i for i,node in enumerate(used)}
    return {
        "points": points[used].round(6).ravel().tolist(),
        "faces": {kind: [[local[node] for node in face] for face in group] for kind,group in faces.items()},
        "stress_mpa": [round(value, 4) for value in stress],
        "compression_mpa": float(max(stress)),
        "shortening_mm": 1000*(displacement_at(half)-displacement_at(g["beam_depth_m"]-half)),
    }

def build_extension_details():
    sys.path.insert(0, str(ROOT))
    from projects.extension.model import solve_extension

    case = json.loads((PROJECTS / "extension" / "roof-extension.json").read_text())
    case["geometry"].update(column_offset_m=1.5,beam_depth_m=.45)
    details = {}
    with TemporaryDirectory() as directory:
        for name, stiffened in (("plain",False),("stiffened",True)):
            mesh = Path(directory) / f"{name}.msh"
            result = Path(directory) / f"{name}.vtu"
            solve_extension(mesh,result,case,local=True,stiffened=stiffened)
            details[name] = extension_detail_result(result,case)
            print("extension detail",name,details[name]["compression_mpa"],details[name]["shortening_mm"],flush=True)
    package = {"cases": details, "geometry": case["geometry"], "connection": case["connection"],
               "column_force_kn": case["loads"]["column_force_kn"]}
    (WEBSITE / "extension-details.js").write_text(
        "window.extensionDetails = " + json.dumps(package,separators=(",",":"),allow_nan=False) + ";\n",
        encoding="utf-8",
    )

def build_brutalist(plans_only):
    sys.path.insert(0, str(ROOT))
    from projects.brutalist.model import STATIONS, draw_case, housing_view_geometry, housing_mesh
    from projects.brutalist.optimize import optimize_housing
    case = json.loads((PROJECTS/"brutalist"/"brutalist-housing.json").read_text())
    plans = WEBSITE/"plans"/"brutalist"
    plans.mkdir(parents=True,exist_ok=True)
    dataset = WEBSITE/"brutalist-cases.js"
    cached = {}
    if plans_only and dataset.is_file():
        payload = dataset.read_text(encoding="utf-8").split(" = ",1)[1].strip().removesuffix(";")
        cached = json.loads(payload)["variants"]
    variants = {}
    for count in STATIONS:
        study = {**case,"geometry":{**case["geometry"],"storeys":count}}
        if plans_only:
            draw_case(plans/f"{count}-uniform",study)
            if (optimized := cached.get(f"{count}-optimized")) is not None:
                draw_case(plans/f"{count}-optimized",study,design=optimized["result"]["thickness_m"])
            continue
        print(f"brutalist {count} storeys: starting thickness study",flush=True)
        study_result = optimize_housing(study)
        nodes,cells,_ = housing_mesh(study)
        for name in ("uniform","optimized"):
            design = study_result[name]
            draw_case(plans/f"{count}-{name}",study,design=design["thickness_m"])
            cad = housing_view_geometry(study,design["thickness_m"])
            result = {**design,"points":[v for xyz in nodes for v in xyz],
                      "faces":[[node-1 for node in cell[1:]] for cell in cells],
                      "front_mm":max(abs(v) for v in design["displacement"][1::3])}
            variants[f"{count}-{name}"] = {"cad":cad,"result":result,"study":{k:v for k,v in study_result.items()
                        if k not in ("uniform","optimized")},"uniform_volume_m3":study_result["uniform"]["volume_m3"],
                        "optimized_volume_m3":study_result["optimized"]["volume_m3"]}
        print(f"brutalist {count} storeys: {study_result['optimized']['thickness_m']} "
              f"({study_result['evaluations']} evaluations)",flush=True)
    if plans_only:
        return
    package = {"variants":variants,
               "wind_pressure_pa":case["loads"]["wind_pressure_pa"],
               "storey_height_m":case["geometry"]["storey_height_m"],
               "slab_thickness_m":case["geometry"]["slab_thickness_m"]}
    dataset.write_text(
        "window.brutalistCases = "+json.dumps(package,separators=(",",":"),allow_nan=False)+";\n",encoding="utf-8")

def build_terrace(plans_only):
    sys.path.insert(0, str(ROOT))
    from projects.terrace.model import STEEL_DENSITY, railing_mass, strip_pressure, write_cracking_map

    baseline = json.loads((PROJECTS/"terrace"/"concrete-terrace.json").read_text())
    plans = WEBSITE/"plans"/"terrace"
    plans.mkdir(parents=True,exist_ok=True)
    variants = {}
    for radius, steel in product((2.5,3.5,4.5),(1400,2400)):
        key = f"{radius:g}-{steel}"
        geometry = {**baseline["geometry"],"radius_m":radius}
        case = {**baseline,"geometry":geometry,
                "reinforcement":{**baseline["reinforcement"],"top_area_mm2_per_m":steel}}
        write_cracking_map(plans/f"{key}-cracking.svg",case)
        with TemporaryDirectory() as directory:
            path = Path(directory)/"concrete-terrace.json"
            path.write_text(json.dumps(case))
            run_variant(path,"terrace",key,plans_only)
            if plans_only:
                continue
            stem = path.with_suffix("")
            reader = vtkXMLUnstructuredGridReader()
            reader.SetFileName(str(stem.with_name(stem.name+"-displacements.vtu")))
            reader.Update()
            mesh = reader.GetOutput()
            nodes = vtk_to_numpy(mesh.GetPoints().GetData())
            data = mesh.GetPointData()
            movement = np.column_stack([vtk_to_numpy(data.GetArray(f"deflection {i}")) for i in (1,2,3)])
            edge = np.isclose(np.hypot(nodes[:,0],nodes[:,1]),radius,rtol=0,atol=1e-5)
            root = np.isclose(nodes[:,1],0)
            if not edge.any() or not np.isfinite(movement).all() or np.max(np.abs(movement[root])) > 1e-8:
                raise ValueError("Invalid terrace displacements or fixed-edge condition.")
            peak = float(-1000*movement[edge,2].min())
            if peak <= 0:
                raise ValueError("The loaded terrace edge must deflect downward.")
            faces = []
            for i in range(mesh.GetNumberOfCells()):
                if mesh.GetCellType(i) == 5:
                    cell = mesh.GetCell(i)
                    faces.append([cell.GetPointId(j) for j in range(3)])
            triangles = nodes[np.asarray(faces)]
            area = np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1).sum()/2
            rail_mass = railing_mass(case)
            expected_force = area*strip_pressure(case)+rail_mass*case["structural_model"]["gravity_m_s2"]
            reactions = vtk_to_numpy(data.GetArray("deflection loads 3"))
            if not isclose(float(reactions[root].sum()),expected_force,rel_tol=.0005):
                raise ValueError(f"Balcony reaction {reactions[root].sum():.1f} N differs from applied load {expected_force:.1f} N.")
            edge_nodes = np.flatnonzero(edge)
            angles = np.arctan2(nodes[edge_nodes,1],nodes[edge_nodes,0])
            order = np.argsort(angles)
            angles,edge_nodes = angles[order],edge_nodes[order]
            cad, masses = [], {}
            for shape, name, _, _ in cq.Assembly.load(str(stem.with_name(stem.name+"-model.step"))):
                name = name.rsplit("/",1)[-1]
                material = {"Support_context":"wall","Door_context":"hyparDoor","Terrace_slab":"roof"}.get(name,"steel")
                points, triangles = shape.tessellate(.5)
                coords = np.asarray([p.toTuple() for p in points])/1000
                part = {"material":material,"points":coords.round(6).ravel().tolist(),"faces":triangles}
                if material == "steel":
                    angle = np.arctan2(coords[:,1],coords[:,0])
                    high = np.searchsorted(angles,angle).clip(1,len(angles)-1)
                    low = high-1
                    weight = ((angle-angles[low])/(angles[high]-angles[low])).clip(0,1)
                    part["attachment"] = np.column_stack((edge_nodes[low],edge_nodes[high],weight.round(5))).tolist()
                if material == "roof":
                    add_mass(masses,shape,"Concrete",case["structural_model"])
                cad.append(part)
            masses["Steel railing"] = rail_mass
            masses["Top reinforcement"] = pi*radius**2/2*steel*1e-6*STEEL_DENSITY
            variants[key] = {"cad":cad,"geometry":geometry,"material_masses_kg":masses,"result":{
                "points":nodes.round(6).ravel().tolist(),"faces":faces,
                "displacement":(1000*movement).round(5).ravel().tolist(),"front_mm":peak}}
            print("terrace",key,f"{peak:.3f} mm",flush=True)
    if not plans_only:
        (WEBSITE/"terrace-cases.js").write_text(
            "window.terraceCases = "+json.dumps(variants,separators=(",",":"),allow_nan=False)+";\n",encoding="utf-8")

def build_atrium(plans_only):
    sys.path.insert(0,str(ROOT))
    from projects.atrium.model import run_case, draw_case

    baseline = json.loads((PROJECTS/"atrium"/"atrium-walkway.json").read_text())
    plans = WEBSITE/"plans"/"atrium"
    plans.mkdir(parents=True,exist_ok=True)

    def build(pair):
        station, depth = pair
        key = f"{station}-{depth}"
        case = {**baseline,"geometry":{**baseline["geometry"],"deck_depth_m":depth/100},
                "hanger":{**baseline["hanger"],"station":station/100}}
        if plans_only:
            draw_case(plans/key,case)
            return key,None
        with TemporaryDirectory() as directory:
            stem = Path(directory)/"walkway"
            step = stem.with_suffix(".step")
            result = run_case(plans/key,step,stem.with_suffix(".msh"),stem.with_suffix(".vtu"),case)
            cad = []
            nodes = np.asarray(result["points"]).reshape(-1,3)
            top = np.flatnonzero(np.isclose(nodes[:,2],case["geometry"]["deck_depth_m"]/2))
            for shape,name,_,_ in cq.Assembly.load(str(step)):
                name = name.rsplit("/",1)[-1]
                points,faces = shape.tessellate(.5)
                coords = np.asarray([p.toTuple() for p in points])/1000
                material = ("glass" if name.startswith("Guard_glass") else
                            "steel" if name.startswith(("Guard_","Hanger")) else
                            "wall" if name.startswith("Landing_") else "roof")
                part = {"material":material,"points":coords.round(6).ravel().tolist(),"faces":faces}
                if material == "glass":
                    part["opacity"] = .28
                if name.startswith("Guard_"):
                    radial = np.arctan2(coords[:,0],coords[:,1]+case["geometry"]["radius_m"])
                    surface = (np.hypot(coords[:,0],coords[:,1]+case["geometry"]["radius_m"]).mean()
                               > case["geometry"]["radius_m"])
                    edge = top[np.isclose(np.hypot(nodes[top,0],nodes[top,1]+case["geometry"]["radius_m"]),
                                          case["geometry"]["radius_m"]+(.5 if surface else -.5)*case["geometry"]["width_m"],atol=.01)]
                    angles = np.arctan2(nodes[edge,0],nodes[edge,1]+case["geometry"]["radius_m"])
                    order = np.argsort(angles)
                    angles,edge = angles[order],edge[order]
                    high = np.searchsorted(angles,radial).clip(1,len(angles)-1)
                    low = high-1
                    weight = ((radial-angles[low])/(angles[high]-angles[low])).clip(0,1)
                    part["attachment"] = np.column_stack((edge[low],edge[high],weight.round(5))).tolist()
                elif name == "Hanger_socket":
                    part["socket"] = True
                part["fixed"] = name.startswith("Landing_") or name == "Hanger_head"
                cad.append(part)
            peak = result["peaks"][0]
            print(f"atrium {key}: {peak['frequency']:.2f} Hz, {peak['acceleration']:.4f} m/s²",flush=True)
            return key,{"cad":cad,"result":result}

    with ThreadPoolExecutor(max_workers=4) as workers:
        variants = dict(workers.map(build,product((33,50),(18,26))))
    if not plans_only:
        (WEBSITE/"atrium-cases.js").write_text(
            "window.atriumCases = "+json.dumps(variants,separators=(",",":"),allow_nan=False)+";\n",encoding="utf-8")

def build_cabin(plans_only):
    sys.path.insert(0,str(ROOT))
    from projects.cabin.model import draw_case,run_case

    baseline = json.loads((PROJECTS/"cabin"/"thermal-cabin.json").read_text())
    plans = WEBSITE/"plans"/"cabin"
    plans.mkdir(parents=True,exist_ok=True)
    variants = {}
    for facade,shade in product(("south","west"),("open","shaded")):
        key = f"{facade}-{shade}"
        case = {**baseline,"windows":{**baseline["windows"],"main_facade":facade,"shaded":shade == "shaded"}}
        if plans_only:
            draw_case(plans/key,case)
            continue
        with TemporaryDirectory() as directory:
            stem = Path(directory)/"cabin"
            step = stem.with_suffix(".step")
            frames = run_case(plans/key,step,stem.with_suffix(".msh"),stem.with_suffix(".vtu"),case)
            if len(frames) != 73 or not all(15 < frame["air"] < 55 for frame in frames):
                raise ValueError("Cabin thermal history is incomplete or outside the study range.")
            cad = []
            for shape,name,_,_ in cq.Assembly.load(str(step)):
                name = name.rsplit("/",1)[-1]
                surface = name[5:] if name.startswith("Wall_") else name.lower() if name in ("Roof","Floor") else None
                material = ("glass" if name.startswith("Window_") else
                            "timber" if name.startswith(("Frame_","Shade_")) else "wall")
                points,faces = shape.tessellate(.5)
                cad.append({"material":material,"surface":surface,"points":[round(v/1000,6) for p in points for v in p.toTuple()],
                            "faces":faces,"opacity":.55 if material == "glass" else 1})
            peak = max(frames,key=lambda frame:frame["air"])
            variants[key] = {"cad":cad,"frames":frames,"peak":peak}
            print(f"cabin {key}: {peak['air']:.2f} °C at hour {peak['hour']}",flush=True)
    if not plans_only:
        (WEBSITE/"cabin-cases.js").write_text(
            "window.cabinCases = "+json.dumps(variants,separators=(",",":"),allow_nan=False)+";\n",encoding="utf-8")

def study_geometry(path):
    parts = []
    for shape,name,_,_ in cq.Assembly.load(str(path)):
        material = name.rsplit("/",1)[-1].rsplit("_",1)[0]
        points,faces = shape.tessellate(.5)
        if faces:
            parts.append({"material":material,"points":[round(v/1000,7) for p in points for v in p.toTuple()],
                              "faces":faces})
        else:
            edges = [edge.Vertices() for edge in shape.Edges()]
            if edges:
                parts.append({"material":material,
                                  "points":[round(v/1000,7) for edge in edges for p in edge for v in p.toTuple()],
                                  "faces":[[2*i,2*i+1] for i in range(len(edges))]})
    return parts

def study_payload(project,config,case):
    sys.path.insert(0,str(ROOT))
    def artifact(suffix):
        return config.with_name(config.stem+suffix)
    cad = study_geometry(artifact("-model.step"))
    if project == "auditorium":
        from projects.auditorium.model import geometry

        result = json.loads(artifact("-acoustic-results.json").read_text())
        roof,rear = case["roof"],case["treatment"]
        room = geometry(case,roof,rear)
        result["parts"] = geometry(case,roof,rear,result["paths"])[len(room):]
        result["audio_mp3"] = b64encode(artifact("-speech.mp3").read_bytes()).decode("ascii")
        return {"cad":cad,"result":result}
    result = json.loads(artifact("-study-results.json").read_text())
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(artifact("-displacements.vtu")))
    reader.Update()
    grid = reader.GetOutput()
    points = vtk_to_numpy(grid.GetPoints().GetData())
    displacement = vtk_to_numpy(grid.GetPointData().GetVectors())
    if project == "facade":
        from projects.facade.model import parts

        result["parts"] = parts(case,case["gallery_width_m"],case["stage"],points[:,0],-displacement[:,2])
    elif project == "vierendeel":
        from projects.vierendeel.model import frame,geometry

        nodes,members = frame(case,case["bay_width_m"])
        result["parts"] = geometry(case,nodes,members,dict(zip(nodes,displacement,strict=True)))
    else:
        from projects.slab.model import visualise

        cells = vtk_to_numpy(grid.GetCells().GetConnectivityArray()).reshape(-1,8)
        result.update(visualise(case,case["opening"],points,cells,displacement.ravel())["result"])
    return {"cad":cad,"result":result}

def build_study(project,config_name,variable,options,plans_only):
    baseline = json.loads((PROJECTS/project/config_name).read_text(encoding="utf-8"))
    variants = {}
    with TemporaryDirectory() as directory:
        for key,overrides in options:
            config = Path(directory)/f"{key}.json"
            case = {**baseline,**overrides}
            config.write_text(json.dumps(case),encoding="utf-8")
            run_variant(config,project,key,plans_only)
            if not plans_only:
                variants[key] = study_payload(project,config,case)
    if not plans_only:
        (WEBSITE/f"{project}-cases.js").write_text(
            f"window.{variable} = "+json.dumps(variants,separators=(",",":"),allow_nan=False)+";\n",
            encoding="utf-8")

def build_facade(plans_only):
    options = ((f"{width:g}-{stage}",{"gallery_width_m":width,"stage":stage})
               for width,stage in product((4,7),("existing","underpinning","excavation","permanent")))
    build_study("facade","historic-facade.json","facadeCases",options,plans_only)

def build_auditorium(plans_only):
    options = ((f"{roof}-{treatment}-{row}",{"roof":roof,"treatment":treatment,"row":row})
               for roof,treatment,row in product(("flat","folded"),("reflective","absorptive"),
                                                 ("front","middle","back")))
    build_study("auditorium","auditorium.json","auditoriumCases",options,plans_only)

def build_vierendeel(plans_only):
    options = ((f"{width:g}-{joint}",{"bay_width_m":width,"joint":joint})
               for width,joint in product((3,4),("rigid","flexible")))
    build_study("vierendeel","cantilever-building.json","vierendeelCases",options,plans_only)

def build_slab(plans_only):
    options = ((variant,{"opening":variant}) for variant in ("none","near","far"))
    build_study("slab","slab-opening.json","slabCases",options,plans_only)

def main():
    parser = argparse.ArgumentParser(description="Precompute the configurations used by the static viewer.")
    parser.add_argument("project", nargs="?", choices=("shelter", "gable", "observatory", "house", "canopy", "hypar", "bridge", "extension", "brutalist", "terrace", "atrium", "cabin", "facade", "auditorium", "vierendeel", "slab"))
    parser.add_argument("--plans-only", action="store_true", help="Export SVG drawings without running Elmer.")
    args = parser.parse_args()
    for model in ((args.project,) if args.project else ("shelter", "gable", "observatory", "house", "canopy", "hypar", "bridge", "extension", "brutalist", "terrace", "atrium", "cabin", "facade", "auditorium", "vierendeel", "slab")):
        if model == "slab":
            build_slab(args.plans_only)
        elif model == "vierendeel":
            build_vierendeel(args.plans_only)
        elif model == "auditorium":
            build_auditorium(args.plans_only)
        elif model == "facade":
            build_facade(args.plans_only)
        elif model == "cabin":
            build_cabin(args.plans_only)
        elif model == "atrium":
            build_atrium(args.plans_only)
        elif model == "terrace":
            build_terrace(args.plans_only)
        elif model == "brutalist":
            build_brutalist(args.plans_only)
        elif model == "observatory":
            build_observatory(args.plans_only)
        elif model == "house":
            build_house(args.plans_only)
        elif model == "extension":
            build_extension(args.plans_only)
            if not args.plans_only:
                build_extension_details()
        elif model == "bridge":
            build_bridge(args.plans_only)
        elif model == "hypar":
            build_hypar(args.plans_only)
        elif model == "canopy":
            build_canopy(args.plans_only)
        elif model == "gable":
            build_gable(args.plans_only)
        else:
            build_shelter(args.plans_only)

if __name__ == "__main__":
    main()
