from pathlib import Path
from math import ceil, cos, isfinite, pi, radians, sin
from shutil import copyfile
import subprocess
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

import cadquery as cq
import numpy as np

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from common.elmer import elmer_runtime

LANDING_LENGTH = 1.65
LANDING_DEPTH = .36
GUARD_HEIGHT = 1.08
GLASS_HEIGHT = .91
GLASS_THICKNESS = .012
POST_WIDTH = .03
CAP_WIDTH = .045
CAP_DEPTH = .025
PANEL_GAP = .055
GLASS_DENSITY = 2500
STEEL_DENSITY = 7850

def guard_layout(g):
    angle = radians(g["angle_deg"])
    return [(across, g["radius_m"] + g["width_m"]*(across-.5),
             ceil(angle*(g["radius_m"] + g["width_m"]*(across-.5))/1.25))
            for across in (.035,.965)]

def guard_mass(g):
    angle = radians(g["angle_deg"])
    total = 0
    for _,radius,bays in guard_layout(g):
        panel_length = 2*radius*sin(angle/(2*bays))-PANEL_GAP
        glass = bays*panel_length*GLASS_HEIGHT*GLASS_THICKNESS
        steel = angle*radius*CAP_WIDTH*CAP_DEPTH + (bays+1)*POST_WIDTH**2*(GUARD_HEIGHT-CAP_DEPTH)
        total += glass*GLASS_DENSITY+steel*STEEL_DENSITY
    return total

def landing_outline(g, end):
    angle = radians(g["angle_deg"])*(end-.5)
    direction = -1 if end == 0 else 1
    dx,dy = (direction*LANDING_LENGTH*v for v in (cos(angle),-sin(angle)))
    a,b = [deck_point(g,end,across)[:2] for across in (0,1)]
    return (a,b,(b[0]+dx,b[1]+dy),(a[0]+dx,a[1]+dy))

def deck_point(g, station, across, z=0):
    angle = radians(g["angle_deg"])*(station-.5)
    radius = g["radius_m"] + g["width_m"]*(across-.5)
    return (radius*sin(angle),radius*cos(angle)-g["radius_m"],z)

def check(case):
    g,h,f = (case[key] for key in ("geometry","hanger","frequency"))
    if not all(isfinite(v) and v > 0 for v in (*g.values(),*h.values(),*f.values())):
        raise ValueError("Walkway dimensions, hanger properties and frequencies must be positive.")
    if not (g["radius_m"] > g["width_m"]/2 and g["angle_deg"] < 180
            and 0 < h["station"] < 1 and f["end_hz"] > f["start_hz"]):
        raise ValueError("Invalid walkway geometry, hanger station or sweep limits.")

def geometry(case):
    g,h = case["geometry"],case["hanger"]
    depth = g["deck_depth_m"]
    def xy(station,across):
        return tuple(1000*v for v in deck_point(g,station,across)[:2])
    deck = (cq.Workplane("XY",origin=(0,0,-500*depth))
            .moveTo(*xy(0,0)).threePointArc(xy(.5,0),xy(1,0)).lineTo(*xy(1,1))
            .threePointArc(xy(.5,1),xy(0,1)).close().extrude(1000*depth))
    x,y,z = deck_point(g,h["station"],.875,depth/2)
    rod = cq.Solid.makeCylinder(500*h["diameter_m"],1000*h["length_m"],cq.Vector(1000*x,1000*y,1000*z))
    model = cq.Assembly(name="Atrium_walkway")
    model.add(deck,name="Deck",color=cq.Color(.75,.74,.70))
    model.add(rod,name="Hanger",color=cq.Color(.29,.33,.33))
    glass = cq.Color(.48,.68,.69,.30)
    steel = cq.Color(.20,.26,.26)
    concrete = cq.Color(.65,.63,.58)

    def prism(outline,z,height):
        return (cq.Workplane("XY",origin=(0,0,1000*z))
                .polyline([(1000*x,1000*y) for x,y in outline]).close().extrude(1000*height))

    for end in (0,1):
        landing = prism(landing_outline(g,end),depth/2-LANDING_DEPTH,LANDING_DEPTH)
        model.add(landing,name=f"Landing_{end}",color=concrete)

    for side,(across,radius,bays) in enumerate(guard_layout(g)):
        for bay in range(bays):
            ax,ay,_ = deck_point(g,bay/bays,across)
            bx,by,_ = deck_point(g,(bay+1)/bays,across)
            length = np.hypot(bx-ax,by-ay)
            ux,uy = (bx-ax)/length,(by-ay)/length
            gap,half = PANEL_GAP/2,GLASS_THICKNESS/2
            outline = [(x+u*ux-v*uy,y+u*uy+v*ux)
                       for x,y,u,v in ((ax,ay,gap,-half),(bx,by,-gap,-half),
                                       (bx,by,-gap,half),(ax,ay,gap,half))]
            panel = prism(outline,depth/2+.10,GLASS_HEIGHT)
            model.add(panel,name=f"Guard_glass_{side}_{bay}",color=glass)
        for post in range(bays+1):
            px,py,pz = deck_point(g,post/bays,across,depth/2)
            column = cq.Solid.makeBox(1000*POST_WIDTH,1000*POST_WIDTH,1000*(GUARD_HEIGHT-CAP_DEPTH),
                                       cq.Vector(1000*(px-POST_WIDTH/2),1000*(py-POST_WIDTH/2),1000*pz))
            model.add(column,name=f"Guard_post_{side}_{post}",color=steel)
        inner,outer = (across+v*CAP_WIDTH/(2*g["width_m"]) for v in (-1,1))
        handrail = (cq.Workplane("XY",origin=(0,0,1000*(depth/2+GUARD_HEIGHT-CAP_DEPTH)))
                    .moveTo(*xy(0,inner)).threePointArc(xy(.5,inner),xy(1,inner)).lineTo(*xy(1,outer))
                    .threePointArc(xy(.5,outer),xy(0,outer)).close().extrude(1000*CAP_DEPTH))
        model.add(handrail,name=f"Guard_cap_{side}",color=steel)

    for name,height,diameter in (("Hanger_socket",z,.065),("Hanger_head",z+h["length_m"]-.14,.09)):
        terminal = cq.Solid.makeCylinder(500*diameter,140,cq.Vector(1000*x,1000*y,1000*height))
        model.add(terminal,name=name,color=steel)
    return model

def draw_case(stem,case):
    check(case)
    g,h = case["geometry"],case["hanger"]
    scale = 575/(2*(g["radius_m"]+g["width_m"]/2)*sin(radians(g["angle_deg"])/2))
    def sheet(suffix,title,number,items):
        write_sheet(stem.with_name(stem.name+f"-{suffix}.svg"),title,number,items,"Atrium Walkway")
    def plan_point(station,across):
        x,y,_ = deck_point(g,station,across)
        return f"{480+scale*x:g} {280-scale*y:g}"
    inner,outer = ((g["radius_m"]+g["width_m"]*(a-.5))*scale for a in (0,1))
    plan = [f'<path d="M{plan_point(0,0)} A{inner:g} {inner:g} 0 0 1 {plan_point(1,0)} '
            f'L{plan_point(1,1)} A{outer:g} {outer:g} 0 0 0 {plan_point(0,1)} Z" class="roof"/>']
    for end in (0,1):
        outline = " ".join(f"{480+scale*x:g},{280-scale*y:g}" for x,y in landing_outline(g,end))
        plan.append(f'<polygon points="{outline}" class="roof"/>')
    for across,radius,_ in guard_layout(g):
        plan.append(f'<path d="M{plan_point(0,across)} A{radius*scale:g} {radius*scale:g} 0 0 1 '
                    f'{plan_point(1,across)}" fill="none" class="ground"/>')
    hx,hy,_ = deck_point(g,h["station"],.875)
    px,py,_ = deck_point(g,.66,.875)
    for x,y,colour,text,offset in ((hx,hy,"#203d46","Hanger",-42),(px,py,"#a46135","Footfall patch",65)):
        x,y=480+x*scale,280-y*scale
        plan.extend([f'<circle cx="{x:g}" cy="{y:g}" r="4" fill="{colour}"/>',
                     line(x,y,x,y+offset*.72,"extension"),label(x,y+offset,text,anchor="middle")])
    end=deck_point(g,1,.5)[0]
    plan+=dimension(480-scale*end,448,480+scale*end,448,32,2*end)
    sheet("plan","Walkway plan","AW-01",plan)
    x=480+hx*scale
    top=511
    rise=h["length_m"]*scale
    depth=g["deck_depth_m"]*scale
    sheet("elevation","Atrium elevation","AW-02",[
        f'<rect x="{480-end*scale:g}" y="{top}" width="{2*end*scale:g}" height="{depth:g}" class="roof"/>',
        line(480-end*scale,top-GUARD_HEIGHT*scale,480+end*scale,top-GUARD_HEIGHT*scale,"ground"),
        *[f'<rect x="{left:g}" y="{top}" width="{LANDING_LENGTH*scale:g}" height="{LANDING_DEPTH*scale:g}" class="roof"/>'
          for left in (480-(end+LANDING_LENGTH)*scale,480+end*scale)],
        line(x,top-rise,x,top,"ground"),line(x-17,top-rise,x+17,top-rise,"ground"),
        *dimension(x,top-rise,x,top,50,h["length_m"])])
    half=g["width_m"]*65
    left,right=480-half,480+half
    depth=g["deck_depth_m"]*130
    sheet("section","Deck section at hanger","AW-03",[
        f'<rect x="{left:g}" y="400" width="{right-left:g}" height="{depth:g}" class="roof"/>',
        line(left+.875*(right-left),230,left+.875*(right-left),400,"ground"),
        *[f'<rect x="{left+a*(right-left)-2:g}" y="{400-GUARD_HEIGHT*130:g}" width="4" height="{GUARD_HEIGHT*130:g}" class="glass"/>'
          for a in (.035,.965)],
        *dimension(left,400+depth,right,400+depth,42,g["width_m"]),
        *dimension(right,400,right,400+depth,58,g["deck_depth_m"],millimetres=True)])

def native_mesh(case, directory, msh):
    g,h,m = (case[key] for key in ("geometry","hanger","mesh"))
    n = max(20,ceil(g["radius_m"]*radians(g["angle_deg"])/m["element_size_m"]))
    w,d = m["width_cells"],m["depth_cells"]
    hanger_station, load_station = h["station"],.66
    half_patch = .014
    stations = sorted({*(i/n for i in range(n+1)),hanger_station-half_patch,hanger_station,
                       hanger_station+half_patch,load_station-half_patch,load_station,load_station+half_patch})
    special = (hanger_station-half_patch,hanger_station,hanger_station+half_patch,
               load_station-half_patch,load_station,load_station+half_patch)
    stations = [s for s in stations if s in special or all(abs(s-t)>.003 for t in special)]
    points = [deck_point(g,s,j/w,g["deck_depth_m"]*(k/d-.5))
              for s in stations for j in range(w+1) for k in range(d+1)]
    def node(i,j,k):
        return 1+(i*(w+1)+j)*(d+1)+k
    def volume(i,j,k):
        a,b,c,e = node(i,j,k),node(i+1,j,k),node(i+1,j+1,k),node(i,j+1,k)
        return (a,b,c,e,a+1,b+1,c+1,e+1)
    count = len(stations)-1
    elements, boundaries = [],[]
    areas = {2:0.,3:0.}
    for i in range(count):
        for j in range(w):
            for k in range(d):
                a,b,c,e,f,g1,h1,i1 = nodes = volume(i,j,k)
                elements.append(nodes)
                parent = len(elements)
                if i == 0:
                    boundaries.append((1,parent,a,e,i1,f))
                if i == count-1:
                    boundaries.append((1,parent,b,c,h1,g1))
                if (j+.5)/w < .75:
                    continue
                for tag,target,layer,face in ((2,hanger_station,d-1,(f,g1,h1,i1)),
                                               (3,load_station,d-1,(f,g1,h1,i1))):
                    if k == layer and abs((stations[i]+stations[i+1])/2-target) < half_patch:
                        boundaries.append((tag,parent,*face))
                        p,q,r,s = (np.asarray(points[index-1]) for index in face)
                        areas[tag] += (np.linalg.norm(np.cross(q-p,r-p))+np.linalg.norm(np.cross(r-p,s-p)))/2
    sample = node(stations.index(load_station),w,d)-1
    assert min(areas.values()) > 0
    midpoints = {}

    def mids(nodes, edges):
        indices = []
        for a,b in edges:
            key = tuple(sorted((nodes[a],nodes[b])))
            if key not in midpoints:
                points.append(tuple((u+v)/2 for u,v in zip(points[key[0]-1],points[key[1]-1],strict=True)))
                midpoints[key] = len(points)
            indices.append(midpoints[key])
        return tuple(indices)

    hex_edges = ((0,1),(1,2),(2,3),(3,0),(0,4),(1,5),(2,6),(3,7),(4,5),(5,6),(6,7),(7,4))
    gmsh_hex_edges = ((0,1),(0,3),(0,4),(1,2),(1,5),(2,3),(2,6),(3,7),(4,5),(4,7),(5,6),(6,7))
    quad_edges = ((0,1),(1,2),(2,3),(3,0))
    quadratic = [nodes+mids(nodes,hex_edges) for nodes in elements]
    boundaries = [(tag,parent,*face,*mids(face,quad_edges)) for tag,parent,*face in boundaries]
    gmsh_cells = [(17,4,*nodes,*mids(nodes,gmsh_hex_edges)) for nodes in elements]
    gmsh_cells += [(16,tag,*face) for tag,_,*face in boundaries]
    directory.mkdir()
    rows = {
        "header":[f"{len(points)} {len(elements)} {len(boundaries)}","2",f"408 {len(boundaries)}",f"820 {len(elements)}"],
        "nodes":[f"{i} -1 {x:.10g} {y:.10g} {z:.10g}" for i,(x,y,z) in enumerate(points,1)],
        "elements":[" ".join(map(str,(i,1,820,*face))) for i,face in enumerate(quadratic,1)],
        "boundary":[" ".join(map(str,(i,tag,parent,0,408,*face))) for i,(tag,parent,*face) in enumerate(boundaries,1)],
    }
    for name,lines in rows.items():
        (directory/f"mesh.{name}").write_text("\n".join(lines)+"\n")
    gmsh_nodes = [f"{i} {x:.10g} {y:.10g} {z:.10g}" for i,(x,y,z) in enumerate(points,1)]
    msh.write_text("\n".join(["$MeshFormat","2.2 0 8","$EndMeshFormat","$Nodes",str(len(points)),*gmsh_nodes,
                                "$EndNodes","$Elements",str(len(gmsh_cells)),
                                *(" ".join(map(str,(i,kind,2,tag,tag,*face)))
                                  for i,(kind,tag,*face) in enumerate(gmsh_cells,1)),
                                "$EndElements",""]))
    return np.asarray(points),sample,areas,elements

def sif(case, frequency, areas):
    h,s = case["hanger"],case["structural_model"]
    stiffness = h["young_modulus_pa"]*pi*h["diameter_m"]**2/(4*h["length_m"])
    a,b = 2*pi*2,2*pi*12
    g = case["geometry"]
    deck_volume = g["radius_m"]*radians(g["angle_deg"])*g["width_m"]*g["deck_depth_m"]
    density = s["density_kg_m3"] + guard_mass(g)/deck_volume
    alpha = 2*s["damping_ratio"]*a*b/(a+b)
    beta = 2*s["damping_ratio"]/(a+b)
    return f"""Header
  CHECK KEYWORDS Warn
  Mesh DB "." "mesh"
End
Simulation
  Coordinate System = Cartesian 3D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
End
Body 1
  Equation = 1
  Material = 1
End
Material 1
  Youngs Modulus = Real {s["young_modulus_pa"]}
  Poisson Ratio = Real {s["poisson_ratio"]}
  Density = Real {density}
  Rayleigh Damping Alpha = Real {alpha}
  Rayleigh Damping Beta = Real {beta}
End
Equation 1
  Active Solvers(2) = 1 2
End
Solver 1
  Equation = Linear elasticity
  Procedure = "StressSolve" "StressSolver"
  Variable = -dofs 3 Displacement
  Harmonic Mode = Logical True
  Frequency = Real {frequency}
  Linear System Solver = Direct
  Linear System Direct Method = UMFPACK
  Nonlinear System Max Iterations = 1
End
Solver 2
  Exec Solver = After Simulation
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = File "response"
  Vtu Format = Logical True
  Binary Output = Logical False
End
Boundary Condition 1
  Target Boundaries(1) = 1
  Displacement 1 = Real 0
  Displacement 2 = Real 0
  Displacement 3 = Real 0
End
Boundary Condition 2
  Target Boundaries(1) = 2
  Spring 3 = Real {stiffness/areas[2]}
End
Boundary Condition 3
  Target Boundaries(1) = 3
  Force 3 = Real {-case["loads"]["footfall_amplitude_n"]/areas[3]}
End
"""

def read_response(path,points):
    piece = ET.parse(path).getroot().find("./UnstructuredGrid/Piece")
    coordinates = np.fromstring(piece.find("./Points/DataArray").text,sep=" ").reshape(-1,3)
    if not np.allclose(coordinates,points,atol=2e-6,rtol=0):
        raise ValueError("Unexpected Elmer node order.")
    arrays = {node.get("Name").lower():np.fromstring(node.text,sep=" ")
              for node in piece.findall("PointData/DataArray")}
    return arrays

def run_case(stem,step,mesh,result,case):
    draw_case(stem,case)
    export_step(geometry(case),step)
    return solve_sweep(case,mesh,result)

def outer_faces(elements):
    exterior = {}
    for a,b,c,d,e,f,g,h in elements:
        for face in ((d,c,b,a),(e,f,g,h),(a,b,f,e),(b,c,g,f),(c,d,h,g),(d,a,e,h)):
            key = tuple(sorted(face))
            if key in exterior:
                del exterior[key]
            else:
                exterior[key] = [node-1 for node in face]
    return list(exterior.values())

def solve_sweep(case, mesh, result):
    f = case["frequency"]
    _, solver, env = elmer_runtime()
    with TemporaryDirectory(prefix=".harmonic-",dir=result.parent) as directory:
        work = Path(directory).resolve()
        points, sample, areas, elements = native_mesh(case,work/"mesh",mesh)
        state = {}

        def solve(frequency):
            (work/"walkway.sif").write_text(sif(case,frequency,areas))
            target = work/"mesh"/"response_t0001.vtu"
            target.unlink(missing_ok=True)
            run = subprocess.run([solver,"walkway.sif"],cwd=work,env=env,capture_output=True,text=True)
            if run.returncode or not target.is_file():
                raise RuntimeError(run.stdout[-5500:] + run.stderr[-1500:])
            arrays = read_response(target,points)
            real, imaginary = arrays["displacement"],arrays["displacement im"]
            response = np.hypot(real[3*sample+2],imaginary[3*sample+2])*(2*pi*frequency)**2
            if not np.isfinite(response) or response <= 0 or not np.any(imaginary):
                raise ValueError("Invalid complex harmonic response.")
            state[frequency] = (float(response),real,imaginary)

        frequencies = sorted({f["end_hz"],*(round(float(freq),6) for freq in
                             np.arange(f["start_hz"],f["end_hz"],f["step_hz"]))})
        for frequency in frequencies:
            solve(frequency)
        peaks = sorted((freq for left,freq,right in zip(frequencies,frequencies[1:],frequencies[2:])
                        if state[left][0] < state[freq][0] > state[right][0]),
                       key=lambda freq: state[freq][0],reverse=True)[:3]
        for peak in peaks:
            for i in (-2,-1,1,2):
                frequency = round(peak+i*f["step_hz"]/5,6)
                if frequency not in state:
                    solve(frequency)
        frequencies = sorted(state)
        candidates = {frequencies[0],frequencies[-1]}
        candidates.update(freq for left,freq,right in zip(frequencies,frequencies[1:],frequencies[2:])
                          if state[left][0] < state[freq][0] > state[right][0])
        peaks = sorted(candidates,key=lambda freq:state[freq][0],reverse=True)[:3]
        solve(peaks[0])
        copyfile(work/"mesh"/"response_t0001.vtu",result)
        hanger = np.asarray(deck_point(case["geometry"],case["hanger"]["station"],.875,
                                      case["geometry"]["deck_depth_m"]/2))
        dist = np.linalg.norm(points-hanger,axis=1)
        attachment = np.flatnonzero(np.isclose(dist,dist.min(),atol=1e-6)).tolist()
        return {"points":points.round(6).ravel().tolist(),"faces":outer_faces(elements),
                "guard_mass_kg":guard_mass(case["geometry"]),"sample":sample,"attachment":attachment,"hanger":hanger.tolist(),
                "hanger_length":case["hanger"]["length_m"],
                "sweep":[[freq,state[freq][0]] for freq in frequencies],
                "peaks":[{"frequency":freq,"acceleration":state[freq][0],
                          "real":(1000*state[freq][1]).round(7).tolist(),
                          "imaginary":(1000*state[freq][2]).round(7).tolist()} for freq in peaks]}
