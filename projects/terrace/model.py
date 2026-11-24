from math import ceil, cos, hypot, isfinite, pi, sin, sqrt

import cadquery as cq
import gmsh

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from common.elmer import add_displacement_vector
from common.shell_solver import solve_shell_structure

WALL_THICKNESS = .35
WALL_BELOW = 1.25
WALL_ABOVE = 2.55
DOOR_WIDTH = 1.40
DOOR_HEIGHT = 2.12
RAIL_HEIGHT = 1.05
RAIL_SETBACK = .055
HANDRAIL_WIDTH = .04
HANDRAIL_DEPTH = .03
POST_DIAMETER = .014
POST_SPACING = .13
STEEL_DENSITY = 7850
RIGIDITY_BANDS = 24

def check(case):
    g, steel, concrete = (case[key] for key in ("geometry", "reinforcement", "structural_model"))
    values = (*g.values(), *steel.values(), concrete["tensile_strength_pa"], case["loads"]["surface_pressure_pa"])
    if not all(isfinite(value) and value > 0 for value in values):
        raise ValueError("Terrace dimensions, properties and pressure must be positive and finite.")
    if g["radius_m"] <= DOOR_WIDTH/2:
        raise ValueError("The balcony diameter must exceed the access width.")
    if steel["top_axis_depth_m"] >= g["slab_thickness_m"]/2:
        raise ValueError("The reinforcement axis must be above the slab mid-plane.")

def section(case):
    t = case["geometry"]["slab_thickness_m"]
    concrete, steel = case["structural_model"], case["reinforcement"]
    gross = t**3/12
    cracking = concrete["tensile_strength_pa"]*gross/(t/2)
    d = t-steel["top_axis_depth_m"]
    area = steel["top_area_mm2_per_m"]*1e-6
    transformed = area*steel["young_modulus_pa"]/concrete["young_modulus_pa"]
    neutral = sqrt(transformed**2+2*transformed*d)-transformed
    cracked = neutral**3/3+transformed*(d-neutral)**2
    return cracking, cracked/gross

def strip_pressure(case):
    g, s = case["geometry"],case["structural_model"]
    return case["loads"]["surface_pressure_pa"] + g["slab_thickness_m"]*s["density_kg_m3"]*s["gravity_m_s2"]

def railing(radius):
    rail_radius = radius-RAIL_SETBACK
    count = ceil(pi*rail_radius/POST_SPACING)-1
    positions = [pi*i/(count+1) for i in range(1,count+1)]
    return rail_radius,positions

def railing_mass(case):
    radius,positions = railing(case["geometry"]["radius_m"])
    handrail = pi*radius*HANDRAIL_WIDTH*HANDRAIL_DEPTH
    posts = len(positions)*pi*POST_DIAMETER**2/4*(RAIL_HEIGHT-HANDRAIL_DEPTH)
    return (handrail+posts)*STEEL_DENSITY

def edge_weight(case):
    return railing_mass(case)*case["structural_model"]["gravity_m_s2"]/(pi*case["geometry"]["radius_m"])

def strip_edge_force(case, span):
    return edge_weight(case)*case["geometry"]["radius_m"]/span

def terrace_cad(case):
    g = case["geometry"]
    r, t = 1000*g["radius_m"],1000*g["slab_thickness_m"]
    slab = (cq.Workplane("XY", origin=(0,0,-t/2)).moveTo(-r,0).lineTo(r,0)
            .threePointArc((0,r),(-r,0)).close().extrude(t))
    wall_bottom = t/2-1000*WALL_BELOW
    wall = cq.Solid.makeBox(2*r,1000*WALL_THICKNESS,1000*(WALL_BELOW+WALL_ABOVE),
                           cq.Vector(-r,-1000*WALL_THICKNESS,wall_bottom))
    door_width,door_height = 1000*DOOR_WIDTH,1000*DOOR_HEIGHT
    opening = cq.Solid.makeBox(door_width,1000*WALL_THICKNESS+2,door_height,
                              cq.Vector(-door_width/2,-1000*WALL_THICKNESS-1,t/2))
    door = cq.Solid.makeBox(door_width,45,door_height,cq.Vector(-door_width/2,-95,t/2))
    assembly = cq.Assembly(name="Concrete_balcony")
    assembly.add(slab, name="Terrace_slab", color=cq.Color(.78,.77,.72))
    assembly.add(wall.cut(opening), name="Support_context", color=cq.Color(.65,.63,.57))
    assembly.add(door, name="Door_context", color=cq.Color(.24,.32,.34))
    rail_radius,positions = railing(g["radius_m"])
    inner,outer = (1000*(rail_radius+offset) for offset in (-HANDRAIL_WIDTH/2,HANDRAIL_WIDTH/2))
    post_height = 1000*(RAIL_HEIGHT-HANDRAIL_DEPTH)
    rail = (cq.Workplane("XY",origin=(0,0,t/2+post_height))
            .moveTo(-outer,0).threePointArc((0,outer),(outer,0)).lineTo(inner,0)
            .threePointArc((0,inner),(-inner,0)).close().extrude(1000*HANDRAIL_DEPTH))
    steel = cq.Color(.20,.24,.24)
    assembly.add(rail,name="Railing_handrail",color=steel)
    for i,angle in enumerate(positions):
        origin = cq.Vector(1000*rail_radius*cos(angle),1000*rail_radius*sin(angle),t/2)
        post = cq.Solid.makeCylinder(500*POST_DIAMETER,post_height,origin)
        assembly.add(post,name=f"Railing_post_{i}",color=steel)
    return assembly

def draw_case(stem, case):
    check(case)
    r,t = (case["geometry"][key] for key in ("radius_m","slab_thickness_m"))
    x,y,scale = 480,280,min(102,300/r)
    radius = r*scale
    left,right = x-radius,x+radius
    span = f'<path d="M{left:g} {y:g} A{radius:g} {radius:g} 0 0 0 {right:g} {y:g} Z" class="roof"/>'
    rail_radius,positions = railing(r)
    rail_px = rail_radius*scale
    plan = [span, line(left,y,right,y,"cut"),
            f'<path d="M{x-rail_px:g} {y:g} A{rail_px:g} {rail_px:g} 0 0 0 {x+rail_px:g} {y:g}" fill="none" class="ground"/>',
            line(x-DOOR_WIDTH*scale/2,y,x+DOOR_WIDTH*scale/2,y,"glass-line"),
            label(x,y-55,"Fixed edge",anchor="middle"),
            *dimension(left,y,right,y,-29,2*r),
            *dimension(x,y,x,y+radius,36,r)]
    write_sheet(stem.with_name(stem.name+"-plan.svg"),"Balcony plan","CT-01",plan,"Concrete Balcony")
    elevation_scale = min(scale,103)
    radius_px = r*elevation_scale
    left,right = x-radius_px,x+radius_px
    deck_y = 419
    wall_top = deck_y-WALL_ABOVE*elevation_scale
    base = deck_y+WALL_BELOW*elevation_scale
    door_px = DOOR_WIDTH*elevation_scale
    door_height = DOOR_HEIGHT*elevation_scale
    rail_y = deck_y-RAIL_HEIGHT*elevation_scale
    elevation = [f'<rect x="{left:g}" y="{wall_top:g}" width="{2*radius_px:g}" height="{base-wall_top:g}" class="roof"/>',
                 f'<rect x="{x-door_px/2:g}" y="{deck_y-door_height:g}" width="{door_px:g}" height="{door_height:g}" class="glass"/>',
                 f'<rect x="{left:g}" y="{deck_y:g}" width="{2*radius_px:g}" height="{t*elevation_scale:g}" class="wall"/>',
                 line(x-rail_radius*elevation_scale,rail_y,x+rail_radius*elevation_scale,rail_y,"ground")]
    for angle in positions:
        post_x = x+rail_radius*cos(angle)*elevation_scale
        elevation.append(line(post_x,rail_y,post_x,deck_y,"ground"))
    elevation += dimension(left,base,right,base,31,2*r)
    write_sheet(stem.with_name(stem.name+"-elevation.svg"),"Front elevation","CT-02",elevation,"Concrete Balcony")
    origin, top = 310,396
    bottom = top+t*scale
    wall_depth = WALL_THICKNESS*scale
    door_head = top-DOOR_HEIGHT*scale
    wall_top = top-WALL_ABOVE*scale
    section = [f'<rect x="{origin-wall_depth:g}" y="{top}" width="{wall_depth:g}" height="{WALL_BELOW*scale:g}" class="roof"/>',
               f'<rect x="{origin-wall_depth:g}" y="{wall_top:g}" width="{wall_depth:g}" height="{door_head-wall_top:g}" class="roof"/>',
               f'<rect x="{origin}" y="{top}" width="{radius:g}" height="{t*scale:g}" class="roof"/>',
               line(origin-.08*scale,door_head,origin-.08*scale,top,"glass-line"),
               line(origin,top,origin,bottom,"cut"),
               line(origin+rail_px,top-RAIL_HEIGHT*scale,origin+rail_px,top,"ground"),
               *dimension(origin,bottom,origin+radius,bottom,51,r),
               *dimension(origin+radius,top,origin+radius,bottom,37,t,millimetres=True)]
    steel_y = top+case["reinforcement"]["top_axis_depth_m"]*scale
    section.extend((line(origin-wall_depth/2,steel_y,origin+radius-.12*scale,steel_y,"ground"),
                    line(origin+radius*.45,steel_y,origin+radius*.45,top-63,"extension"),
                    label(origin+radius*.45,top-69,"Top reinforcement perpendicular to fixed edge",anchor="middle")))
    write_sheet(stem.with_name(stem.name+"-section.svg"),"Centreline section","CT-03",section,"Concrete Balcony")

def terrace_mesh(case, path):
    r = case["geometry"]["radius_m"]
    size = case["mesh"]["element_size_m"]
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal",0)
        gmsh.model.add("terrace")
        geo = gmsh.model.geo
        centre = geo.addPoint(0,0,0,size)
        right = geo.addPoint(r,0,0,size)
        front = geo.addPoint(0,r,0,size)
        left = geo.addPoint(-r,0,0,size)
        edge = [geo.addLine(left,centre),geo.addLine(centre,right)]
        arcs = [geo.addCircleArc(right,centre,front),geo.addCircleArc(front,centre,left)]
        surface = geo.addPlaneSurface([geo.addCurveLoop([*edge,*arcs])])
        geo.synchronize()
        gmsh.model.mesh.generate(2)
        tags, coordinates, _ = gmsh.model.mesh.getNodes()
        points = {int(tag):tuple(coordinates[i:i+3]) for tag,i in zip(tags,range(0,len(coordinates),3),strict=True)}
        _, _, triangles = gmsh.model.mesh.getElements(2,surface)
        _, _, edges = gmsh.model.mesh.getElements(1)
    finally:
        gmsh.finalize()

    cracking, ratio = section(case)
    q = strip_pressure(case)
    bands = {}
    cells = []
    for batch in triangles:
        for i in range(0,len(batch),3):
            nodes = batch[i:i+3]
            x,y = (sum(points[int(n)][axis] for n in nodes)/3 for axis in (0,1))
            span = sqrt(r*r-x*x)
            arm = span-y
            moment = q*arm**2/2 + strip_edge_force(case,span)*arm
            weight = max(0, 1-(cracking/moment)**2) if moment else 0
            band = round(weight*RIGIDITY_BANDS)
            body = bands.setdefault(band, len(bands)+4)
            cells.append((2,body,*nodes))
    edge_weights = {}
    for batch in edges:
        for i in range(0,len(batch),2):
            a,b = batch[i:i+2]
            pa,pb = points[int(a)],points[int(b)]
            if abs(pa[1])+abs(pb[1]) < 1e-9:
                cells.append((1,3,a,b))
            else:
                half_length = hypot(*(v-u for u,v in zip(pa,pb,strict=True)))/2
                edge_weights[a] = edge_weights.get(a,0)+half_length
                edge_weights[b] = edge_weights.get(b,0)+half_length
    rows = ["$MeshFormat","2.2 0 8","$EndMeshFormat","$Nodes",str(len(points))]
    rows.extend(f"{tag} {x:.12g} {y:.12g} {z:.12g}" for tag,(x,y,z) in points.items())
    rows.extend(("$EndNodes","$Elements",str(len(cells))))
    rows.extend(" ".join(map(str,(i,kind,2,body,body,*nodes)))
                for i,(kind,body,*nodes) in enumerate(cells,1))
    path.write_text("\n".join([*rows,"$EndElements",""]),encoding="ascii")
    rail_force = railing_mass(case)*case["structural_model"]["gravity_m_s2"]
    force_per_m = rail_force/sum(edge_weights.values())
    point_loads = [(*points[int(node)],-force_per_m*weight) for node,weight in edge_weights.items()]
    return {body:1/(1-band/RIGIDITY_BANDS+band/RIGIDITY_BANDS/ratio) for band,body in bands.items()}, point_loads

def run_case(stem, step, mesh, result, case):
    draw_case(stem,case)
    export_step(terrace_cad(case),step)
    factors, point_loads = terrace_mesh(case,mesh)
    t = case["geometry"]["slab_thickness_m"]
    s = case["structural_model"]
    pressure = case["loads"]["surface_pressure_pa"]
    def material(factor):
        return (t,s["young_modulus_pa"]*factor,s["poisson_ratio"],s["density_kg_m3"],pressure,0)
    materials = [material(1)]*3 + [material(factor) for factor in factors.values()]
    solve_shell_structure(mesh,result,s,t,t,pressure,body_materials=materials,
                          point_loads=point_loads,calculate_loads=True)
    add_displacement_vector(result)

def write_cracking_map(path, case):
    r = case["geometry"]["radius_m"]
    cracking, _ = section(case)
    q = strip_pressure(case)
    root_limit = sqrt(2*max(0,cracking-edge_weight(case)*r)/q)
    cracked_half_width = sqrt(max(0,r*r-root_limit**2))
    scale, x, y = 130/r, 280, 48
    zone = ""
    if cracked_half_width:
        points = []
        for i in range(81):
            u = cracked_half_width*(i/40-1)
            span = sqrt(r*r-u*u)
            p = strip_edge_force(case,span)
            clear_length = 2*cracking/(sqrt(p*p+2*q*cracking)+p)
            depth = max(0,span-clear_length)
            points.append(f"{x+u*scale:.2f},{y+depth*scale:.2f}")
        zone = f'<polygon points="{" ".join(points)}" fill="#a46135"/>'
    path.write_text(f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 211" role="img" aria-labelledby="title">
<title id="title">Estimated top-face cracking near the fixed edge</title>
<rect width="560" height="211" fill="#f9f8f4"/>
<text x="{x}" y="31" text-anchor="middle" font-family="Arial" font-size="13" fill="#26383b">Fixed edge</text>
<path d="M150 {y} A130 130 0 0 0 410 {y} Z" fill="#e3eae6" stroke="#74908c"/>
{zone}
<path d="M150 {y}H410" stroke="#465764" stroke-width="2"/>
<rect x="126" y="190" width="14" height="12" fill="#a46135"/>
<text x="147" y="200" font-family="Arial" font-size="13" fill="#26383b">Estimated top-face cracking under study load</text>
</svg>""",encoding="utf-8")
