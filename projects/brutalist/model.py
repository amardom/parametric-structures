from collections import Counter
from itertools import pairwise
from math import ceil, cos, isfinite, pi, sin

import cadquery as cq

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from common.elmer import add_displacement_vector
from common.shell_solver import solve_shell_structure

WIDTH, DEPTH, CORE = 20, 10, 4
CORE_AREA = 4 * CORE
ACCESS_Y = (.4, 1.3)
ACCESS_HEIGHT = 2.1
WALL_AREA = 2 * DEPTH + WIDTH - CORE
SLAB_AREA = WIDTH * DEPTH - CORE**2
STATIONS = (6, 10, 14)

def check(case):
    g, loads = case["geometry"], case["loads"]
    n = g["storeys"]
    if type(n) is not int or n < 3:
        raise ValueError("The building needs at least three storeys.")
    if not all(isfinite(v) and v > 0 for v in (*g.values(), *loads.values())):
        raise ValueError("Housing dimensions and loads must be finite and positive.")
    if g["storey_height_m"] <= ACCESS_HEIGHT:
        raise ValueError("Storey height must exceed the core access height.")
    if not g["minimum_thickness_m"] <= g["baseline_thickness_m"] <= g["maximum_thickness_m"]:
        raise ValueError("Baseline thickness must lie within the optimisation bounds.")

def band(level, count):
    return min(2, 3 * level // count)

def volumes(case):
    g = case["geometry"]
    counts = Counter(band(i,g["storeys"]) for i in range(g["storeys"]))
    height = g["storey_height_m"]
    opening_area = (ACCESS_Y[1] - ACCESS_Y[0]) * ACCESS_HEIGHT
    areas = [counts[i] * area for i in range(3)
             for area in (height*CORE_AREA - 2*opening_area, height*WALL_AREA)]
    return g["storeys"] * SLAB_AREA * g["slab_thickness_m"], areas

def wall_runs():
    core = [((-2,-2),(2,-2)),((2,-2),(2,2)),((2,2),(-2,2)),((-2,2),(-2,-2))]
    walls = [((-10,-5),(-10,5)),((10,-5),(10,5)),((-10,0),(-2,0)),((2,0),(10,0))]
    return core, walls

def subdivide(values, size):
    for a,b in pairwise(values):
        divisions = ceil((b-a)/size)
        yield from (a+(b-a)*i/divisions for i in range(divisions))
    yield values[-1]

def housing_mesh(case, mesh_path=None, *, core_openings=True):
    check(case)
    g = case["geometry"]
    n, height = g["storeys"],g["storey_height_m"]
    size = case["mesh"]["element_size_m"]
    xs = list(subdivide((-10,-2,0,2,10),size))
    ys = list(subdivide((-5,-2,0,*ACCESS_Y,2,5),size))
    node_ids, nodes, cells, supports = {}, [], [], {}

    def quad(body, points):
        ids = []
        for point in points:
            if point not in node_ids:
                nodes.append(point)
                node_ids[point] = len(nodes)
            ids.append(node_ids[point])
        cells.append((body,*ids))
        for node,point in zip(ids,points,strict=True):
            if point[2] == 0:
                supports.setdefault(node,len(cells))

    for level in range(n):
        low, high = level*height,(level+1)*height
        for a,b in pairwise(xs):
            for c,d in pairwise(ys):
                if -2 <= a and b <= 2 and -2 <= c and d <= 2:
                    continue
                quad(1,[(a,c,high),(b,c,high),(b,d,high),(a,d,high)])
        head = low + ACCESS_HEIGHT
        levels = list(subdivide((low,head,high),size))
        for kind,runs in enumerate(wall_runs()):
            body = 2+2*band(level,n)+kind
            for (x0,y0),(x1,y1) in runs:
                if x0 == x1:
                    line_points = [(x0,y) for y in ys if min(y0,y1)<=y<=max(y0,y1)]
                else:
                    line_points = [(x,y0) for x in xs if min(x0,x1)<=x<=max(x0,x1)]
                has_access = kind == 0 and x0 == x1
                for (a,c),(b,d) in pairwise(line_points):
                    in_access = has_access and ACCESS_Y[0] <= c and d <= ACCESS_Y[1]
                    for za,zb in pairwise(levels):
                        if core_openings and in_access and zb <= head:
                            continue
                        quad(body,[(a,c,za),(b,d,za),(b,d,zb),(a,c,zb)])

    if mesh_path is not None:
        rows = ["$MeshFormat","2.2 0 8","$EndMeshFormat","$Nodes",str(len(nodes))]
        rows.extend(f"{i} {x:g} {y:g} {z:.12g}" for i,(x,y,z) in enumerate(nodes,1))
        rows += ["$EndNodes","$Elements",str(len(cells)+len(supports))]
        rows.extend(" ".join(map(str,(i,3,2,body,body,*ids))) for i,(body,*ids) in enumerate(cells,1))
        rows.extend(f"{i} 15 2 3 8 {node}" for i,node in enumerate(supports,len(cells)+1))
        mesh_path.write_text("\n".join([*rows,"$EndElements",""]),encoding="ascii")
    return nodes,cells,supports

def native_mesh(directory, data):
    nodes,cells,supports = data
    directory.mkdir()
    rows = {
        "header": [f"{len(nodes)} {len(cells)} {len(supports)}","2",f"101 {len(supports)}",f"404 {len(cells)}"],
        "nodes": [f"{i} -1 {x:.12g} {y:.12g} {z:.12g}" for i,(x,y,z) in enumerate(nodes,1)],
        "elements": [" ".join(map(str,(i,body,404,*ids))) for i,(body,*ids) in enumerate(cells,1)],
        "boundary": [f"{i} 3 {parent} 0 101 {node}" for i,(node,parent) in enumerate(supports.items(),1)],
    }
    for name,lines in rows.items():
        (directory/f"mesh.{name}").write_text("\n".join(lines)+"\n",encoding="ascii")

def solve_housing(case, design, mesh_data, result_path):
    g,s = case["geometry"],case["structural_model"]
    props = (s["young_modulus_pa"],s["poisson_ratio"],s["density_kg_m3"])
    materials = [(t,*props,0,0) for t in (g["slab_thickness_m"],*design)]
    force = case["loads"]["wind_pressure_pa"] * WIDTH * g["storey_height_m"]
    load_y = force / (SLAB_AREA * g["slab_thickness_m"])
    solve_shell_structure(result_path,result_path,s,0,0,0,body_materials=materials,
                          native_mesh=lambda path: native_mesh(path,mesh_data),
                          body_force_y={1:load_y})
    add_displacement_vector(result_path)

def emblem_profiles():
    angles = [pi*(58+197*i/24)/180 for i in range(25)]
    blade = [(0.66*cos(a),0.08+0.66*sin(a)) for a in angles]
    inner = [(r*cos(a),0.08+r*sin(a)) for i,a in enumerate(angles)
             for r in [0.66-0.22*(i/24)**0.65]]
    sickle = blade + [(.34,-.72),(.42,-.59)] + list(reversed(inner[1:]))
    profile = [(0,-.075),(1.23,-.075),(1.23,-.32),(1.46,-.32),
               (1.46,.32),(1.23,.32),(1.23,.075),(0,.075)]
    hammer = [(-.51+.65*u-.76*v,-.61+.76*u+.65*v) for u,v in profile]
    return (("Sickle",sickle,0,"#953a27"),("Hammer",hammer,.05,"#a6412b"))

def housing_cad(case, design):
    g = case["geometry"]
    n,h = g["storeys"],g["storey_height_m"]
    building = cq.Assembly(name="Brutalist_housing")
    concrete, facade = cq.Color(.61,.59,.54),cq.Color(.72,.69,.61)
    glass, relief = cq.Color(.16,.22,.23),cq.Color(.52,.20,.13)

    def box(x,y,z,dx,dy,dz,name,color):
        shape = cq.Solid.makeBox(*(1000*v for v in (dx,dy,dz)),cq.Vector(*(1000*v for v in (x,y,z))))
        building.add(shape,name=name,color=color)

    for i in range(n):
        for j,runs in enumerate(wall_runs()):
            t = design[2*band(i,n)+j]
            for k,((a,b),(c,d)) in enumerate(runs):
                if a == c:
                    origin,sizes = (a-t/2,min(b,d)),(t,abs(b-d))
                else:
                    origin,sizes = (min(a,c),b-t/2),(abs(a-c),t)
                if j == 0 and a == c:
                    start, end = ACCESS_Y
                    box(origin[0],origin[1],i*h,t,start-origin[1],h,f"Wall_{i}_{j}_{k}_lower_y",concrete)
                    box(origin[0],end,i*h,t,origin[1]+sizes[1]-end,h,f"Wall_{i}_{j}_{k}_upper_y",concrete)
                    box(origin[0],start,i*h+ACCESS_HEIGHT,t,end-start,h-ACCESS_HEIGHT,
                        f"Wall_{i}_{j}_{k}_above_access",concrete)
                else:
                    box(*origin,i*h,*sizes,h,f"Wall_{i}_{j}_{k}",concrete)
        z = (i+1)*h-g["slab_thickness_m"]/2
        for j,(x,y,w,d) in enumerate(((-10,-5,8,10),(2,-5,8,10),(-2,-5,4,3),(-2,2,4,3))):
            box(x,y,z,w,d,g["slab_thickness_m"],f"Slab_{i}_{j}",concrete)
        for side,y in enumerate((-5.45,5.0)):
            box(-10.35,y,z-.53,20.7,.45,.82,f"Spandrel_{side}_{i}",facade)
            for j,x in enumerate(range(-10,11,2)):
                fin = .58 if j in (0,5,10) else .34
                box(x-fin/2,y-.12 if side == 0 else y,i*h,fin,.57,h,f"Fin_{side}_{i}_{j}",facade)
            for j,x in enumerate(range(-10,10,2)):
                if i == 0 and x in (-2,0):
                    continue
                glass_y = y+.39 if side == 0 else y+.015
                box(x+.17,glass_y,i*h+.14,1.66,.04,h-.76,f"Glazing_{side}_{i}_{j}",glass)
    box(-10.45,-5.60,n*h+.12,20.9,11.2,.48,"Crown",facade)
    box(-2.7,-6.35,2.50,5.4,1.40,.48,"Entrance_canopy",facade)
    for i in range(3):
        box(-2.8+i*.15,-6.65+i*.27,-.12,5.6-i*.30,1.28-i*.27,.12*(i+1),
            f"Plinth_step_{i}",concrete)
    box(-2,-5.52,3.17,4,.3,2.44,"Entrance_plaque",concrete)
    for name,profile,offset,_ in emblem_profiles():
        plane = cq.Plane(origin=(0,-1000*(5.52+offset),4300),xDir=(1,0,0),normal=(0,-1,0))
        solid = cq.Workplane(plane).polyline([(1550*x,1550*z) for x,z in profile]).close().extrude(55)
        building.add(solid,name=name,color=relief)
    return building

def housing_view_geometry(case, design):
    parts = []
    for shape, name, _, _ in housing_cad(case,design):
        part = name.rsplit("/",1)[-1]
        material = ("housingGlass" if part.startswith("Glazing") else
                    "emblem" if part == "Sickle" else
                    "emblemHammer" if part == "Hammer" else
                    "emblemBacking" if part == "Entrance_plaque" else
                    "wall" if part.startswith("Wall_") else "roof")
        points, faces = shape.tessellate(1.0)
        parts.append({"material":material,
                      "points":[round(v/1000,5) for point in points for v in point.toTuple()],
                      "faces":faces})
    return parts

def draw_case(stem,case,*,design=None):
    check(case)
    g=case["geometry"]
    n,h = g["storeys"],g["storey_height_m"]
    def sheet(suffix,title,ref,items):
        write_sheet(stem.with_name(stem.name+f"-{suffix}.svg"),title,ref,items,"Brutalist Housing Block")

    def rect(x,y,w,d,style="roof"):
        return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{d:g}" class="{style}"/>'

    scale=29
    x,y=480,375
    thickness = g["baseline_thickness_m"] if design is None else design[2]
    outer = (CORE + thickness) * scale
    inner = (CORE - thickness) * scale
    plan = [rect(x-10*scale,y-5*scale,20*scale,10*scale)]
    for size in (outer, inner):
        fill = "#203d46" if size == outer else "#f9f8f4"
        plan.append(f'<rect x="{x-size/2:g}" y="{y-size/2:g}" width="{size:g}" height="{size:g}" fill="{fill}"/>')
    for u in (-10,10):
        plan.append(line(x+u*scale,y-5*scale,x+u*scale,y+5*scale,"ground"))
    for a,b in ((-10,-outer/2/scale),(outer/2/scale,10)):
        plan.append(line(x+a*scale,y,x+b*scale,y,"ground"))
    for a,letter in ((-6,"Apartment A"),(6,"Apartment B")):
        plan.append(label(x+a*scale,y-72,letter,anchor="middle"))
    stair_left, stair_top = x-1.25*scale, y+.69*scale
    stair_width, stair_depth = 2.5*scale, .95*scale
    plan.append(rect(stair_left,stair_top,stair_width,stair_depth))
    for step in range(1,8):
        tread = stair_left+step*stair_width/8
        plan.append(line(tread,stair_top,tread,stair_top+stair_depth,"extension"))
    arrow_y = stair_top+stair_depth/2
    arrow_end = stair_left+stair_width-8
    plan.extend((line(stair_left+8,arrow_y,arrow_end,arrow_y,"ground"),
                 line(arrow_end-4,arrow_y-4,arrow_end,arrow_y,"ground"),
                 line(arrow_end-4,arrow_y+4,arrow_end,arrow_y,"ground")))

    lift_width = 1.45*scale
    plan.append(rect(x-lift_width/2,y-1.62*scale,lift_width,1.25*scale))
    plan.append(label(x,y-.83*scale,"Lift",anchor="middle"))
    for side in (-1,1):
        door_x = min(x+side*outer/2,x+side*inner/2)
        plan.append(f'<rect x="{door_x:g}" y="{y-ACCESS_Y[1]*scale:g}" '
                    f'width="{thickness*scale:g}" height="{(ACCESS_Y[1]-ACCESS_Y[0])*scale:g}" fill="#f9f8f4"/>')
    plan.append(label(x,y+outer/2+24,"Shared core",anchor="middle"))
    plan+=dimension(x-10*scale,y-5*scale,x+10*scale,y-5*scale,-43,WIDTH)
    plan+=dimension(x+10*scale,y-5*scale,x+10*scale,y+5*scale,45,DEPTH)
    sheet("plan","Typical floor plan","BH-01",plan)

    scale=min(380/(n*h),25)
    base,left=570,480-WIDTH*scale/2
    elevation=[]
    for i in range(n):
        top=base-(i+1)*h*scale
        elevation.append(rect(left,top,WIDTH*scale,h*scale))
        for j in range(10):
            if i == 0 and j in (4,5):
                continue
            elevation.append(rect(left+(2*j+.27)*scale,top+.48*scale,1.46*scale,1.85*scale,"wall"))
    elevation += [rect(480-2.5*scale,base-2.97*scale,5*scale,.42*scale,"wall"),
                  rect(480-2*scale,base-5.61*scale,4*scale,2.44*scale)]
    for _,profile,_,color in emblem_profiles():
        coords = " ".join(f"{480+1.55*x*scale:g},{base-(4.30+1.55*z)*scale:g}" for x,z in profile)
        elevation.append(f'<polygon points="{coords}" fill="{color}"/>')
    elevation+=dimension(left+WIDTH*scale,base-n*h*scale,left+WIDTH*scale,base,55,n*h)
    elevation.append(label(left+WIDTH*scale/2,base+35,f"{n} storeys · Two apartments per storey",anchor="middle"))
    sheet("elevation","Entrance elevation","BH-02",elevation)

    section=[line(left,base,left+WIDTH*scale,base,"ground")]
    for i in range(n):
        top=base-(i+1)*h*scale
        section.append(line(left,top,left+WIDTH*scale,top,"ground"))
        core_thickness = g["baseline_thickness_m"] if design is None else design[2*band(i,n)]
        for wall_x in (480-CORE*scale/2,480+CORE*scale/2):
            section.append(rect(wall_x-core_thickness*scale/2,top,
                                core_thickness*scale,(h-ACCESS_HEIGHT)*scale))
    bracket = left + WIDTH * scale + 14
    for index, name in enumerate(("Lower band", "Middle band", "Upper band")):
        floors = [i+1 for i in range(n) if band(i,n) == index]
        top = base - floors[-1] * h * scale
        bottom = base - (floors[0]-1) * h * scale
        section += [line(bracket,top,bracket,bottom,"extension"),
                    line(bracket-4,top,bracket+4,top,"ground"),
                    line(bracket-4,bottom,bracket+4,bottom,"ground"),
                    label(bracket+12,(top+bottom)/2+4,
                          f"{name} · Storeys {floors[0]}–{floors[-1]}")]
    section+=dimension(left,base-n*h*scale,left,base,-45,n*h)
    sheet("section","Section through the core accesses","BH-03",section)

def run_case(stem,step,mesh,result,case):
    draw_case(stem,case)
    design = [case["geometry"]["baseline_thickness_m"]]*6
    export_step(housing_cad(case,design),step)
    solve_housing(case,design,housing_mesh(case,mesh),result)
