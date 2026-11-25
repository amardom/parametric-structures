from itertools import product

import numpy as np

from common.study_output import write_displacements, write_mesh, write_result, write_step
from common.drawings import dimension, label, line, write_sheet

JOINTS = ("rigid","flexible")
SECTIONS = {
    "chord": (.34,.56,.022),
    "post": (.30,.38,.018),
    "floor": (.26,.40,.016),
}
AMPLIFICATION = 20
BOX_FACES = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]

def section_properties(width,depth,wall):
    inner_w,inner_d = width-2*wall,depth-2*wall
    area = width*depth-inner_w*inner_d
    iy = (width*depth**3-inner_w*inner_d**3)/12
    iz = (depth*width**3-inner_d*inner_w**3)/12
    torsion = 2*wall*((width-wall)*(depth-wall))**2/(width+depth-2*wall)
    return area,iy,iz,torsion

def local_axes(a,b):
    axis = b-a
    length = np.linalg.norm(axis)
    axis = axis/length
    reference = (0,0,1) if abs(axis[2]) < .9 else (0,1,0)
    side = np.cross(reference,axis)
    side /= np.linalg.norm(side)
    return length,np.array([axis,side,np.cross(axis,side)])

def local_stiffness(length,young,shear,section):
    area,iy,iz,j = section_properties(*section)
    k = np.zeros((12,12))
    for ids,rigidity in (((0,6),young*area),((3,9),shear*j)):
        k[np.ix_(ids,ids)] = rigidity/length*np.array([[1,-1],[-1,1]])
    l = length
    bending = np.array([[12,6*l,-12,6*l],[6*l,4*l*l,-6*l,2*l*l],
                        [-12,-6*l,12,-6*l],[6*l,2*l*l,-6*l,4*l*l]])
    k[np.ix_((1,5,7,11),(1,5,7,11))] = young*iz/l**3*bending
    sign = np.diag([1,-1,1,-1])
    k[np.ix_((2,4,8,10),(2,4,8,10))] = young*iy/l**3*(sign@bending@sign)
    return k

def flexible_ends(k, spring):
    ids = (5,11)
    to_joint = np.eye(12)
    to_joint[ids,:] = 0
    to_post = np.eye(12)[:,ids]
    joint_rotations = to_post.T
    internal = to_post.T@k@to_post + spring*np.eye(2)
    coupling = to_joint.T@k@to_post - spring*joint_rotations.T
    external = to_joint.T@k@to_joint + spring*joint_rotations.T@joint_rotations
    return external-coupling@np.linalg.solve(internal,coupling.T)

def frame(config,bay):
    count = round(config["length_m"]/bay)
    nodes = {}
    for i,side,level in product(range(count+1),range(2),range(3)):
        nodes[i,side,level] = (i*bay,side*config["width_m"],level*config["storey_height_m"])
    members = []
    for i,side,level in product(range(count+1),range(2),range(3)):
        if i < count:
            members.append(((i,side,level),(i+1,side,level),"chord"))
        if level < 2:
            members.append(((i,side,level),(i,side,level+1),"post"))
        if side == 0:
            members.append(((i,0,level),(i,1,level),"floor"))
    return nodes,members

def solve_frame(config,bay,joint):
    nodes,members = frame(config,bay)
    indices = {key:i for i,key in enumerate(nodes)}
    k = np.zeros((6*len(nodes),)*2)
    load = np.zeros(len(k))
    for a,b,kind in members:
        length,axes = local_axes(np.array(nodes[a]),np.array(nodes[b]))
        local = local_stiffness(length,config["steel_modulus_pa"],config["steel_shear_modulus_pa"],SECTIONS[kind])
        if joint == "flexible" and kind == "post":
            local = flexible_ends(local,config["joint_stiffness_nm_rad"])
        transform = np.kron(np.eye(4),axes)
        dofs = np.r_[6*indices[a]:6*indices[a]+6,6*indices[b]:6*indices[b]+6]
        k[np.ix_(dofs,dofs)] += transform.T@local@transform
    count = round(config["length_m"]/bay)
    for (i,side,level),index in indices.items():
        weight = .5 if i in (0,count) else 1
        share = config["near_side_load_fraction"] if side == 0 else 1-config["near_side_load_fraction"]
        load[6*index+2] = -weight*bay*config["width_m"]*config["floor_pressure_pa"][level]*share
    free = np.array([6*index+dof for key,index in indices.items() if key[0] for dof in range(6)])
    displacement = np.zeros(len(k))
    displacement[free] = np.linalg.solve(k[np.ix_(free,free)],load[free])
    reactions = k@displacement-load
    if not np.isclose(reactions[2::6].sum(),-load[2::6].sum(),rtol=1e-6):
        raise ValueError("Vertical reactions do not balance the floor loads.")
    translation = {key:displacement[6*i:6*i+3] for key,i in indices.items()}
    return nodes,members,translation

def window_corners(nodes,translation):
    keys = ((0,0,0),(1,0,0),(1,0,1),(0,0,1))
    start = np.array([nodes[key] for key in keys])
    moved = start+np.array([translation[key] for key in keys])
    return start,moved

def window_measures(nodes,translation):
    start,moved = window_corners(nodes,translation)
    diagonals = ((0,2),(1,3))
    changes = [float(1000*(np.linalg.norm(moved[a]-moved[b])-np.linalg.norm(start[a]-start[b])))
               for a,b in diagonals]
    return changes

def geometry(config,nodes,members,translation=None):
    parts = []
    level = config["storey_height_m"]
    width = config["width_m"]
    top = 2*level
    length = config["length_m"]

    def box(points,material):
        parts.append({"material":material,"points":np.asarray(points).round(6).ravel().tolist(),"faces":BOX_FACES})

    def cuboid(x0,x1,y0,y1,z0,z1,material):
        box([(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
             (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)],material)

    cuboid(-3.1,-.12,-.22,width+.22,-3.2,top+.55,"vierCore")
    cuboid(-3.15,length+.75,-.9,width+.9,-3.30,-3.22,"vierGround")
    def position(key):
        return np.array(nodes[key]) if translation is None else np.array(nodes[key])+AMPLIFICATION*translation[key]
    for a,b,kind in members:
        begin,end = position(a),position(b)
        _,axes = local_axes(np.array(nodes[a]),np.array(nodes[b]))
        w,d,_ = SECTIONS[kind]
        offsets = (w/2*axes[1],d/2*axes[2])
        u,v = offsets
        box([point+offset for point in (begin,end) for offset in (-u-v,u-v,u+v,-u+v)],
            "vierFloor" if kind == "floor" else "vierSteel")
    count = max(key[0] for key in nodes)
    for i,storey in product(range(count),range(3)):
        slab = [position(key) for key in ((i,0,storey),(i+1,0,storey),(i+1,1,storey),(i,1,storey))]
        box([point+np.array([0,0,z]) for z in (-.085,.085) for point in slab],"vierDeck")
    window = [position(key)+np.array([0,-.23,0]) for key in ((0,0,0),(1,0,0),(1,0,1),(0,0,1))]
    parts.append({"material":"vierWindow","points":np.asarray(window).ravel().tolist(),
                  "faces":[[0,1],[1,2],[2,3],[3,0]]})
    if translation is not None:
        parts.append({"material":"vierWindow","points":np.asarray(window).ravel().tolist(),"faces":[[0,2],[1,3]]})
    return parts

def draw_case(stem,config):
    bay = config['bay_width_m']
    length,width,height = (config[key] for key in ("length_m","width_m","storey_height_m"))
    scale = 42
    x,y = 216,480
    count = round(length/bay)
    def rect(x,y,w,h,style):
        return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" class="{style}"/>'
    def sheet(view,title,ref,items):
        write_sheet(stem.with_name(stem.name+f"-{view}.svg"),title,ref,items,"Vierendeel Cantilever")
    plan = [rect(x-3*scale,y-width*scale,3*scale,width*scale,"wall"),
            rect(x,y-width*scale,length*scale,width*scale,"roof")]
    for i in range(count+1):
        axis = x+i*bay*scale
        plan.append(line(axis,y-width*scale,axis,y,"ground"))
    plan += [label(x+8,y-15,"Heavier load on this side"),
             *dimension(x,y,x+length*scale,y,43,length)]
    sheet("plan","Framing plan","VC-01",plan)
    elevation = [rect(x-3*scale,y-2*height*scale,3*scale,(2*height+3.2)*scale,"wall")]
    for i in range(count):
        for level in range(2):
            elevation.append(rect(x+i*bay*scale,y-(level+1)*height*scale,bay*scale,height*scale,
                                  "glass" if i == level == 0 else "roof"))
    elevation += [*dimension(x,y,x+bay*scale,y,34,bay),
                  *dimension(x,y,x+length*scale,y,84,length)]
    sheet("elevation","Vierendeel facade elevation","VC-02",elevation)
    section = [rect(x,y-2*height*scale,width*scale,2*height*scale,"roof"),
               line(x,y-height*scale,x+width*scale,y-height*scale,"ground"),
               *dimension(x,y,x+width*scale,y,40,width)]
    sheet("section","Transverse section through the cantilever","VC-03",section)

def run_case(stem,step,mesh,result,config):
    bay,joint = config["bay_width_m"],config["joint"]
    draw_case(stem,config)
    nodes,members,motion = solve_frame(config,bay,joint)
    write_step(step,geometry(config,nodes,members))
    indices = {key:index for index,key in enumerate(nodes)}
    points = np.asarray(list(nodes.values()))
    cells = np.asarray([(indices[a],indices[b]) for a,b,_ in members])
    write_mesh(mesh,points,cells,1)
    write_displacements(result,points,cells,3,[motion[key] for key in nodes])
    start,moved = window_corners(nodes,motion)
    tip = round(config["length_m"]/bay)
    drops = [float(-1000*motion[tip,side,0][2]) for side in (0,1)]
    write_result(stem.with_name(stem.name+"-study-results.json"),
                 {"tip_mm":drops,"diagonal_changes_mm":window_measures(nodes,motion),
                  "window_initial":start[:,[0,2]].tolist(),
                  "window_displacement":(moved-start)[:,[0,2]].tolist(),"warp":AMPLIFICATION})
