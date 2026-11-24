from itertools import combinations
from math import cos, radians, sin
from pathlib import Path
from xml.etree import ElementTree as ET
import subprocess
from tempfile import TemporaryDirectory

import gmsh
import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader

from common.elmer import elmer_runtime

LUG_WIDTH = 0.034
LUG_HEIGHT = 0.048
PIN_OFFSET = 0.065

def bolt_centres(g):
    rows = (g["bolt_half_height_m"], -g["bolt_half_height_m"])
    if g["bolts"] == 6:
        rows = (rows[0], 0, rows[1])
    return [(x, z) for z in rows for x in (-g["bolt_half_span_m"], g["bolt_half_span_m"])]

def mesh_solids(g, mesh):
    w, h, t = (g[f"plate_{key}_m"] for key in ("width", "height", "thickness"))
    edge_z = g["bolt_half_height_m"] + g["edge_distance_m"]
    wall_t = g["wall_thickness_m"]
    radius = g["anchor_diameter_m"] / 2
    embedment = g["embedment_m"]
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("canopy_anchor")
        occ = gmsh.model.occ
        concrete = occ.addBox(-.34, -wall_t, -.36, .68, wall_t, .36 + edge_z)
        plate = occ.addBox(-w/2, 0, -h/2, w, t, h)
        lug = occ.addBox(-LUG_WIDTH/2, t, -LUG_HEIGHT/2, LUG_WIDTH, PIN_OFFSET-t, LUG_HEIGHT)
        steel, _ = occ.fuse([(3, plate)], [(3, lug)])
        rods = [(3, occ.addCylinder(x, -embedment, z, 0, embedment+t, 0, radius))
                for x, z in bolt_centres(g)]
        _, mapping = occ.fragment([(3, concrete), *steel], rods)
        occ.synchronize()
        rod_volumes = {tag for copies in mapping[2:] for dim, tag in copies if dim == 3}
        groups = [{tag for dim, tag in copies if dim == 3} for copies in mapping]
        groups[0] -= rod_volumes
        groups[1] -= rod_volumes

        fine = mesh["bolt_size_m"]
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh["element_size_m"])
        gmsh.option.setNumber("Mesh.MeshSizeMin", fine * .75)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        near = set()
        for tag in groups[1] | rod_volumes:
            near.update(gmsh.model.getBoundary([(3, tag)], combined=False, recursive=True))
        gmsh.model.mesh.setSize(list(near), fine)
        gmsh.model.mesh.generate(3)

        node_ids, coordinates, _ = gmsh.model.mesh.getNodes()
        pts = coordinates.reshape(-1, 3).tolist()
        node_index = {int(tag): i for i, tag in enumerate(node_ids)}
        cells, bodies = [], []
        for i, volumes in enumerate(groups):
            body = (1, 2)[i] if i < 2 else 10 + i - 2
            for volume in sorted(volumes):
                kinds, _, connectivity = gmsh.model.mesh.getElements(3, volume)
                if list(kinds) != [4]:
                    raise ValueError("Expected linear tetrahedra in the anchor mesh.")
                for row in connectivity[0].reshape(-1, 4):
                    cells.append([node_index[int(j)] for j in row])
                    bodies.append(body)
    finally:
        gmsh.finalize()

    faces = {}
    for i, tet in enumerate(cells):
        for face in combinations(tet, 3):
            if all(abs(pts[j][1]) < 1e-9 for j in face):
                faces.setdefault(tuple(sorted(face)), []).append(i)
    interface = [(face, next(i for i in sides if bodies[i] == 1),
                   next(i for i in sides if bodies[i] == 2))
                 for face, sides in faces.items() if {bodies[i] for i in sides} == {1, 2}]
    if not interface:
        raise RuntimeError("The concrete and plate have no matching contact surface.")
    duplicates = {}
    for j in sorted({j for face, _, _ in interface for j in face}):
        duplicates[j] = len(pts)
        pts.append(pts[j].copy())

    boundaries = []
    contact_pairs = [(wall, plate) for plate, wall in duplicates.items()]
    for face, concrete_cell, plate_cell in interface:
        boundaries.append((3, concrete_cell, tuple(duplicates[j] for j in face)))
        boundaries.append((2, plate_cell, face))
    for i, tet in enumerate(cells):
        body = bodies[i]
        if body == 1:
            cells[i] = [duplicates.get(j, j) for j in tet]
        if body not in (1, 2):
            continue
        y = -wall_t if body == 1 else PIN_OFFSET
        for face in combinations(tet, 3):
            if all(abs(pts[j][1] - y) < 1e-9 for j in face):
                boundaries.append((1 if body == 1 else 4, i, face))
    if {tag for tag, _, _ in boundaries} != {1, 2, 3, 4}:
        raise RuntimeError("Missing anchor boundary group.")
    points = np.asarray(pts)
    tets = np.asarray(cells)
    body_ids = np.asarray(bodies)
    jac = points[tets[:, 1:]] - points[tets[:, :1]]
    for i in np.flatnonzero(np.linalg.det(jac) < 0):
        tets[i, [2, 3]] = tets[i, [3, 2]]
    oriented = []
    for tag, parent, face in boundaries:
        a,b,c = points[list(face)]
        other = next(j for j in tets[parent] if j not in face)
        if np.dot(np.cross(b-a, c-a), points[other]-a) > 0:
            face = (face[0], face[2], face[1])
        oriented.append((tag, parent, face))
    return points, tets, body_ids, oriented, contact_pairs

def row(*values):
    return " ".join(map(str, values))

def write_mesh(path, data):
    points, tets, bodies, boundaries, _ = data
    names = [(3, 1, "concrete"), (3, 2, "anchor_plate"), (2, 1, "fixed_back"),
             (2, 2, "plate_contact"), (2, 3, "wall_contact"), (2, 4, "pin_load")]
    names += [(3, int(body), f"bolt_{body-9}") for body in sorted(set(bodies)) if body >= 10]
    elements = [(4, body, tet) for body, tet in zip(bodies, tets, strict=True)]
    elements += [(2, tag, face) for tag, _, face in boundaries]
    path.write_text("\n".join([
        "$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$PhysicalNames", str(len(names)),
        *(row(dim, tag, f'"{name}"') for dim, tag, name in names),
        "$EndPhysicalNames", "$Nodes", str(len(points)),
        *(row(i, *xyz) for i, xyz in enumerate(points, 1)),
        "$EndNodes", "$Elements", str(len(elements)),
        *(row(i, kind, 2, tag, tag, *(j+1 for j in ids))
          for i, (kind, tag, ids) in enumerate(elements, 1)),
        "$EndElements", "",
    ]))

def write_elmer_mesh(directory, data):
    points, tets, bodies, boundaries, _ = data
    directory.mkdir()
    rows = {
        "header": [row(len(points), len(tets), len(boundaries)), "2",
                   row(303, len(boundaries)), row(504, len(tets))],
        "nodes": [row(i, -1, *xyz) for i, xyz in enumerate(points, 1)],
        "elements": [row(i, body, 504, *(j+1 for j in tet))
                     for i, (body, tet) in enumerate(zip(bodies, tets, strict=True), 1)],
        "boundary": [row(i, tag, parent+1, 0, 303, *(j+1 for j in face))
                     for i, (tag, parent, face) in enumerate(boundaries, 1)],
    }
    for name, content in rows.items():
        (directory / f"mesh.{name}").write_text("\n".join(content) + "\n")

def solve_anchor(result, case, data):
    settings = case["structural_model"]
    loads = case["loads"]
    angle = radians(loads["tie_angle_deg"])
    force = 1000 * loads["tie_force_kn"] * np.array([0, cos(angle), -sin(angle)])
    traction = force / (LUG_WIDTH * LUG_HEIGHT)
    steel = sorted(set(data[2]) - {1})
    sif = f"""Header
  CHECK KEYWORDS Warn
  Mesh DB "." "mesh"
End
Simulation
  Max Output Level = 5
  Coordinate System = Cartesian 3D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Vtu Save Bulk Only = Logical True
End
Body 1
  Target Bodies(1) = 1
  Equation = 1
  Material = 1
End
Body 2
  Target Bodies({len(steel)}) = {' '.join(map(str, steel))}
  Equation = 1
  Material = 2
End
Material 1
  Youngs Modulus = Real {settings["concrete_young_modulus_pa"]}
  Poisson Ratio = Real {settings["concrete_poisson_ratio"]}
End
Material 2
  Youngs Modulus = Real {settings["steel_young_modulus_pa"]}
  Poisson Ratio = Real {settings["steel_poisson_ratio"]}
End
Equation 1
  Active Solvers(2) = 1 2
End
Solver 1
  Equation = "Elasticity"
  Procedure = "ElasticSolve" "ElasticSolver"
  Variable = -dofs 3 Displacement
  Linear System Solver = Direct
  Linear System Direct Method = Mumps
  Linear System Residual Mode = Logical True
  Apply Contact BCs = Logical True
  Elasticity Solver Linear = Logical True
  Nonlinear System Max Iterations = 30
  Nonlinear System Convergence Tolerance = 1.0e-5
  Nonlinear System Abort Not Converged = Logical True
  Nonlinear System Convergence Without Constraints = Logical True
  Displace Mesh = Logical False
End
Solver 2
  Exec Solver = After Simulation
  Equation = "Result output"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "anchor"
  Vtu Format = Logical True
  Binary Output = Logical False
  Single Precision = Logical False
End
Boundary Condition 1
  Target Boundaries(1) = 1
  Displacement 1 = Real 0.0
  Displacement 2 = Real 0.0
  Displacement 3 = Real 0.0
End
Boundary Condition 2
  Target Boundaries(1) = 2
  Mortar BC = Integer 3
  Mortar BC Nonlinear = Logical True
  Slide Contact = Logical True
  Plane Projector = Logical True
  Galerkin Projector = Logical True
  Normal-Tangential Displacement = Logical True
  Mass Consistent Normals = Logical True
End
Boundary Condition 3
  Target Boundaries(1) = 3
  Normal-Tangential Displacement = Logical True
  Mass Consistent Normals = Logical True
End
Boundary Condition 4
  Target Boundaries(1) = 4
  Surface Traction 2 = Real {traction[1]}
  Surface Traction 3 = Real {traction[2]}
End
"""
    _, solver, env = elmer_runtime()
    with TemporaryDirectory(prefix=".elmer-", dir=result.parent) as tmp:
        work = Path(tmp).resolve()
        write_elmer_mesh(work / "mesh", data)
        (work / "anchor.sif").write_text(sif)
        run = subprocess.run([solver, "anchor.sif"], cwd=work, env=env, capture_output=True, text=True)
        files = list(work.rglob("anchor*.vtu"))
        if run.returncode or len(files) != 1:
            raise RuntimeError(run.stdout[-9000:] + run.stderr[-3500:])
        print("\n".join(line for line in run.stdout.splitlines()
                        if "ComputeChange:" in line or "Active set" in line)[-2000:])
        files[0].replace(result)
    return force

def read_solution(path, reference):
    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.Update()
    grid = reader.GetOutput()
    points = vtk_to_numpy(grid.GetPoints().GetData())
    if points.shape != reference.shape or not np.allclose(points, reference, atol=1e-8, rtol=0):
        raise RuntimeError("Elmer result must preserve the contact node numbering.")
    displacement = grid.GetPointData().GetArray("displacement")
    if displacement is None:
        raise RuntimeError("Elmer did not export the displacement vector.")
    moves = vtk_to_numpy(displacement)
    if not np.isfinite(moves).all() or not moves.any():
        raise RuntimeError("The anchor solution must have finite nonzero displacements.")
    return moves

def anchor_result(result, case, data, force):
    points, tets, bodies, boundaries, contact = data
    moves = read_solution(result, points)
    settings = case["structural_model"]
    x = points[tets]
    jac = x[:, 1:] - x[:, :1]
    grad = np.empty_like(x)
    grad[:, 1:] = np.linalg.inv(jac).transpose(0, 2, 1)
    grad[:, 0] = -grad[:, 1:].sum(axis=1)
    gradient = np.einsum("tni,tnj->tij", moves[tets], grad)
    strain = (gradient + gradient.transpose(0, 2, 1)) / 2
    young = np.where(bodies == 1, settings["concrete_young_modulus_pa"], settings["steel_young_modulus_pa"])
    nu = np.where(bodies == 1, settings["concrete_poisson_ratio"], settings["steel_poisson_ratio"])
    lam = young * nu / ((1 + nu) * (1 - 2 * nu))
    stress = young[:, None, None] / (1 + nu[:, None, None]) * strain
    stress += (lam * np.trace(strain, axis1=1, axis2=2))[:, None, None] * np.eye(3)
    forces = np.einsum("tij,tnj->tni", stress, grad) * (np.linalg.det(jac)/6)[:, None, None]
    fixed = np.isclose(x[:, :, 1], -case["geometry"]["wall_thickness_m"], atol=1e-9)
    reaction = forces[fixed].sum(axis=0)
    imbalance = float(np.linalg.norm(reaction + force) / np.linalg.norm(force))
    if imbalance > .01:
        raise RuntimeError(f"Anchor force balance failed: {imbalance:.2%}")
    bolts = []
    for body in sorted(set(bodies) - {1, 2}):
        embedded = (bodies == body) & (x[:, :, 1].mean(axis=1) < 0)
        cut = np.isclose(x[embedded, :, 1], 0, atol=1e-9)
        if not cut.any():
            raise RuntimeError("Missing bolt section at the face of concrete.")
        transfer = forces[embedded][cut].sum(axis=0) / 1000
        bolts.append({"id": int(body)-9, "axial_kn": round(float(transfer[1]), 3),
                      "shear_kn": round(float(np.hypot(transfer[0], transfer[2])), 3),
                      "vertical_kn": round(float(transfer[2]), 3)})
    vertical = sum(bolt["vertical_kn"] for bolt in bolts)
    if abs(vertical - force[2] / 1000) > .01 * abs(force[2]) / 1000:
        raise RuntimeError(f"Bolt shear does not balance the applied force: {vertical:g} kN")
    gap = np.array([moves[plate, 1] - moves[wall, 1] for wall, plate in contact])
    if gap.min() < -2e-5 or gap.max() <= 0:
        raise RuntimeError(f"Unexpected plate contact gap: {gap.min():g} to {gap.max():g} m")
    return {"opening_mm": round(1000*float(gap.max()), 4),
            "minimum_gap_mm": round(1000*float(gap.min()), 5),
            "max_displacement_mm": round(1000*float(np.linalg.norm(moves, axis=1).max()), 4),
            "imbalance_percent": round(imbalance*100, 4),
            "bolts": bolts}

def tag_result(path, data):
    _, tets, bodies, _, _ = data
    by_nodes = {tuple(sorted(tet)): body for tet, body in zip(tets, bodies, strict=True)}
    tree = ET.parse(path)
    piece = tree.find("./UnstructuredGrid/Piece")
    cells = piece.find("Cells")
    connectivity = np.fromstring(cells.find("DataArray[@Name='connectivity']").text, sep=" ", dtype=int)
    offsets = np.fromstring(cells.find("DataArray[@Name='offsets']").text, sep=" ", dtype=int)
    types = np.fromstring(cells.find("DataArray[@Name='types']").text, sep=" ", dtype=int)
    values = []
    for start, end, kind in zip([0, *offsets[:-1]], offsets, types, strict=True):
        values.append(str(by_nodes[tuple(sorted(connectivity[start:end]))]) if kind == 10 else "0")
    fields = piece.find("CellData")
    if fields is None:
        fields = ET.SubElement(piece, "CellData")
    value = ET.SubElement(fields, "DataArray", type="Int32", Name="anchor_body", format="ascii")
    value.text = " ".join(values)
    tree.write(path, encoding="utf-8", xml_declaration=True)
