from math import ceil, hypot, isfinite
from pathlib import Path

import cadquery as cq
import gmsh

from common.cad import export_step
from common.shell_solver import solve_shell_structure
from .drawings import draw_concrete_plans
from .geometry import build_concrete_geometry

def build_concrete_cad_model(geometry: dict) -> cq.Assembly:
    model = cq.Assembly(name="Concrete_shelter")
    concrete = cq.Color(0.71, 0.70, 0.66)
    parts = {"Roof": geometry["roof"]}
    for side, bounds in geometry["walls"].items():
        parts[f"Wall_{side}"] = bounds

    def box(bounds):
        x0, y0, z0 = bounds["min"]
        x1, y1, z1 = bounds["max"]
        return cq.Workplane("XY", origin=(1000 * x0, 1000 * y0, 1000 * z0)).box(
            1000 * (x1 - x0),
            1000 * (y1 - y0),
            1000 * (z1 - z0),
            centered=(False, False, False),
        )
    window = geometry.get("rear_window")
    for name, bounds in parts.items():
        solid = box(bounds)
        if name == "Wall_rear" and window is not None:
            solid = solid.cut(box(window))
        model.add(solid, name=name, color=concrete)

    if window is not None:
        x0, y0, z0 = window["min"]
        x1, y1, z1 = window["max"]
        glass_y = (y0 + y1) / 2
        glass = box({"min": (x0, glass_y - .006, z0), "max": (x1, glass_y + .006, z1)})
        model.add(glass, name="Rear_glass", color=cq.Color(0.39, 0.72, 0.77, 0.35))

    return model

def generate_shell_mesh(geometry: dict, mesh_path: Path, size_m: float) -> None:
    if not isfinite(size_m) or size_m <= 0:
        raise ValueError("Shell mesh element size must be positive and finite.")
    walls = geometry["walls"]
    roof = geometry["roof"]
    left = walls["left"]["max"][0] / 2
    right = (walls["right"]["min"][0] + walls["right"]["max"][0]) / 2
    rear = (walls["rear"]["min"][1] + walls["rear"]["max"][1]) / 2
    top = (roof["min"][2] + roof["max"][2]) / 2

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("shelter_shell")
        geo = gmsh.model.geo
        def edge(a, b, length):
            tag = geo.addLine(a, b)
            geo.mesh.setTransfiniteCurve(tag, ceil(length / size_m) + 1)
            return tag

        def face(edges):
            tag = geo.addPlaneSurface([geo.addCurveLoop(edges)])
            geo.mesh.setTransfiniteSurface(tag)
            geo.mesh.setRecombine(2, tag)
            return tag

        window = geometry.get("rear_window")
        if window is None:
            bottom = [geo.addPoint(x, y, 0) for x, y in
                      ((left, 0), (right, 0), (right, rear), (left, rear))]
            upper = [geo.addPoint(x, y, top) for x, y in
                     ((left, 0), (right, 0), (right, rear), (left, rear))]
            spans = (right - left, rear, right - left, rear)

            top_edges = [edge(upper[i], upper[(i + 1) % 4], spans[i]) for i in range(4)]
            uprights = [edge(bottom[i], upper[i], top) for i in range(4)]
            base_edges, wall_faces = [], []
            for i in (1, 2, 3):
                j = (i + 1) % 4
                base = edge(bottom[i], bottom[j], spans[i])
                base_edges.append(base)
                wall_faces.append(face([base, uprights[j], -top_edges[i], -uprights[i]]))
            roof_faces = [face(top_edges)]
        else:
            x0, _, sill = window["min"]
            x1 = window["max"][0]
            xs = (left, x0, x1, right)
            points = {}
            edges = {}

            def shared_edge(a, b):
                for point in (a, b):
                    if point not in points:
                        points[point] = geo.addPoint(*point)
                if (b, a) in edges:
                    return -edges[b, a]
                if (a, b) not in edges:
                    length = hypot(*(v - u for u, v in zip(a, b, strict=True)))
                    edges[a, b] = edge(points[a], points[b], length)
                return edges[a, b]

            def panel(a, b, c, d):
                return face([shared_edge(a, b), shared_edge(b, c),
                             shared_edge(c, d), shared_edge(d, a)])

            roof_faces, wall_faces, base_edges = [], [], []
            for i, (a, b) in enumerate(zip(xs[:-1], xs[1:], strict=True)):
                roof_faces.append(panel((a, 0, top), (b, 0, top), (b, rear, top), (a, rear, top)))
                base_edges.append(shared_edge((b, rear, 0), (a, rear, 0)))
                wall_faces.append(panel((b, rear, 0), (a, rear, 0), (a, rear, sill), (b, rear, sill)))
                if i != 1:
                    wall_faces.append(panel((b, rear, sill), (a, rear, sill),
                                            (a, rear, top), (b, rear, top)))
            for x, start_y, end_y in ((right, 0, rear), (left, rear, 0)):
                base_edges.append(shared_edge((x, start_y, 0), (x, end_y, 0)))
                for za, zb in ((0, sill), (sill, top)):
                    wall_faces.append(panel((x, start_y, za), (x, end_y, za),
                                            (x, end_y, zb), (x, start_y, zb)))
        geo.synchronize()
        gmsh.model.addPhysicalGroup(2, roof_faces, 1, "roof")
        gmsh.model.addPhysicalGroup(2, wall_faces, 2, "walls")
        gmsh.model.addPhysicalGroup(1, base_edges, 3, "wall_bases")
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(2)
        gmsh.write(str(mesh_path))
    finally:
        gmsh.finalize()

def draw_case(stem, case):
    draw_concrete_plans(build_concrete_geometry(case["geometry"]), stem)

def run_case(stem, step, mesh, result, case):
    dimensions = case["geometry"]
    geometry = build_concrete_geometry(dimensions)
    draw_concrete_plans(geometry, stem)
    export_step(build_concrete_cad_model(geometry), step)
    generate_shell_mesh(geometry, mesh, case["mesh"]["element_size_m"])
    pressure = case.get("loads", {}).get("roof_pressure_pa", 0.0)
    solve_shell_structure(mesh, result, case["structural_model"],
                          dimensions["roof_thickness_m"], dimensions["wall_thickness_m"], pressure,
                          calculate_loads=True)
