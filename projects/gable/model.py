from math import ceil, hypot, isfinite

import cadquery as cq
import gmsh

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from common.shell_solver import SQUARE_COLUMN, solve_shell_structure

def build_gable_cad(width, depth, eave, rise, thickness, side, projection=0):
    model = cq.Assembly(name="Gable_roof")
    concrete = cq.Color(0.71, 0.70, 0.66)
    half_side = side / 2
    ridge = width / 2
    slope = rise / ridge
    half_vertical_thickness = thickness * hypot(1, slope) / 2

    def soffit(x):
        return eave + rise - slope * abs(x - ridge) - half_vertical_thickness

    def extrude_section(points, back_y, length):
        plane = cq.Plane(origin=(0, 1000 * back_y, 0),
                         xDir=(1, 0, 0), normal=(0, -1, 0))
        section = [(1000 * x, 1000 * z) for x, z in points]
        return cq.Workplane(plane).polyline(section).close().extrude(1000 * length)

    edges = (-half_side, ridge, width + half_side)
    bottom = [(x, soffit(x)) for x in edges]
    top = [(x, soffit(x) + 2 * half_vertical_thickness) for x in reversed(edges)]
    roof = extrude_section(bottom + top, depth + half_side, depth + half_side + max(half_side, projection))
    model.add(roof, name="Roof", color=concrete)

    for index, (x, y) in enumerate(((0, 0), (width, 0), (0, depth), (width, depth)), start=1):
        left, right = x - half_side, x + half_side
        section = [(left, 0), (right, 0), (right, soffit(right)), (left, soffit(left))]
        model.add(extrude_section(section, y + half_side, side),
                  name=f"Column_{index}", color=concrete)
    return model

def draw_gable(stem, width, depth, eave, rise, side, projection=0):
    scale = min(550 / width, 250 / max(depth + projection, eave + rise))
    x, y = 190, 510
    right, back = x + width * scale, y - depth * scale
    center = (x + right) / 2
    front = y + projection * scale
    plan = [f'<rect x="{x}" y="{back}" width="{width*scale}" height="{(depth+projection)*scale}" class="roof"/>',
            line(center, back, center, front, "cut"), label(center + 12, back + 26, "Ridge")]
    for px, py in ((x, y), (right, y), (x, back), (right, back)):
        plan.append(f'<rect x="{px-side*scale/2}" y="{py-side*scale/2}" '
                    f'width="{side*scale}" height="{side*scale}" class="wall"/>')
    plan.extend(dimension(x,front,right,front,40,width))
    plan.extend(dimension(x,back,x,y,-60,depth))

    if projection:
        plan += [f'<rect x="{x:g}" y="{y:g}" width="{center-x:g}" height="{front-y:g}" class="glass"/>',
                 line(x,y,right,y,"cut"), label(x+8,front-10,"Uplift zone")]
        plan += dimension(right,y,right,front,58,projection)

    roof_y = y - eave * scale
    ridge_y = y - (eave + rise) * scale
    cross = [line(x,y,x,roof_y,"ground"), line(right,y,right,roof_y,"ground"),
             line(x,roof_y,center,ridge_y,"ground"), line(center,ridge_y,right,roof_y,"ground"),
             line(x-20,y,right+20,y,"ground")]
    cross.extend(dimension(x,roof_y,x,y,-55,eave))
    cross.extend(dimension(right,ridge_y,right,roof_y,52,rise))
    cross.extend(dimension(x,y,right,y,40,width))

    end = x + depth * scale
    nose = x - projection * scale
    longitudinal = [line(x,y,x,roof_y,"ground"), line(end,y,end,roof_y,"ground"),
                    line(nose,roof_y,end,roof_y,"ground"), line(nose,ridge_y,end,ridge_y,"cut"),
                    line(nose,roof_y,nose,ridge_y,"ground"), line(end,roof_y,end,ridge_y,"ground")]
    longitudinal.extend(dimension(x,y,end,y,40,depth))
    longitudinal.extend(dimension(end,ridge_y,end,y,45,eave+rise))
    if projection:
        longitudinal += dimension(nose,y,x,y,40,projection)
    for number, (suffix, title, drawing) in enumerate((
        ("plan", "Roof plan", plan), ("elevation", "Longitudinal elevation", longitudinal),
        ("section", "Cross-section", cross),
    ), start=1):
        path=stem.with_name(f"{stem.name}-{suffix}.svg")
        write_sheet(path, title, f"GF-{number:02d}", drawing, project="Gable frame")
        print(f"Wrote {path}",flush=True)

def gable_mesh(path, width, depth, eave, rise, size, projection=0):
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal",0)
        gmsh.model.add("gable")
        g=gmsh.model.geo
        front=[g.addPoint(x,0,z) for x,z in ((0,eave),(width/2,eave+rise),(width,eave))]
        rear=[g.addPoint(x,depth,z) for x,z in ((0,eave),(width/2,eave+rise),(width,eave))]
        slope=hypot(width/2,rise)

        def edge(a,b,length):
            tag=g.addLine(a,b)
            g.mesh.setTransfiniteCurve(tag,ceil(length/size)+1)
            return tag

        rows = [(front, rear, depth)]
        if projection:
            tip = [g.addPoint(x,-projection,z) for x,z in ((0,eave),(width/2,eave+rise),(width,eave))]
            rows.insert(0,(tip,front,projection))
        cross_edges = {}
        roof, corner = [], []
        for start, end, length in rows:
            longitudinal = [edge(a,b,length) for a,b in zip(start,end,strict=True)]
            for i in (0,1):
                for row in (start,end):
                    pair = (row[i],row[i+1])
                    if pair not in cross_edges:
                        cross_edges[pair] = edge(*pair,slope)
                a = cross_edges[(start[i],start[i+1])]
                b = cross_edges[(end[i],end[i+1])]
                face = g.addPlaneSurface([g.addCurveLoop([a,longitudinal[i+1],-b,-longitudinal[i]])])
                g.mesh.setTransfiniteSurface(face)
                g.mesh.setRecombine(2,face)
                (corner if start is not front and i == 0 else roof).append(face)
        bases=[g.addPoint(x,y,0) for x,y in ((0,0),(width,0),(0,depth),(width,depth))]
        columns=[edge(a,b,eave) for a,b in zip(bases,[front[0],front[2],rear[0],rear[2]],strict=True)]
        g.synchronize()
        gmsh.model.addPhysicalGroup(2,roof,1,"roof")
        if corner:
            gmsh.model.addPhysicalGroup(2,corner,3,"wind_zone")
        gmsh.model.addPhysicalGroup(1,columns,2,"columns")
        gmsh.model.addPhysicalGroup(0,bases,3,"fixed_bases")
        gmsh.option.setNumber("Mesh.MshFileVersion",2.2)
        gmsh.model.mesh.generate(2)
        gmsh.write(str(path))
    finally:
        gmsh.finalize()

def gable_dimensions(case):
    dimensions = case["geometry"]
    width, depth, eave, rise, thickness, side = (
        dimensions[key] for key in ("width_m", "depth_m", "eave_height_m",
                                    "rise_m", "roof_thickness_m", "column_side_m")
    )
    if not all(isfinite(value) and value > 0 for value in (width, depth, eave, rise, thickness, side)):
        raise ValueError("Gable dimensions must be finite and positive.")
    return width, depth, eave, rise, thickness, side

def loading(case):
    projection = case["geometry"].get("projection_m", 0)
    loads = case.get("loads", {})
    pressure = loads.get("roof_pressure_pa", 0)
    uplift = loads.get("corner_uplift_pa", 0)
    if not all(isfinite(v) and v >= 0 for v in (projection,pressure,uplift)):
        raise ValueError("Projection, roof pressure and uplift must be finite and non-negative.")
    if uplift and not projection:
        raise ValueError("Corner uplift requires a projecting roof.")
    return projection,pressure,uplift

def draw_case(stem, case):
    width, depth, eave, rise, _, side = gable_dimensions(case)
    projection,_,_ = loading(case)
    draw_gable(stem, width, depth, eave, rise, side, projection)

def run_case(stem, step, mesh, result, case):
    width, depth, eave, rise, thickness, side = gable_dimensions(case)
    projection,pressure,uplift = loading(case)
    draw_gable(stem, width, depth, eave, rise, side, projection)
    export_step(build_gable_cad(width, depth, eave, rise, thickness, side, projection), step)
    gable_mesh(mesh, width, depth, eave, rise, case["mesh"]["element_size_m"], projection)
    settings = case["structural_model"]
    concrete = (settings["young_modulus_pa"], settings["poisson_ratio"], settings["density_kg_m3"])
    materials = [(thickness,*concrete,pressure,0), (side,*concrete,0,0)]
    if projection:
        materials.append((thickness,*concrete,pressure-uplift,0))
    solve_shell_structure(mesh, result, settings, thickness, side, pressure,
                          body_materials=materials, beam_source=SQUARE_COLUMN)
