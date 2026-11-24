from itertools import pairwise
from math import ceil, isfinite
from pathlib import Path

import cadquery as cq

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from common.elmer import add_displacement_vector
from common.shell_solver import solve_shell_structure

def check(case):
    g, h = case["geometry"], case["hangers"]
    if not all(isfinite(v) and v > 0 for v in (*g.values(), *h.values())):
        raise ValueError("Bridge dimensions and hanger properties must be finite and positive.")
    if type(h["count_per_side"]) is not int or h["count_per_side"] < 2:
        raise ValueError("Use at least two hangers per arch.")
    if g["arch_width_m"] >= g["deck_width_m"] / 2 or not 0 < g["deck_thickness_m"] < g["arch_depth_m"]:
        raise ValueError("The deck, arches and end walls must fit together.")
    pressure = case["loads"]["deck_pressure_pa"]
    if not isfinite(pressure) or pressure < 0:
        raise ValueError("Deck pressure must be finite and non-negative.")

def arch_height(g, x):
    fraction = x/g["span_m"]
    return g["arch_depth_m"]/2 + 4*g["arch_rise_m"]*fraction*(1-fraction)

def hanger_stations(case):
    count = case["hangers"]["count_per_side"]
    span = case["geometry"]["span_m"]
    return [span*i/(count+1) for i in range(1,count+1)]

def bridge_cad(case):
    g, h = case["geometry"], case["hangers"]
    span, width, deck, depth, rib, height, wall = (g[k] for k in (
        "span_m", "deck_width_m", "deck_thickness_m", "arch_depth_m",
        "arch_width_m", "abutment_height_m", "abutment_thickness_m"))
    bridge = cq.Assembly(name="Concrete_arch_bridge")
    concrete, steel = cq.Color(0.74,0.71,0.65), cq.Color(0.27,0.34,0.38)

    def box(origin, sizes):
        return cq.Solid.makeBox(*(1000*v for v in sizes), cq.Vector(*(1000*v for v in origin)))

    bridge.add(box((0,-width/2-rib/2,-deck/2),(span,width+rib,deck)), name="Deck", color=concrete)
    for name, x in (("West", -wall), ("East", span)):
        bridge.add(box((x,-width/2-rib/2,-height),(wall,width+rib,height+depth)),
                   name=f"Abutment_{name}",color=concrete)
    for name, y in (("North", width/2), ("South", -width/2)):
        bottom, top = [], []
        for i in range(25):
            x = span*i/24
            z = arch_height(g,x)
            bottom.append((x*1000,(z-depth/2)*1000))
            top.append((x*1000,(z+depth/2)*1000))
        arch = (cq.Workplane("XZ",origin=(0,1000*(y+rib/2),0))
                .moveTo(*bottom[0]).spline(bottom[1:],includeCurrent=True)
                .lineTo(*top[-1]).spline(top[-2::-1],includeCurrent=True)
                .close().extrude(1000*rib))
        bridge.add(arch,name=f"Arch_{name}",color=concrete)
        for i,x in enumerate(hanger_stations(case),1):
            cable = cq.Solid.makeCylinder(h["diameter_mm"]/2,1000*arch_height(g,x),
                                          cq.Vector(1000*x,1000*y,0))
            bridge.add(cable,name=f"Hanger_{name}_{i}",color=steel)
    return bridge

def stations(stops, size):
    grid = sorted(set(stops))
    output = []
    for a,b in pairwise(grid):
        n = ceil((b-a)/size)
        output.extend(a+(b-a)*i/n for i in range(n))
    return output + grid[-1:]

def bridge_mesh(path, case, *, remove_midspan_hanger=False):
    g = case["geometry"]
    span, half, depth, base = g["span_m"], g["deck_width_m"]/2, g["arch_depth_m"], -g["abutment_height_m"]
    size = case["mesh"]["element_size_m"]
    hanging = hanger_stations(case)
    if remove_midspan_hanger and len(hanging) % 2 == 0:
        raise ValueError("The hanger-loss study requires a hanger at midspan.")
    xs = stations((0,*hanging,span),size)
    ys = stations((-half,0,half),size)
    zs = stations((base,0,depth/2,depth),size)
    nodes, cells = {}, []

    def cell(kind, body, points):
        ids = [nodes.setdefault(point,len(nodes)+1) for point in points]
        cells.append((kind,body,*ids))

    for a,b in pairwise(xs):
        for c,d in pairwise(ys):
            cell(3,1,[(a,c,0),(b,c,0),(b,d,0),(a,d,0)])
        for y in (-half,half):
            za,zb = arch_height(g,a),arch_height(g,b)
            for low,high in pairwise((-depth/2,0,depth/2)):
                cell(3,3,[(a,y,za+low),(b,y,zb+low),(b,y,zb+high),(a,y,za+high)])
    for x in (0,span):
        for a,b in pairwise(ys):
            for low,high in pairwise(zs):
                cell(3,4,[(x,a,low),(x,b,low),(x,b,high),(x,a,high)])
    for x in hanging:
        for y in (-half,half):
            if remove_midspan_hanger and x == span/2 and y == -half:
                continue
            cell(1,2,[(x,y,0),(x,y,arch_height(g,x))])
    for point in list(nodes):
        if point[2] == base:
            cell(15,3,[point])
    rows = ["$MeshFormat","2.2 0 8","$EndMeshFormat","$PhysicalNames","5",
            '2 1 "deck"','1 2 "hangers"','2 3 "arches"','2 4 "abutments"','0 3 "fixed_base"',
            "$EndPhysicalNames","$Nodes",str(len(nodes))]
    rows.extend(f"{i} {x} {y} {z}" for (x,y,z),i in nodes.items())
    rows.extend(("$EndNodes","$Elements",str(len(cells))))
    rows.extend(" ".join(map(str,(i,kind,2,group,kind*10+group,*ids)))
                for i,(kind,group,*ids) in enumerate(cells,1))
    path.write_text("\n".join([*rows,"$EndElements",""]),encoding="ascii")

def draw_case(stem, case):
    check(case)
    g, h = case["geometry"], case["hangers"]
    span, width, rise = (g[k] for k in ("span_m","deck_width_m","arch_rise_m"))
    scale = min(600/span, 210/width, 160/rise)
    left, deck = 175, 430
    right = left+span*scale
    rib = g["arch_width_m"]*scale
    half_depth = g["arch_depth_m"]*scale/2
    hanger_labels = f'{h["count_per_side"]} × Ø{h["diameter_mm"]:g} mm per side'

    def draw(suffix,title,number,elements):
        write_sheet(stem.with_name(stem.name+f"-{suffix}.svg"),title,number,elements,"Concrete Arch Bridge")

    def shape(points):
        coords = " ".join(f"{x:g},{y:g}" for x,y in points)
        return f'<polygon points="{coords}" class="roof"/>'

    def rect(x,y,w,h):
        return shape([(x,y),(x+w,y),(x+w,y+h),(x,y+h)])

    plan_top = 250
    plan = [rect(left,plan_top,right-left,width*scale),
            rect(left,plan_top-rib/2,right-left,rib),
            rect(left,plan_top+width*scale-rib/2,right-left,rib),
            line(left,plan_top+width*scale/2,right,plan_top+width*scale/2,"cut")]
    for x in hanger_stations(case):
        for y in (plan_top,plan_top+width*scale):
            plan.append(rect(left+x*scale-2,y-2,4,4))
    plan += dimension(left,plan_top,right,plan_top,-34,span)
    plan += dimension(right,plan_top,right,plan_top+width*scale,40,width)
    draw("plan","Bridge plan","A-01",plan)

    deck_depth = g["deck_thickness_m"]*scale
    wall_width = g["abutment_thickness_m"]*scale
    wall_height = g["abutment_height_m"]*scale
    axis = [(left+x*scale,deck-arch_height(g,x)*scale) for x in (span*i/60 for i in range(61))]
    elevation = [line(left+x*scale,deck,left+x*scale,deck-arch_height(g,x)*scale,"ground")
                 for x in hanger_stations(case)]
    elevation += [rect(left,deck-deck_depth/2,right-left,deck_depth),
                  shape([(x,y-half_depth) for x,y in axis]+[(x,y+half_depth) for x,y in reversed(axis)]),
                  rect(left-wall_width,deck-2*half_depth,wall_width,wall_height+2*half_depth),
                  rect(right,deck-2*half_depth,wall_width,wall_height+2*half_depth)]
    elevation += dimension(left,deck+wall_height,right,deck+wall_height,36,span)
    elevation += [label((left+right)/2,deck-scale*rise-54,hanger_labels,anchor="middle")]
    draw("elevation","Longitudinal elevation","A-02",elevation)

    centre = 475
    edge = centre-width*scale/2
    crown = deck-scale*arch_height(g,span/2)
    section = [rect(edge-rib/2,deck-deck_depth/2,width*scale+rib,deck_depth)]
    for y in (edge,edge+width*scale):
        section += [line(y,deck-deck_depth/2,y,crown+half_depth,"ground"),
                    rect(y-rib/2,crown-half_depth,rib,2*half_depth)]
    section += dimension(edge,deck,edge+width*scale,deck,40,width)
    section += dimension(edge+width*scale+rib/2,deck-deck_depth/2,
                         edge+width*scale+rib/2,deck+deck_depth/2,39,g["deck_thickness_m"],millimetres=True)
    draw("section","Midspan section","A-03",section)

def run_case(stem, step, mesh, result, case):
    draw_case(stem,case)
    export_step(bridge_cad(case),step)
    solve_bridge(mesh, result, case)

def solve_bridge(mesh, result, case, *, remove_midspan_hanger=False):
    check(case)
    bridge_mesh(mesh,case,remove_midspan_hanger=remove_midspan_hanger)
    g,h,s = (case[k] for k in ("geometry","hangers","structural_model"))
    concrete = (s["young_modulus_pa"],s["poisson_ratio"],s["density_kg_m3"])
    materials = [(g["deck_thickness_m"],*concrete,case["loads"]["deck_pressure_pa"],0),
                 (h["diameter_mm"]/1000,h["young_modulus_pa"],0.3,h["density_kg_m3"],0,0),
                 (g["arch_width_m"],*concrete,0,0),
                 (g["abutment_thickness_m"],*concrete,0,0)]
    solve_shell_structure(mesh,result,s,0,0,0,body_materials=materials,
                          beam_source=Path(__file__).with_name("hanger.f90"))
    add_displacement_vector(result)
