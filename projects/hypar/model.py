from math import ceil, hypot, isfinite

import cadquery as cq

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from common.elmer import add_displacement_vector
from common.shell_solver import CIRCULAR_TUBE, solve_shell_structure

WALL_DEPTH, WALL_EXTENSION = .55, 1.6
WALL_BASE, WALL_TOP = -3.8, 1.6
DOOR_WIDTH, DOOR_HEIGHT = 1.0, 2.1

def check(case):
    g = case["geometry"]
    if not all(isfinite(v) and v > 0 for v in g.values()):
        raise ValueError("Hypar dimensions must be finite and positive.")
    if 2 * g["tube_wall_m"] >= min(g["tube_depth_m"],g["tube_width_m"]):
        raise ValueError("The tube must have a hollow section.")
    if not all(isfinite(v) and v >= 0 for v in case["loads"].values()):
        raise ValueError("Uplift values must be finite and non-negative.")

def dimensions(g):
    return g["projection_m"], g["width_m"]/2, g["tip_rise_m"]

def height(g, x, y):
    length, half, rise = dimensions(g)
    return rise * (x / length) * (y / half)

def corners(g):
    length, half, rise = dimensions(g)
    return [(0, -half, 0), (length, -half, -rise), (length, half, rise), (0, half, 0)]

def hypar_cad(g):
    model = cq.Assembly(name="Steel_hypar")
    t = g["plate_thickness_m"]
    depth, width, wall = (1000*g[k] for k in ("tube_depth_m","tube_width_m","tube_wall_m"))

    def edge(a, b, offset):
        return cq.Edge.makeLine(cq.Vector(a[0]*1000, a[1]*1000, (a[2]+offset)*1000),
                                cq.Vector(b[0]*1000, b[1]*1000, (b[2]+offset)*1000))

    a, b, c, d = corners(g)
    face = cq.Face.makeRuledSurface(edge(a, b, -t/2), edge(d, c, -t/2))
    plate = face.thicken(1000*t)
    model.add(plate, name="Skin", color=cq.Color(0.64, 0.72, 0.74))
    for i, (p, q) in enumerate(((a,b), (b,c), (c,d)), 1):
        line = edge(p, q, 0)
        origin, axis = line.startPoint(), line.endPoint() - line.startPoint()
        direction = axis.normalized()
        plane = cq.Plane(origin=origin, xDir=direction.cross(cq.Vector(0,0,1)), normal=direction)
        tube = cq.Workplane(plane).rect(width,depth).rect(width-2*wall,depth-2*wall).extrude(axis.Length)
        model.add(tube, name=f"Edge_tube_{i}", color=cq.Color(0.26, 0.33, 0.36))
    half = g["width_m"]/2 + WALL_EXTENSION
    wall_context = cq.Solid.makeBox(1000*WALL_DEPTH,2000*half,1000*(WALL_TOP-WALL_BASE),
                                    cq.Vector(-1000*WALL_DEPTH,-1000*half,1000*WALL_BASE))
    recess = cq.Solid.makeBox(130, 1000*DOOR_WIDTH, 1000*DOOR_HEIGHT+1,
                             cq.Vector(-120, -500*DOOR_WIDTH, 1000*WALL_BASE-1))
    door = cq.Solid.makeBox(40, 1000*DOOR_WIDTH-70, 1000*DOOR_HEIGHT-35,
                            cq.Vector(-100, -500*DOOR_WIDTH+35, 1000*WALL_BASE))
    model.add(wall_context.cut(recess), name="Wall_context", color=cq.Color(.63,.61,.55))
    model.add(door, name="Door_context", color=cq.Color(.30,.33,.31))
    return model

def surface_cells(case):
    g = case["geometry"]
    length, half, _ = dimensions(g)
    size = case["mesh"]["element_size_m"]
    nx, ny = ceil(length / size), 2 * ceil(half / size)
    grid = [[(length*i/nx, half*(2*j-ny)/ny, height(g, length*i/nx, half*(2*j-ny)/ny))
             for j in range(ny+1)] for i in range(nx+1)]
    plates, tubes = [], []
    for i in range(nx):
        for j in range(ny):
            plates.append((3 if j < ny/2 else 4,
                           (grid[i][j], grid[i+1][j], grid[i+1][j+1], grid[i][j+1])))
        tubes.extend(((grid[i][0], grid[i+1][0]), (grid[i][-1], grid[i+1][-1])))
    tubes.extend(zip(grid[-1], grid[-1][1:]))
    return plates, tubes, grid[0]

def hypar_mesh(path, case):
    plates, tubes, fixed = surface_cells(case)
    nodes, cells = {}, []

    def cell(kind, body, points):
        ids = [nodes.setdefault(point, len(nodes)+1) for point in points]
        cells.append((kind, body, *ids))

    for body, points in plates:
        cell(3, body, points)
    for points in tubes:
        cell(1, 2, points)
    for point in fixed:
        cell(15, 3, [point])
    rows = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$PhysicalNames", "4",
            '2 3 "left_skin"', '2 4 "right_skin"', '1 2 "edge_profiles"', '0 3 "wall_fixity"',
            "$EndPhysicalNames", "$Nodes", str(len(nodes))]
    rows.extend(f"{i} {x} {y} {z}" for (x,y,z),i in nodes.items())
    rows.extend(("$EndNodes", "$Elements", str(len(cells))))
    rows.extend(" ".join(map(str, (i,kind,2,group,kind*10+group,*ids)))
                for i,(kind,group,*ids) in enumerate(cells,1))
    path.write_text("\n".join([*rows,"$EndElements",""]), encoding="ascii")

def wall_moment(case):
    g, settings, loads = (case[k] for k in ("geometry", "structural_model", "loads"))
    t, depth, width, wall = (g[k] for k in ("plate_thickness_m", "tube_depth_m","tube_width_m","tube_wall_m"))
    weight = settings["density_kg_m3"] * settings["gravity_m_s2"]
    length, half, rise = dimensions(g)
    pressure = {3: loads["left_uplift_pa"], 4: loads["right_uplift_pa"]}
    plates, tubes, _ = surface_cells(case)
    moment = 0
    for body, (a, b, c, _) in plates:
        x, y = (a[0]+c[0])/2, (a[1]+c[1])/2
        area = (b[0]-a[0])*(c[1]-b[1]) * hypot(1, rise*y/(length*half), rise*x/(length*half))
        moment += (pressure[body]-weight*t)*area*x
    tube_area = depth*width - (depth-2*wall)*(width-2*wall)
    for a,b in tubes:
        moment -= weight*tube_area*hypot(*(q-p for p,q in zip(a,b,strict=True)))*(a[0]+b[0])/2
    return moment / 1000

def draw_case(stem, case):
    check(case)
    g = case["geometry"]
    length, half, rise = dimensions(g)
    width = 2*half
    scale = min(88, 730/(width+2*WALL_EXTENSION), 310/length, 135/rise, 248/-WALL_BASE)
    left, wall = 480-scale*half, 235
    right, front = left+scale*width, wall+scale*length

    def draw(suffix,title,number,elements):
        write_sheet(stem.with_name(stem.name+f"-{suffix}.svg"), title, number, elements, "Steel Hypar")

    def area(points, style="roof"):
        coords = " ".join(f"{x:g},{y:g}" for x,y in points)
        return f'<polygon points="{coords}" class="{style}"/>'

    middle = (left+right)/2
    wall_left, wall_right = left-WALL_EXTENSION*scale,right+WALL_EXTENSION*scale
    wall_back = wall-WALL_DEPTH*scale
    plan = [area([(wall_left,wall_back),(wall_right,wall_back),(wall_right,wall),(wall_left,wall)],"roof"),
            area([(left,wall),(right,wall),(right,front),(left,front)]),
            line(left,wall,right,wall,"cut"), line(middle,wall,middle,front,"extension"),
            label(middle,wall_back-12,"Fixed horizontal wall edge",anchor="middle"),
            label((left+middle)/2,(wall+front)/2,"Left wind zone",anchor="middle"),
            label((middle+right)/2,(wall+front)/2,"Right wind zone",anchor="middle")]
    plan += dimension(left,front,right,front,31,width)
    plan += dimension(right,wall,right,front,37,length)
    draw("plan","Canopy plan","A-01",plan)

    datum = 380
    dz = scale*rise
    top, bottom = datum-WALL_TOP*scale, datum-WALL_BASE*scale
    door_left, door_right = middle-DOOR_WIDTH*scale/2, middle+DOOR_WIDTH*scale/2
    door_top = bottom-DOOR_HEIGHT*scale
    elevation = [area([(wall_left,top),(wall_right,top),(wall_right,bottom),(wall_left,bottom)]),
                 area([(door_left,door_top),(door_right,door_top),(door_right,bottom),(door_left,bottom)],"wall"),
                 area([(left,datum+dz),(middle,datum),(right,datum-dz),(right,datum),(left,datum)]),
                 line(left,datum,right,datum,"cut"), line(left,datum+dz,right,datum-dz,"ground")]
    elevation += dimension(right,datum-dz,right,datum,56,rise)
    elevation += dimension(left,datum,left,datum+dz,-44,rise)
    draw("elevation","Front elevation","A-02",elevation)

    root, tip = 260, 260+scale*length
    wall_back = root-WALL_DEPTH*scale
    top,bottom = datum-WALL_TOP*scale,datum-WALL_BASE*scale
    section = [area([(wall_back,top),(root,top),(root,bottom),(wall_back,bottom)]),
               line(root,top,root,bottom,"cut"),
               line(root,datum,tip,datum-dz,"ground"),
               label(root+12,datum+100,"Fixed wall edge"),
               label(tip+14,datum-dz,
                     f'RHS {1000*g["tube_depth_m"]:g} × {1000*g["tube_width_m"]:g} × {1000*g["tube_wall_m"]:g} mm'),
               label((root+tip)/2,datum+28,f'{1000*g["plate_thickness_m"]:g} mm steel skin',anchor="middle")]
    section += dimension(root,datum+100,tip,datum+100,48,length)
    draw("section","Section along high edge","A-03",section)

def run_case(stem, step, mesh, result, case):
    draw_case(stem, case)
    g, s, loads = (case[k] for k in ("geometry", "structural_model", "loads"))
    export_step(hypar_cad(g), step)
    hypar_mesh(mesh, case)
    steel = (s["young_modulus_pa"], s["poisson_ratio"], s["density_kg_m3"])
    skin, tube, wall = (g[k] for k in ("plate_thickness_m","tube_depth_m","tube_wall_m"))
    materials = [(skin,*steel,0,0), (tube,*steel,0,wall),
                 (skin,*steel,-loads["left_uplift_pa"],0), (skin,*steel,-loads["right_uplift_pa"],0)]
    solve_shell_structure(mesh,result,s,0,0,0,body_materials=materials,beam_source=CIRCULAR_TUBE,
                          beam_widths={2:g["tube_width_m"]})
    add_displacement_vector(result)
