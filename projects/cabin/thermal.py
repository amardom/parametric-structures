from math import ceil, cos, pi, radians, sin
from pathlib import Path
from shutil import copyfile
import subprocess
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from common.elmer import elmer_runtime

FACADES = ("south","west","north","east","roof","floor")
WARMUP_DAYS = 2
DISPLAY_DAYS = 3
TIME_STEP = 600
SLAT_DEPTH = .30
SLAT_SPACING = .24
AIR_HEAT_CAPACITY = 1206
CONCRETE = (1.7,2300*880)
INSULATION = (.037,32*1400)

def glazing(case):
    w = case["windows"]
    return {w["main_facade"]:(w["main_width_m"],w["main_height_m"]),
            "north":(w["north_width_m"],w["north_height_m"])}

def weather_at(case, second):
    w = case["weather"]
    hour = (second/3600)%24
    mean = (w["outdoor_max_c"]+w["outdoor_min_c"])/2
    half = (w["outdoor_max_c"]-w["outdoor_min_c"])/2
    outdoor = mean+half*cos((hour-15)*pi/12)
    latitude = radians(w["latitude_deg"])
    declination = radians(23.44)*sin(2*pi*(284+w["day_of_year"])/365)
    angle = (hour-12)*pi/12
    east = -cos(declination)*sin(angle)
    north = cos(latitude)*sin(declination)-sin(latitude)*cos(declination)*cos(angle)
    up = sin(latitude)*sin(declination)+cos(latitude)*cos(declination)*cos(angle)
    beam = 900*.76**(.35/max(up,.035)) if up > 0 else 0
    diffuse = 95*max(0,up)
    solar = {face:beam*max(0,norm)+diffuse*(1 if face == "roof" else .5)
             for face,norm in zip(FACADES,(-north,-east,north,east,up,0),strict=True)}
    solar["floor"] = 0
    window = case["windows"]
    direct_normal = {"south":-north,"west":-east}
    transmitted = 0
    for face,(width,height) in glazing(case).items():
        incident = solar[face]
        if face == window["main_facade"] and window["shaded"]:
            normal = max(0,direct_normal[face])
            open_fraction = max(0,1-SLAT_DEPTH*max(up,0)/(SLAT_SPACING*normal)) if normal else 0
            incident = beam*normal*open_fraction+.24*diffuse
        transmitted += incident*width*height*window["solar_factor"]
    return outdoor,solar,transmitted

def thermal_mesh(case, folder, msh):
    g = case["geometry"]
    side,height = g["side_m"],g["height_m"]
    volume = side*side*height
    air = AIR_HEAT_CAPACITY*volume
    vent = air*case["use"]["air_changes_per_hour"]/3600
    points = [(0.,0.,0.)]
    cells, boundaries, materials = [],[],[]
    inside = {}
    window_areas = {face:w*h for face,(w,h) in glazing(case).items()}

    def branch(layers, index, boundary):
        end = 1
        for length,conductivity,capacity,divisions in layers:
            materials.append((conductivity,capacity))
            for _ in range(divisions):
                points.append((points[end-1][0]+length/divisions,float(index),0.))
                cells.append((len(materials),end,len(points)))
                end = len(points)
                if len(cells) == 1 or cells[-1][1] == 1:
                    surface = end
        if boundary:
            boundaries.append((boundary,len(cells),end))
        return surface

    for index,face in enumerate(FACADES):
        area = (side**2 if face in ("roof","floor") else side*height)-window_areas.get(face,0)
        layers = [(1,7.7*area,0,1)]
        for length,(k,c) in ((g["concrete_m"],CONCRETE),(g["insulation_m"],INSULATION)):
            layers.append((length,k*area,c*area,ceil(length/case["mesh"]["element_size_m"])))
        layers.append((1,20*area,0,1))
        inside[face] = branch(layers,index+1,index+1)-1
    window_conductance = sum(window_areas.values())*case["windows"]["u_value_w_m2k"]
    branch([(1,window_conductance,0,1)],7,7)
    branch([(1,vent,0,1)],8,8)
    branch([(.01,1e4,air/.01,1)],9,None)

    for i, (x,ray,z) in enumerate(points[1:],1):
        angle = ray*2*pi/9
        points[i] = (x*cos(angle),x*sin(angle),z)
    folder.mkdir()
    rows = {
        "header":[f"{len(points)} {len(cells)} {len(boundaries)}","2",
                  f"101 {len(boundaries)}",f"202 {len(cells)}"],
        "nodes":[f"{i} -1 {x:.12g} {y:.12g} {z:.12g}" for i,(x,y,z) in enumerate(points,1)],
        "elements":[f"{i} {body} 202 {a} {b}" for i,(body,a,b) in enumerate(cells,1)],
        "boundary":[f"{i} {tag} {parent} 0 101 {node}" for i,(tag,parent,node) in enumerate(boundaries,1)],
    }
    for name,lines in rows.items():
        (folder/f"mesh.{name}").write_text("\n".join(lines)+"\n")
    msh.write_text("\n".join(["$MeshFormat","2.2 0 8","$EndMeshFormat","$Nodes",str(len(points)),
        *(f"{i} {x:.12g} {y:.12g} {z:.12g}" for i,(x,y,z) in enumerate(points,1)),
        "$EndNodes","$Elements",str(len(cells)+len(boundaries)),
        *(f"{i} 1 2 {body} {body} {a} {b}" for i,(body,a,b) in enumerate(cells,1)),
        *(f"{i} 15 2 {tag} {tag} {node}" for i,(tag,_,node) in enumerate(boundaries,len(cells)+1)),
        "$EndElements",""]))
    return points,materials,inside,vent

def heat_sif(materials,case,vent):
    steps = (WARMUP_DAYS+DISPLAY_DAYS)*86400//TIME_STEP
    bodies = []
    for i,(conductivity,capacity) in enumerate(materials,1):
        bodies.append(f"""Body {i}
  Equation = 1
  Material = {i}
  Initial Condition = 1
End
Material {i}
  Heat Conductivity = Real {conductivity}
  Density = Real 1
  Heat Capacity = Real {capacity}
End""")
    histories = [[] for _ in range(8)]
    for i in range(steps+1):
        t = i*TIME_STEP
        outdoor,solar,gain = weather_at(case,t)
        values = [outdoor+(.65 if face == "roof" else .5)*solar[face]/20 for face in FACADES[:-1]]
        values += [case["weather"]["ground_c"],outdoor,
                   outdoor+(gain+case["use"]["internal_gains_w"])/vent]
        for history,value in zip(histories,values,strict=True):
            history.append(f"    {t} {value:.8f}")
    boundaries = []
    for i,history in enumerate(histories,1):
        table = "\n".join(history)
        boundaries.append(f"""Boundary Condition {i}
  Target Boundaries(1) = {i}
  Temperature = Variable Time
    Real
{table}
    End
End""")
    return f"""Header
  CHECK KEYWORDS Warn
  Mesh DB "." "mesh"
End
Simulation
  Simulation Type = Transient
  Timestepping Method = BDF
  BDF Order = 2
  Timestep Intervals = {steps}
  Timestep Sizes = {TIME_STEP}
  Output Intervals = {3600//TIME_STEP}
  Coordinate System = Cartesian 3D
End
Initial Condition 1
  Temperature = Real 23
End
Equation 1
  Active Solvers(2) = 1 2
End
Solver 1
  Equation = Heat Equation
  Procedure = "HeatSolve" "HeatSolver"
  Variable = Temperature
  Variable DOFs = 1
  Linear System Solver = Direct
  Linear System Direct Method = Banded
  Nonlinear System Max Iterations = 1
End
Solver 2
  Exec Solver = After Timestep
  Equation = Result Output
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = File "temperature"
  Vtu Format = Logical True
  Binary Output = Logical False
End
{chr(10).join(bodies)}
{chr(10).join(boundaries)}
"""

def solve_heat(case,msh,result):
    _,solver,env = elmer_runtime()
    with TemporaryDirectory(prefix=".cabin-heat-",dir=result.parent) as directory:
        work = Path(directory).resolve()
        points,materials,inside,vent = thermal_mesh(case,work/"mesh",msh)
        (work/"heat.sif").write_text(heat_sif(materials,case,vent),encoding="ascii")
        run = subprocess.run([solver,"heat.sif"],cwd=work,env=env,capture_output=True,text=True)
        files = sorted((work/"mesh").glob("temperature_t*.vtu"))[3600//TIME_STEP-1::3600//TIME_STEP]
        if run.returncode or len(files) != 24*(WARMUP_DAYS+DISPLAY_DAYS):
            raise RuntimeError(run.stdout[-6000:]+run.stderr[-1800:])
        frames = []
        for hour,path in enumerate(files,1):
            if hour < WARMUP_DAYS*24:
                continue
            piece = ET.parse(path).find("./UnstructuredGrid/Piece")
            coordinates = [float(v) for v in piece.find("./Points/DataArray").text.split()]
            if any(abs(a-b)>1e-7 for a,b in zip(coordinates,(v for point in points for v in point),strict=True)):
                raise ValueError("Unexpected thermal node order.")
            temperatures = list(map(float,piece.find("PointData/DataArray[@Name='temperature']").text.split()))
            outdoor,solar,gain = weather_at(case,hour*3600)
            frames.append({"hour":hour-WARMUP_DAYS*24,"air":round(temperatures[0],3),
                           "outdoor":round(outdoor,3),"gain":round(gain,1),
                           "surface":{f:round(temperatures[i],2) for f,i in inside.items()},
                           "solar":{f:round(v,1) for f,v in solar.items()}})
        copyfile(files[-1],result)
    return frames
