from itertools import pairwise
from math import ceil, isfinite, sqrt

import cadquery as cq

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from common.elmer import add_displacement_vector
from common.shell_solver import SQUARE_COLUMN, solve_shell_structure

def check(case):
    g = case["geometry"]
    if not all(isfinite(v) and v > 0 for v in g.values()):
        raise ValueError("Extension dimensions must be finite and positive.")
    if not (g["column_side_m"]/2 < g["column_offset_m"] < g["span_m"] - g["column_side_m"]/2
            and g["beam_depth_m"] > 2*g["flange_thickness_m"]
            and g["flange_width_m"] > g["web_thickness_m"]
            and g["column_side_m"] <= g["flange_width_m"]):
        raise ValueError("The column footprint and I-section dimensions must fit.")
    connection = case.get("connection")
    if connection and not all(isfinite(connection[key]) and connection[key] > 0
                              for key in ("bearing_plate_thickness_m", "stiffener_thickness_m", "mesh_size_m")):
        raise ValueError("Connection dimensions and mesh size must be finite and positive.")
    force = case["loads"]["column_force_kn"]
    wall_modulus = case["structural_model"]["wall_modulus_pa"]
    if not all(isfinite(v) and v > 0 for v in (force, wall_modulus)):
        raise ValueError("Column force and wall modulus must be finite and positive.")

def beam_parameters(g):
    return (g["span_m"], g["column_offset_m"], g["beam_depth_m"],
            g["flange_width_m"], g["flange_thickness_m"], g["web_thickness_m"])

def extension_cad(g):
    span, x, depth, width, flange, web = beam_parameters(g)
    wall, wall_width, height = (g[k] for k in ("wall_thickness_m","wall_effective_width_m","wall_height_m"))
    column, storey = g["column_side_m"], g["storey_height_m"]
    model = cq.Assembly(name="Roof_extension")
    steel, masonry, timber = cq.Color(0.28,0.35,0.38), cq.Color(0.73,0.69,0.63), cq.Color(0.78,0.70,0.57)
    run = span + wall

    def box(origin, sizes, name, color):
        shape = cq.Solid.makeBox(*(1000*v for v in sizes), cq.Vector(*(1000*v for v in origin)))
        model.add(shape, name=name, color=color)

    for name, z in (("Bottom_flange", 0), ("Top_flange", depth-flange)):
        box((-wall/2,-width/2,z),(run,width,flange),name,steel)
    box((-wall/2,-web/2,flange),(run,web,depth-2*flange),"Web",steel)
    for name, station in (("Left_wall",0),("Right_wall",span)):
        box((station-wall/2,-wall_width/2,-height),(wall,wall_width,height),name,masonry)
    for floor in range(2):
        z = depth + floor*storey
        box((x-column/2,-column/2,z),(column,column,storey),"Upper_column_"+str(floor+1),timber)
        box((-wall/2,-wall_width/2,z+storey),(run,wall_width,0.16),"Upper_floor_"+str(floor+1),timber)
    return model

def stations(stops, size):
    values = sorted(set(stops))
    grid = []
    for a,b in pairwise(values):
        n = ceil((b-a)/size)
        grid.extend(a+(b-a)*i/n for i in range(n))
    return grid + values[-1:]

def extension_mesh(path,case,connection=None,stiffened=False):
    g = case["geometry"]
    span, x, depth, width, flange, _ = beam_parameters(g)
    wall, height = g["wall_thickness_m"],g["wall_height_m"]
    half_load = g["column_side_m"]/2
    size = case["mesh"]["element_size_m"]
    bottom, top = flange/2, depth-flange/2
    xs = stations((-wall/2,0,x-half_load,x,x+half_load,span,span+wall/2),size)
    if connection:
        fine = connection["mesh_size_m"]
        reach = min(0.55, x, span-x)
        left = stations((-wall/2,0,x-reach),size)
        near = stations((x-reach,x-half_load,x,x+half_load,x+reach),fine)
        right = stations((x+reach,span,span+wall/2),size)
        xs = left[:-1]+near[:-1]+right
        size = fine
    ys = stations((-width/2,0,width/2),size)
    zs = stations((bottom,top),size)
    nodes,cells = {},[]

    def cell(kind,body,points):
        ids = [nodes.setdefault(p,len(nodes)+1) for p in points]
        cells.append((kind,body,*ids))

    for a,b in pairwise(xs):
        for c,d in pairwise(ys):
            cell(3,1,[(a,c,bottom),(b,c,bottom),(b,d,bottom),(a,d,bottom)])
            loaded = a >= x-half_load and b <= x+half_load
            cell(3,4 if loaded else 1,[(a,c,top),(b,c,top),(b,d,top),(a,d,top)])
        for c,d in pairwise(zs):
            cell(3,3,[(a,0,c),(b,0,c),(b,0,d),(a,0,d)])
    if stiffened:
        for a,b in pairwise(ys):
            for low,high in pairwise(zs):
                cell(3,5,[(x,a,low),(x,b,low),(x,b,high),(x,a,high)])
    for station in (0,span):
        base = (station,0,-height)
        cell(1,2,[base,(station,0,bottom)])
        cell(15,3,[base])
    groups = ['2 1 "flanges"','1 2 "equivalent_walls"','2 3 "web"','2 4 "column_patch"',
              '0 3 "fixed_bases"']
    if stiffened:
        groups.append('2 5 "paired_stiffeners"')
    rows = ["$MeshFormat","2.2 0 8","$EndMeshFormat","$PhysicalNames",str(len(groups)),
            *groups,'$EndPhysicalNames','$Nodes',str(len(nodes))]
    rows.extend(f"{tag} {a} {b} {c}" for (a,b,c),tag in nodes.items())
    rows.extend(("$EndNodes","$Elements",str(len(cells))))
    rows.extend(" ".join(map(str,(i,kind,2,group,kind*10+group,*ids)))
                for i,(kind,group,*ids) in enumerate(cells,1))
    path.write_text("\n".join([*rows,"$EndElements",""]),encoding="ascii")

def draw_case(stem,case):
    check(case)
    g = case["geometry"]
    span,x,depth,width,flange,web = beam_parameters(g)
    scale = min(84,550/span,360/(2*g["storey_height_m"]+g["wall_height_m"]+depth))
    left, datum = 220,480
    right,pillar,top = left+scale*span,left+scale*x,datum-scale*depth
    t = scale*g["wall_thickness_m"]
    side = scale*g["column_side_m"]
    h = scale*g["wall_height_m"]
    storey = scale*g["storey_height_m"]
    wall_width = scale*g["wall_effective_width_m"]
    beam_width = scale*width

    def rect(x,y,w,h,style="roof"):
        return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" class="{style}"/>'

    def draw(suffix,title,number,elements):
        write_sheet(stem.with_name(stem.name+f"-{suffix}.svg"),title,number,elements,"Roof Extension")

    plan = [rect(left-t/2,320-wall_width/2,t,wall_width),rect(right-t/2,320-wall_width/2,t,wall_width),
            rect(left-t/2,320-beam_width/2,right-left+t,beam_width),
            rect(pillar-side/2,320-side/2,side,side,"wall")]
    plan += [line(left-t/2-22,320,left-t/2,320,"cut"),
             line(right+t/2,320,right+t/2+22,320,"cut"),
             label(left-t/2-27,325,"B",anchor="end"), label(right+t/2+27,325,"B")]
    plan += dimension(left,320-wall_width/2,right,320-wall_width/2,-42,span)
    plan += dimension(left,320+wall_width/2,pillar,320+wall_width/2,45,x)
    draw("plan","Transfer beam plan","A-01",plan)

    elevation = [rect(left-t/2,datum,t,h),rect(right-t/2,datum,t,h),
                 rect(left-t/2,top,right-left+t,datum-top,"wall")]
    for level in (0,1):
        z = top-(level+1)*storey
        elevation += [rect(pillar-side/2,z,side,storey),rect(left-t/2,z-6,right-left+t,6)]
    elevation += dimension(left,datum+h,right,datum+h,32,span)
    elevation += [label(pillar+15,top-12,f'{case["loads"]["column_force_kn"]:g} kN at column base')]
    draw("elevation","Load transfer elevation","A-02",elevation)

    section_scale = min(550,235/depth)
    bw,bh,ft,wt = (section_scale*v for v in (width,depth,flange,web))
    cx,cy = 450,275
    section = [rect(cx-bw/2,cy,bw,ft),rect(cx-wt/2,cy+ft,wt,bh-2*ft),rect(cx-bw/2,cy+bh-ft,bw,ft)]
    section += dimension(cx-bw/2,cy,cx+bw/2,cy,-35,width,millimetres=True)
    section += dimension(cx+bw/2,cy,cx+bw/2,cy+bh,45,depth,millimetres=True)
    section += [label(cx-bw/2,cy+bh+38,f'Web {web*1000:g} mm · Flanges {flange*1000:g} mm')]
    draw("section","Transfer beam cross-section","A-03",section)

def draw_comparison(path, variants):
    selected = [variants[key] for key in ("150-450", "300-450")]
    scale, beam_bottom = 39, 432
    max_force = max(force for v in selected for force in v["result"]["wall_reactions_kn"])
    depth_mm = selected[0]["geometry"]["beam_depth_m"] * 1000
    load = selected[0]["column_force_kn"]
    elements = [
        label(64, 151, f"SECTION B–B  ·  {depth_mm:g} mm transfer beam  ·  {load:g} kN column load plus beam self-weight"),
        line(480, 181, 480, 623, "extension"),
    ]

    def rect(x, y, w, h, fill, stroke):
        return (f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" '
                f'fill="{fill}" stroke="#33474b" stroke-width="{stroke}"/>')

    for left, variant in zip((146, 568), selected, strict=True):
        g = variant["geometry"]
        span, offset = g["span_m"], g["column_offset_m"]
        right, column = left + scale * span, left + scale * offset
        beam_top = beam_bottom - scale * g["beam_depth_m"]
        wall = scale * g["wall_thickness_m"]
        pier = scale * g["column_side_m"]
        storey = scale * g["storey_height_m"]
        foundation = beam_bottom + scale * g["wall_height_m"]
        title = "Offset column" if offset != span / 2 else "Centred column"
        elements += [label((left+right)/2, 179, title, "measure", "middle")]
        for level in (0, 1):
            z = beam_top - (level+1) * storey
            elements += [rect(column-pier/2, z, pier, storey, "#d8c6ad", 1.5),
                         rect(left-wall/2, z-6, right-left+wall, 6, "#eee5d7", 0.65)]
        elements += [rect(left-wall/2, beam_top, right-left+wall, beam_bottom-beam_top, "#416d74", 1.8)]

        forces = variant["result"]["wall_reactions_kn"]
        for station, force in zip((left, right), forces, strict=True):
            elements += [rect(station-wall/2, beam_bottom, wall, foundation-beam_bottom, "#ddd9d1", 1.6)]
            tip = foundation + 6
            tail = tip + 45 * force / max_force
            elements += [f'<path d="M{station:g} {tail:g} V{tip:g} m-5 7 l5 -7 5 7" '
                         'fill="none" stroke="#356d72" stroke-width="2"/>',
                         label(station, 612, f"{force:.1f} kN · {force/sum(forces):.0%}", "measure", "middle")]

        elements += dimension(left, beam_bottom, column, beam_bottom, 21, offset)
        elements += dimension(left, beam_bottom, right, beam_bottom, 47, span)

    elements.append(label(64, 638, "Arrows show vertical wall reactions at a common scale. Existing walls have equivalent stiffness."))
    write_sheet(path, "Column position and wall reactions", "A-04", elements, "Roof Extension")

def run_case(stem,step,mesh,result,case):
    draw_case(stem,case)
    g,s = case["geometry"],case["structural_model"]
    export_step(extension_cad(g),step)
    solve_extension(mesh, result, case)

def solve_extension(mesh, result, case, *, local=False, stiffened=False):
    check(case)
    g,s = case["geometry"],case["structural_model"]
    connection = case["connection"] if local else None
    extension_mesh(mesh,case,connection,stiffened)
    _,_,_,width,flange,web = beam_parameters(g)
    steel = (s["young_modulus_pa"],s["poisson_ratio"],s["density_kg_m3"])
    area = g["wall_thickness_m"]*g["wall_effective_width_m"]
    pressure = case["loads"]["column_force_kn"]*1000/(width*g["column_side_m"])
    seat = flange + (connection["bearing_plate_thickness_m"] if connection else 0)
    materials = [(flange,*steel,0,0),(sqrt(area),s["wall_modulus_pa"],0.2,0,0,0),
                 (web,*steel,0,0),(seat,*steel,pressure,0)]
    if stiffened:
        materials.append((connection["stiffener_thickness_m"],*steel,0,0))
    solve_shell_structure(mesh,result,s,0,0,0,body_materials=materials,beam_source=SQUARE_COLUMN)
    add_displacement_vector(result)
