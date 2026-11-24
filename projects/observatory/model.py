from collections import Counter
from functools import partial
from math import asin, ceil, cos, dist, isfinite, pi, radians, sin, sqrt

import cadquery as cq

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from common.shell_solver import CIRCULAR_TUBE, solve_shell_structure
from common.elmer import add_displacement_vector

def subdivide(stops, max_step):
    values = [stops[0]]
    for a, b in zip(stops, stops[1:]):
        count = ceil((b - a) / max_step)
        values.extend(a + (b - a) * i / count for i in range(1, count))
        values.append(b)
    return values

def dome_point(radius, u, angle, height):
    across = radius * cos(u)
    return (radius * sin(u), across * cos(angle), height + across * sin(angle))

def observatory_mesh(radius, height, slot, stop, door, door_height, size,
                     interior_arches, glass_radius, glass_thickness, glass_density, transverse_arches):
    half_slot = asin(slot / (2 * radius))
    door_angle = pi / 2 - asin(door / (2 * radius))
    count = interior_arches // 2 + 1
    side = [-pi / 2 + (pi / 2 - half_slot) * i / count for i in range(count)]
    stations = side + [-half_slot, half_slot] + [-u for u in reversed(side)]
    intervals = transverse_arches + 1
    before = max(1, min(intervals - 1, round(intervals * stop / pi)))
    after = intervals - before
    angles = ([stop * i / before for i in range(before)] + [stop]
              + [stop + (pi-stop)*i/after for i in range(1, after)] + [pi])
    nodes, ids = [], {}

    def node(point):
        point = tuple(round(v, 10) for v in point)
        if point not in ids:
            nodes.append(point)
            ids[point] = len(nodes)
        return ids[point]

    beams, ring, walls, supports = set(), [], [], {}
    glass_mass = Counter()
    glass_inner = glass_radius - glass_thickness

    def member(u0, u1, t0, t1, divisions):
        span = [node(dome_point(radius, u0 + (u1-u0)*i/divisions,
                                t0 + (t1-t0)*i/divisions, height))
                for i in range(divisions + 1)]
        return [tuple(sorted((a, b))) for a, b in zip(span, span[1:]) if a != b]

    wall_stations = subdivide(sorted({*stations, door_angle}), size / radius)

    def panel_edge(u0, u1, angle):
        if angle in (0, pi):
            cuts = [u for u in wall_stations if u0 <= u <= u1]
            return [pair for a, b in zip(cuts, cuts[1:]) for pair in member(a, b, angle, angle, 1)]
        return member(u0, u1, angle, angle, ceil(radius * (u1-u0) / size))

    for a, b in zip(stations, stations[1:]):
        for low, high in zip(angles, angles[1:]):
            if -half_slot <= a and b <= half_slot and high <= stop:
                continue
            divisions = ceil(radius * (high-low) / size)
            edges = [panel_edge(a, b, low), panel_edge(a, b, high),
                     member(a, a, low, high, divisions), member(b, b, low, high, divisions)]
            if low > 0:
                beams.update(edges[0])
            if high < pi:
                beams.update(edges[1])
            beams.update(edges[2])
            beams.update(edges[3])
            x0 = -glass_radius if a == -pi / 2 else radius * sin(a)
            x1 = glass_radius if b == pi / 2 else radius * sin(b)
            def integral(r):
                lo, hi = max(-r, x0), min(r, x1)
                return r*r*(hi-lo) - (hi**3-lo**3)/3 if hi > lo else 0
            mass = (high-low) / 2 * (integral(glass_radius) - integral(glass_inner)) * glass_density
            perimeter = [pair for edge in edges for pair in edge]
            lengths = [dist(nodes[i-1], nodes[j-1]) for i, j in perimeter]
            perimeter_length = sum(lengths)
            for pair, length in zip(perimeter, lengths, strict=True):
                glass_mass[pair] += mass * length / perimeter_length

    bearings = [(sin(u), cos(u)) for u in wall_stations]
    bearings += [(sin(u), -cos(u)) for u in reversed(wall_stations[1:-1])]
    levels = subdivide([0, door_height, height], size)
    for i, (x, y) in enumerate(bearings):
        xx, yy = bearings[(i + 1) % len(bearings)]
        ring.append(tuple(sorted(node((radius * a, radius * b, height)) for a, b in ((x, y), (xx, yy)))))
        for low, high in zip(levels, levels[1:]):
            if high <= door_height and min(x, xx) >= sin(door_angle) - 1e-10:
                continue
            quad = tuple(node((radius * a, radius * b, z))
                         for a, b, z in ((xx, yy, low), (x, y, low), (x, y, high), (xx, yy, high)))
            walls.append(quad)
            if low == 0:
                for j in quad[:2]:
                    supports.setdefault(j, len(walls))

    return nodes, sorted(beams), ring, walls, supports, glass_mass

def write_meshes(path, data, member_groups):
    nodes, beams, ring, walls, supports, _ = data
    cells = [(1, 1, 202, pair) for pair in beams]
    cells += [(1, 2, 202, pair) for pair in ring]
    cells += [(3, 3, 404, quad) for quad in walls]
    nodes_text = [" ".join(map(str, xyz)) for xyz in nodes]
    gmsh_cells = [(kind, group, ids) for kind, group, _, ids in cells]
    gmsh_cells += [(15, 4, (j,)) for j in supports]

    def row(*values):
        return " ".join(map(str, values))

    path.write_text("\n".join([
        "$MeshFormat", "2.2 0 8", "$EndMeshFormat",
        "$PhysicalNames", "4", '1 1 "dome_ribs"', '1 2 "support_ring"',
        '2 3 "concrete_wall"', '0 4 "fixed_base"', "$EndPhysicalNames",
        "$Nodes", str(len(nodes)),
        *(row(i, xyz) for i, xyz in enumerate(nodes_text, 1)), "$EndNodes",
        "$Elements", str(len(gmsh_cells)),
        *(row(i, kind, 2, group, group, *ids)
          for i, (kind, group, ids) in enumerate(gmsh_cells, 1)),
        "$EndElements", "",
    ]))

    def native_mesh(directory):
        directory.mkdir()
        counts = Counter(code for _, _, code, _ in cells)
        counts[101] = len(supports)
        rows = {
            "header": [row(len(nodes), len(cells), len(supports)), str(len(counts)),
                       *(row(code, count) for code, count in sorted(counts.items()))],
            "nodes": [row(i, -1, xyz) for i, xyz in enumerate(nodes_text, 1)],
            "elements": [row(i, body, code, *ids)
                         for i, ((_, _, code, ids), body) in enumerate(
                             zip(cells, member_groups + [3] * len(walls), strict=True), 1)],
            "boundary": [row(i, 3, len(beams) + len(ring) + parent, 0, 101, j)
                         for i, (j, parent) in enumerate(supports.items(), 1)],
        }
        for name, content in rows.items():
            (directory / f"mesh.{name}").write_text("\n".join(content) + "\n")

    return native_mesh

def build_observatory_cad(g, data):
    ro = 500 * g["diameter_m"]
    height = 1000 * g["wall_height_m"]
    wall = 1000 * g["wall_thickness_m"]
    half_slot = 500 * g["opening_width_m"]
    glass = 1000 * g["glass_thickness_m"]
    stop = radians(g["opening_end_deg"])
    origin = cq.Vector(0, 0, height)

    concrete = cq.Workplane("XY").circle(ro).circle(ro - wall).extrude(height)
    door = cq.Solid.makeBox(ro, 1000 * g["door_width_m"], 1000 * g["door_height_m"] + 1,
                            cq.Vector(0, -500 * g["door_width_m"], -1))
    concrete = concrete.cut(door)
    outer = cq.Solid.makeSphere(ro, origin, angleDegrees1=0)
    inner = cq.Solid.makeSphere(ro - glass, origin, angleDegrees1=0)
    wedge = cq.Workplane("YZ", origin=(-half_slot, 0, height)).polyline(
        [(0, 0), (3 * ro, 0), (3 * ro * cos(stop / 2), 3 * ro * sin(stop / 2)),
         (3 * ro * cos(stop), 3 * ro * sin(stop))]
    ).close().extrude(2 * half_slot)
    glazing = outer.cut(inner).cut(wedge.val())

    nodes, beams, ring, _, _, _ = data

    def frame(members, diameter, thickness):
        bars = []
        for a, b in members:
            p = cq.Vector(*(1000 * v for v in nodes[a - 1]))
            q = cq.Vector(*(1000 * v for v in nodes[b - 1]))
            outer = cq.Solid.makeCylinder(500 * diameter, (q - p).Length, p, q - p)
            inner = cq.Solid.makeCylinder(500 * diameter - 1000 * thickness, (q - p).Length, p, q - p)
            bars.append(outer.cut(inner))
        return cq.Compound.makeCompound(bars)

    model = cq.Assembly(name="Observatory")
    model.add(concrete, name="Concrete_base", color=cq.Color(0.70, 0.69, 0.65))
    model.add(glazing, name="Glazing", color=cq.Color(0.45, 0.72, 0.80, 0.30))
    model.add(frame(beams, g["rib_diameter_m"], g["rib_wall_m"]), name="Steel_grid", color=cq.Color(0.24, 0.30, 0.32))
    model.add(frame(ring, g["ring_diameter_m"], g["ring_wall_m"]), name="Steel_ring", color=cq.Color(0.24, 0.30, 0.32))
    return model

def draw_observatory(stem, g, data):
    radius = g["diameter_m"] / 2
    height = g["wall_height_m"]
    t = g["wall_thickness_m"]
    half_slot = g["opening_width_m"] / 2
    stop = radians(g["opening_end_deg"])
    scale = min(74, 335 / max(2 * radius, height + radius))
    cx, cy, ground = 480, 355, 529
    rr = radius * scale
    nodes, beams, ring, _, _, _ = data

    def circle(r, style):
        return f'<circle cx="{cx}" cy="{cy}" r="{r * scale}" class="{style}"/>'

    def rectangle(x, y, w, h, style):
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="{style}"/>'

    def trace(project, edges):
        return [line(*project(nodes[a - 1]), *project(nodes[b - 1]), "ground") for a, b in edges]

    def sheet(suffix, title, ref, elements):
        path = stem.with_name(f"{stem.name}-{suffix}.svg")
        write_sheet(path, title, ref, elements, "Observatory")

    plan = [circle(radius, "roof"), circle(radius - t, "roof")]
    plan += trace(lambda p: (cx + p[0] * scale, cy - p[1] * scale), beams + ring)
    plan += dimension(cx - rr, cy + rr, cx + rr, cy + rr, 43, 2 * radius)
    plan += [label(cx, 158, "Observation slit", anchor="middle"),
             line(cx, 165, cx, cy - rr * .73, "extension"),
             label(cx + rr + 18, cy + 6, "Side entrance")]
    sheet("plan", "Roof plan", "OBS-01", plan)

    top = ground - height * scale
    profile = f'M {cx-rr} {top} A {rr} {rr} 0 0 1 {cx+rr} {top} Z'
    elevation = [rectangle(cx - rr, top, 2 * rr, height * scale, "wall"),
                 f'<path d="{profile}" class="glass"/>']
    edge_height = sqrt(radius**2 - half_slot**2)
    slot_top = top - edge_height * sin(stop) * scale
    crown = top - edge_height * scale
    left, right = cx - half_slot * scale, cx + half_slot * scale
    elevation += [f'<path d="M {left} {top} V {slot_top} Q {left} {crown} {cx} {crown} '
                  f'Q {right} {crown} {right} {slot_top} V {top} Z" fill="#f9f8f4"/>']
    front = [(a, b) for a, b in beams if min(nodes[a - 1][1], nodes[b - 1][1]) >= -1e-9]
    elevation += trace(lambda p: (cx + p[0] * scale, ground - p[2] * scale), front)
    elevation += [line(cx-rr-25, ground, cx+rr+25, ground, "ground")]
    elevation += dimension(cx-rr, ground, cx-rr, top, -38, height)
    elevation += dimension(cx+rr, ground, cx+rr, top-rr, 45, height + radius)
    elevation += dimension(left, top, right, top, -27, 2 * half_slot)
    sheet("elevation", "Elevation facing the slit", "OBS-02", elevation)

    section = [rectangle(cx - rr, top, t * scale, height * scale, "wall"),
               rectangle(cx + rr - t * scale, top, t * scale, height * scale, "wall"),
               line(cx-rr-30, ground, cx+rr+30, ground, "ground"),
               f'<path d="M {cx-rr} {top} A {rr} {rr} 0 0 1 '
               f'{cx+rr*cos(stop)} {top-rr*sin(stop)}" class="glass-line" fill="none"/>']
    section += dimension(cx-rr, ground, cx-rr, top, -38, height)
    section += dimension(cx+rr, ground, cx+rr, top-rr, 45, height + radius)
    section += dimension(cx-rr+t*scale, ground, cx+rr-t*scale, ground, 38, 2*(radius-t))
    section += [label(cx+rr*.7, top-rr*.75, "Open to the sky", anchor="middle")]
    sheet("section", "Section through the slit", "OBS-03", section)

def tube_area(diameter, thickness):
    return pi * thickness * (diameter - thickness)

def observatory_case_mesh(case):
    g, settings = case["geometry"], case["structural_model"]
    if not all(isfinite(v) and v > 0 for k, v in g.items() if k != "transverse_arches"):
        raise ValueError("Observatory dimensions must be finite and positive.")
    radius = g["diameter_m"] / 2
    wall = g["wall_thickness_m"]
    height = g["wall_height_m"]
    slot = g["opening_width_m"]
    door = g["door_width_m"]
    stop = radians(g["opening_end_deg"])
    if (max(wall, g["glass_thickness_m"]) >= radius or max(slot, door) >= 2 * (radius - wall)
            or g["door_height_m"] >= height or not pi / 2 < stop < pi):
        raise ValueError("The openings must fit within the observatory envelope.")

    if type(g["interior_arches"]) is not int or g["interior_arches"] % 2:
        raise ValueError("Use a positive even number of interior arches.")
    if any(2 * g[f"{part}_wall_m"] >= g[f"{part}_diameter_m"] for part in ("rib", "ring")):
        raise ValueError("Tube wall thickness must be less than its radius.")

    transverse = g.get("transverse_arches", ceil(stop*(radius-wall/2)/0.55) + ceil((pi-stop)*(radius-wall/2)/0.55) - 1)
    if type(transverse) is not int or transverse < 2:
        raise ValueError("Use at least two transverse arches.")

    return observatory_mesh(radius - wall / 2, height, slot, stop, door, g["door_height_m"],
                            case["mesh"]["element_size_m"], g["interior_arches"], radius,
                            g["glass_thickness_m"], settings["glass_density_kg_m3"], transverse)

def draw_case(stem, case):
    draw_observatory(stem, case["geometry"], observatory_case_mesh(case))

def run_case(stem, step, mesh, result, case):
    g, settings = case["geometry"], case["structural_model"]
    wall = g["wall_thickness_m"]
    data = observatory_case_mesh(case)
    draw_observatory(stem, g, data)
    export_step(build_observatory_cad(g, data), step)
    nodes, beams, ring, _, _, glass_mass = data
    areas = {part: tube_area(g[f"{part}_diameter_m"], g[f"{part}_wall_m"])
             for part in ("rib", "ring")}
    steel = settings["steel_density_kg_m3"]
    materials = [
        (g["rib_diameter_m"], 210e9, 0.3, steel, 0, g["rib_wall_m"]),
        (g["ring_diameter_m"], 210e9, 0.3, steel, 0, g["ring_wall_m"]),
        (wall, settings["young_modulus_pa"], settings["poisson_ratio"], settings["density_kg_m3"], 0, 0),
    ]
    body_for_load = {}
    member_groups = []
    for part, members in (("rib", beams), ("ring", ring)):
        for pair in members:
            a, b = pair
            volume = areas[part] * dist(nodes[a-1], nodes[b-1])
            load = round(glass_mass[pair] / volume, 8)
            key = (part, load)
            if key not in body_for_load:
                body_for_load[key] = len(materials) + 1
                materials.append((g[f"{part}_diameter_m"], 210e9, 0.3, steel + load, 0, g[f"{part}_wall_m"]))
            member_groups.append(body_for_load[key])

    native_mesh = write_meshes(mesh, data, member_groups)
    solve_shell_structure(mesh, result, settings, 0, 0, 0,
                          body_materials=materials, native_mesh=native_mesh,
                          beam_source=CIRCULAR_TUBE)

    add_displacement_vector(result)
