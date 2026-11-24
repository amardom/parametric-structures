from itertools import pairwise
from math import ceil, isfinite

import cadquery as cq

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from common.shell_solver import SQUARE_COLUMN, solve_shell_structure
from common.elmer import add_displacement_vector

def stations(stops, size):
    values = sorted(set(stops))
    grid = [values[0]]
    for a, b in pairwise(values):
        n = ceil((b - a) / size)
        grid.extend(a + (b - a) * i / n for i in range(1, n))
        grid.append(b)
    return grid

def house_mesh(path, g, size):
    w, d, h = (g[key] for key in ("width_m", "depth_m", "storey_height_m"))
    inner = g["wall_thickness_m"] / 2
    setback = g["column_setback_m"]
    px, py = w - setback, d - setback
    xs = stations((inner, px, g["door_center_m"], w), size)
    ys = stations((inner, py, d), size)
    zs = stations((0, h, 2 * h), size)
    nodes, elements, fixed = {}, [], set()

    def element(kind, body, points):
        ids = [nodes.setdefault(p, len(nodes) + 1) for p in points]
        elements.append((kind, body, *ids))
        fixed.update(i for i, p in zip(ids, points, strict=True) if p[2] == 0)

    for top, body in ((h, 1), (2 * h, 4)):
        for a, b in pairwise(xs):
            for c, e in pairwise(ys):
                element(3, body, [(a,c,top), (b,c,top), (b,e,top), (a,e,top)])
    for z0, z1 in pairwise(zs):
        for a, b in pairwise(xs):
            element(3, 3, [(b,inner,z0), (a,inner,z0), (a,inner,z1), (b,inner,z1)])
        for a, b in pairwise(ys):
            element(3, 3, [(inner,a,z0), (inner,b,z0), (inner,b,z1), (inner,a,z1)])
        element(1, 2, [(px,py,z0), (px,py,z1)])

    cells = elements + [(15, 3, i) for i in sorted(fixed)]
    rows = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$PhysicalNames", "5",
            '2 1 "first_floor"', '1 2 "column"', '2 3 "concrete_walls"',
            '2 4 "roof"', '0 3 "fixed_base"', "$EndPhysicalNames", "$Nodes", str(len(nodes))]
    rows.extend(f"{i} {x} {y} {z}" for (x, y, z), i in nodes.items())
    rows.extend(("$EndNodes", "$Elements", str(len(cells))))
    rows.extend(" ".join(map(str, (i, kind, 2, group, kind * 10 + group, *ids)))
                for i, (kind, group, *ids) in enumerate(cells, 1))
    rows.extend(("$EndElements", ""))
    path.write_text("\n".join(rows))

def house_cad(g):
    w, d, h = (g[key] for key in ("width_m", "depth_m", "storey_height_m"))
    wall, floor, roof, glass = (g[f"{key}_thickness_m"] for key in ("wall", "floor", "roof", "glass"))
    side, setback = g["column_side_m"], g["column_setback_m"]
    cx, cy = w - setback, d - setback
    door_x = g["door_center_m"] - g["door_width_m"] / 2
    door_w, door_h = g["door_width_m"], g["door_height_m"]
    model = cq.Assembly(name="Glass_house")
    concrete = cq.Color(0.71, 0.69, 0.64)
    glazing = cq.Color(0.49, 0.74, 0.80, 0.35)

    def box(x, y, z, dx, dy, dz):
        origin = cq.Vector(*(1000 * v for v in (x, y, z)))
        return cq.Solid.makeBox(1000 * dx, 1000 * dy, 1000 * dz, origin)

    for level, low, high in (
        (1, 0, h - floor / 2),
        (2, h + floor / 2, 2 * h - roof / 2),
    ):
        model.add(box(0, 0, low, w, wall, high-low), name=f"Wall_back_{level}", color=concrete)
        model.add(box(0, wall, low, wall, d-wall, high-low), name=f"Wall_side_{level}", color=concrete)
        model.add(box(cx-side/2, cy-side/2, low, side, side, high-low),
                  name=f"Column_{level}", color=concrete)
        model.add(box(w-glass, wall, low, glass, d-wall-glass, high-low),
                  name=f"Glass_side_{level}", color=glazing)
        front = box(wall, d-glass, low, w-wall, glass, high-low)
        if level == 1:
            front = front.cut(box(door_x, d-glass-.01, -.01, door_w, glass+.02, door_h+.01))
        model.add(front, name=f"Glass_front_{level}", color=glazing)

    reveal = .012
    model.add(box(door_x+reveal, d-glass, reveal, door_w-2*reveal, glass, door_h-2*reveal),
              name="Door_glass", color=cq.Color(0.30, 0.57, 0.64, 0.50))
    model.add(box(0, 0, h-floor/2, w, d, floor), name="Floor", color=concrete)
    model.add(box(0, 0, 2*h-roof/2, w, d, roof), name="Roof", color=concrete)
    return model

def draw_house(stem, g):
    w, d, h = (g[key] for key in ("width_m", "depth_m", "storey_height_m"))
    wall, floor, roof = (g[f"{key}_thickness_m"] for key in ("wall", "floor", "roof"))
    side, setback = g["column_side_m"], g["column_setback_m"]
    door_center, door_w, door_h = (g[key] for key in ("door_center_m", "door_width_m", "door_height_m"))
    scale = min(48, 320 / max(w, d, 2*h))
    x, y = 480 - w*scale/2, 527
    x_right, cy = x + w*scale, y - d*scale
    px, py = x_right - setback*scale, cy + setback*scale
    door_x = x + (door_center - door_w/2)*scale

    def rect(x, y, w, h, style):
        return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" class="{style}"/>'

    def sheet(suffix, title, ref, elements):
        path = stem.with_name(f"{stem.name}-{suffix}.svg")
        write_sheet(path, title, ref, elements, "Glass house")

    plan = [rect(x, cy, w*scale, d*scale, "roof"),
            rect(x, cy, wall*scale, d*scale, "wall"),
            rect(x, y-wall*scale, w*scale, wall*scale, "wall"),
            line(x, cy, x_right, cy, "glass-line"), line(x_right, cy, x_right, y, "glass-line"),
            line(door_x, cy, door_x+door_w*scale, cy, "ground"),
            line(door_x, cy, door_x, cy+door_w*scale, "ground"),
            f'<path d="M {door_x+door_w*scale} {cy} A {door_w*scale} {door_w*scale} 0 0 1 '
            f'{door_x} {cy+door_w*scale}" class="extension" fill="none"/>',
            rect(px-side*scale/2, py-side*scale/2, side*scale, side*scale, "wall"),
            line(px, py, x_right, cy, "cut"),
            label(x_right+16, cy+8, "Column-free corner"),
            line(px-24, py, px-side*scale/2, py, "extension"),
            label(px-30, py+4, f"Column {side*1000:g} × {side*1000:g} mm", anchor="end")]
    plan += dimension(x, y, x_right, y, 39, w)
    plan += dimension(x, y, x, cy, -45, d)
    plan += dimension(px, py, x_right, py, 36, setback)
    sheet("plan", "Ground-floor plan", "GH-01", plan)

    middle = y - h*scale
    top = y - 2*h*scale
    edges = [rect(x, middle-floor*scale/2, w*scale, floor*scale, "wall"),
             rect(x, top-roof*scale/2, w*scale, roof*scale, "wall"),
             line(x-26, y, x_right+26, y, "ground")]
    elevations = [rect(x, top, w*scale, 2*h*scale, "glass"),
                  rect(door_x, y-door_h*scale, door_w*scale, door_h*scale, "glass")]
    elevations += [line(door_x+door_w*scale-8, y-door_h*scale*.52,
                        door_x+door_w*scale-4, y-door_h*scale*.52, "ground")]
    elevations += edges + dimension(x, y, x, middle, -40, h) + dimension(x, middle, x, top, -40, h)
    elevations += dimension(x, y, x_right, y, 38, w)
    sheet("elevation", "Glazed elevation", "GH-02", elevations)

    section = [rect(x, top, wall*scale, 2*h*scale, "wall"),
               rect(px-side*scale/2, top, side*scale, 2*h*scale, "wall"),
               line(x_right, y, x_right, top, "glass-line"), *edges,
               label(px, y+35, "Continuous column", anchor="middle"),
               *dimension(px, top, x_right, top, -38, setback),
               *dimension(x, y, x, top, -42, 2*h)]
    sheet("section", "Section through the column", "GH-03", section)

def draw_case(stem, case):
    draw_house(stem, case["geometry"])

def run_case(stem, step, mesh, result, case):
    g = case["geometry"]
    if not all(isfinite(v) and v > 0 for v in g.values()):
        raise ValueError("House dimensions must be finite and positive.")
    if (g["column_setback_m"] <= g["column_side_m"] / 2 + g["glass_thickness_m"]
            or g["column_setback_m"] + g["wall_thickness_m"] + g["column_side_m"] / 2
            >= min(g["width_m"], g["depth_m"])):
        raise ValueError("The column must fit between the walls and the glazing.")
    door_w, door_x = g["door_width_m"], g["door_center_m"]
    if (door_x - door_w/2 <= g["wall_thickness_m"] or door_x + door_w/2 >= g["width_m"] - g["glass_thickness_m"]
            or g["door_height_m"] >= g["storey_height_m"] - g["floor_thickness_m"]/2
            or (g["floor_thickness_m"] + g["roof_thickness_m"])/2 >= g["storey_height_m"]
            or g["glass_thickness_m"] + g["wall_thickness_m"] >= min(g["width_m"], g["depth_m"])
            or door_w <= .024 or g["door_height_m"] <= .024):
        raise ValueError("The glazing, door and slabs must fit within the house.")

    draw_case(stem, case)
    export_step(house_cad(g), step)
    house_mesh(mesh, g, case["mesh"]["element_size_m"])
    settings = case["structural_model"]
    concrete = (settings["young_modulus_pa"], settings["poisson_ratio"], settings["density_kg_m3"])
    materials = [(g[key], *concrete, 0, 0) for key in
                 ("floor_thickness_m", "column_side_m", "wall_thickness_m", "roof_thickness_m")]
    solve_shell_structure(mesh, result, settings, 0, 0, 0, body_materials=materials,
                          beam_source=SQUARE_COLUMN)
    add_displacement_vector(result)
