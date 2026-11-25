from itertools import pairwise, product
from math import ceil, cos, pi, sin, sqrt

import cadquery as cq
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from common.study_output import write_displacements, write_mesh, write_result, write_step
from common.drawings import dimension, label, line, write_sheet

VARIANTS = ("none","near","far")
SIDES = ("west","east","south","north")
CORNERS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                    [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]])
FACES = ((0,3,7,4),(1,5,6,2),(0,4,5,1),(3,2,6,7),(0,1,2,3),(4,7,6,5))
GAUSS = (-1/sqrt(3),1/sqrt(3))

def opening(config,variant):
    if variant == "none":
        return None
    left = config["opening_offsets_m"][variant]
    half = config["opening_length_m"]/2
    return left,left+config["opening_width_m"],-half,half

def partition(stops,max_size):
    points = sorted(set(stops))
    grid = [points[0]]
    for a,b in pairwise(points):
        count = ceil((b-a)/max_size)
        grid.extend(a+(b-a)*i/count for i in range(1,count))
        grid.append(b)
    return list(pairwise(grid))

def mesh(config,variant):
    h = config["half_span_m"]
    core = config["column_side_m"]/2
    cut = config["control_half_width_m"]
    thickness = config["slab_thickness_m"]
    hole = opening(config,variant)
    x = [-h,-cut,-core,core,cut,h]
    y = x.copy()
    if hole:
        x.extend(hole[:2])
        y.extend(hole[2:])
    size = config["mesh_size_m"]
    xs,ys = (partition(axis,size) for axis in (x,y))
    zs = partition((-config["column_height_m"],0,thickness),min(size,thickness/4))
    ids = {}
    cells,dimensions = [],[]
    for (x0,x1),(y0,y1),(z0,z1) in product(xs,ys,zs):
        cx,cy = (x0+x1)/2,(y0+y1)/2
        if z0 < 0 and (abs(cx) >= core or abs(cy) >= core):
            continue
        if z0 >= 0 and hole and hole[0] < cx < hole[1] and hole[2] < cy < hole[3]:
            continue
        lo,hi = np.array([x0,y0,z0]),np.array([x1,y1,z1])
        corners = lo+(CORNERS+1)/2*(hi-lo)
        corners = np.round(corners,12)
        cells.append([ids.setdefault(tuple(p),len(ids)) for p in corners])
        dimensions.append(hi-lo)
    return np.asarray(list(ids)),np.asarray(cells),np.asarray(dimensions)

def strain_matrix(location,dimensions):
    xi,eta,zeta = location
    x,y,z = CORNERS.T
    gradients = np.array([x*(1+y*eta)*(1+z*zeta),
                          y*(1+x*xi)*(1+z*zeta),
                          z*(1+x*xi)*(1+y*eta)])/(4*dimensions[:,None])
    dx,dy,dz = gradients
    b = np.zeros((6,24))
    b[0,0::3],b[1,1::3],b[2,2::3] = dx,dy,dz
    b[3,0::3],b[3,1::3] = dy,dx
    b[4,1::3],b[4,2::3] = dz,dy
    b[5,0::3],b[5,2::3] = dz,dx
    return b

def elastic_matrix(young,poisson):
    shear = young/(2*(1+poisson))
    lame = young*poisson/((1+poisson)*(1-2*poisson))
    matrix = np.diag([2*shear]*3+[shear]*3)
    matrix[:3,:3] += lame
    return matrix

def element(dimensions,elastic):
    stiffness = np.zeros((24,24))
    for corner in product(GAUSS,repeat=3):
        b = strain_matrix(corner,dimensions)
        stiffness += b.T@elastic@b
    return stiffness*np.prod(dimensions)/8

def architectural_context(config,variant,show_cut):
    base = -config["column_height_m"]
    pad = .39
    points = [v for x,y,z in CORNERS for v in
              (pad*x,pad*y,base-.09+.09*z)]
    parts = [{"material":"slabPlinth","points":points,"faces":FACES}]
    hole = opening(config,variant)
    if hole is None:
        return parts

    left,right,south,north = hole
    x = (left+right)/2
    y = (south+north)/2
    half_width = (right-left)/2-.048
    half_depth = (north-south)/2-.05
    radius = .31
    elbow_z = -.22
    inlet = -.035 if show_cut else config["slab_thickness_m"]+.15
    rings = [(x,inlet,1.,0.)]
    for i in range(9):
        angle = pi*i/16
        rings.append((x+radius*(1-cos(angle)),elbow_z-radius*sin(angle),cos(angle),-sin(angle)))
    rings.append((config["half_span_m"]+.08,elbow_z-radius,0.,-1.))

    points = []
    for bx,bz,u,v in rings:
        for inset in (0,.012):
            for a,b in ((-1,-1),(1,-1),(1,1),(-1,1)):
                offset = a*(half_width-inset)
                points.extend((bx+u*offset,y+b*(half_depth-inset),bz+v*offset))
    faces = []
    for i in range(len(rings)-1):
        start = 8*i
        for skin in (0,4):
            for j in range(4):
                a,b = start+skin+j,start+skin+(j+1)%4
                faces.append([a,b,b+8,a+8])
    for start in (0,8*(len(rings)-1)):
        for j in range(4):
            a,b = start+j,start+(j+1)%4
            faces.append([a,b,b+4,a+4])
    parts.append({"material":"slabDuct","points":[round(v,5) for v in points],"faces":faces})
    return parts

def solve_mesh(config,variant):
    nodes,cells,size = mesh(config,variant)
    elastic = elastic_matrix(config["young_modulus_pa"],config["poisson_ratio"])
    matrices = {}
    stiffness = []
    for dimensions in size:
        key = tuple(np.round(dimensions,10))
        if key not in matrices:
            matrices[key] = element(np.array(key),elastic)
        stiffness.append(matrices[key])
    stiffness = np.asarray(stiffness)
    dofs = (3*cells[:,:,None]+np.arange(3)).reshape(-1,24)
    ndof = nodes.size
    stiffness_global = coo_matrix((stiffness.ravel(),(np.repeat(dofs,24,axis=1).ravel(),
                                  np.tile(dofs,(1,24)).ravel())),shape=(ndof,ndof)).tocsr()
    top = np.isclose(nodes[cells[:,4],2],config["slab_thickness_m"])
    areas = size[:,0]*size[:,1]
    pressure = config["total_load_n"]/areas[top].sum()
    local_load = np.zeros((len(cells),24))
    local_load[top,14::3] = -(pressure*areas[top]/4)[:,None]
    load = np.zeros(ndof)
    np.add.at(load,dofs.ravel(),local_load.ravel())
    fixed = np.repeat(np.isclose(nodes[:,2],-config["column_height_m"]),3)
    displacement = np.zeros(ndof)
    free = ~fixed
    displacement[free] = spsolve(stiffness_global[free][:,free],load[free])
    reaction = (stiffness_global@displacement-load)[2::3][fixed[2::3]].sum()
    if not np.isclose(reaction,config["total_load_n"],rtol=1e-6):
        raise ValueError("Column reactions do not balance the applied load.")

    cut = config["control_half_width_m"]
    centers = nodes[cells].mean(axis=1)
    inside = (np.abs(centers[:,:2]) < cut).all(axis=1)
    traction = np.zeros(len(nodes))
    residual = np.einsum("eij,ej->ei",stiffness[inside],displacement[dofs[inside]])-local_load[inside]
    np.add.at(traction,cells[inside].ravel(),residual[:,2::3].ravel())
    along_cut = (np.abs(nodes[:,:2]) <= cut+1e-9).all(axis=1)
    masks = np.array([along_cut & np.isclose(nodes[:,axis],sign*cut)
                      for axis,sign in ((0,-1),(0,1),(1,-1),(1,1))])
    weights = masks.sum(axis=0).clip(min=1)
    flux = -(masks@(traction/weights))
    expected = reaction + local_load[inside].sum()
    if not np.isclose(flux.sum(),expected,rtol=1e-6):
        raise ValueError("The balancing shear across the study cut does not close.")

    return nodes,cells,size,displacement,{
        "shares":[float(value/flux.sum()*100) for value in flux],
        "shear_kn":float(flux.sum()/1000),"reaction_kn":float(reaction/1000),
    }

def visualise(config,variant,nodes,cells,displacement):
    size = nodes[cells].max(axis=1)-nodes[cells].min(axis=1)
    centers = nodes[cells].mean(axis=1)
    cut = config["control_half_width_m"]
    inside = (np.abs(centers[:,:2]) < cut).all(axis=1)
    along_cut = (np.abs(nodes[:,:2]) <= cut+1e-9).all(axis=1)
    masks = [along_cut & np.isclose(nodes[:,axis],sign*cut)
             for axis,sign in ((0,-1),(0,1),(1,-1),(1,1))]
    elastic = elastic_matrix(config["young_modulus_pa"],config["poisson_ratio"])
    dofs = (3*cells[:,:,None]+np.arange(3)).reshape(-1,24)
    surface,cut_faces = {},[]
    for i,cell in enumerate(cells):
        for side,face in enumerate(FACES):
            ids = tuple(cell[list(face)])
            key = tuple(sorted(ids))
            if key in surface:
                del surface[key]
            else:
                surface[key] = (i,side,ids)
            if inside[i] and side < 4 and masks[side][list(ids)].all():
                cut_faces.append((i,side,ids))

    def get_colour(i,side):
        axis,sign = divmod(side,2)
        field = []
        for a,b in product(GAUSS,repeat=2):
            location = [a,b]
            location.insert(axis,2*sign-1)
            stress = elastic@strain_matrix(location,size[i])@displacement[dofs[i]]
            field.append(abs(stress[5-axis]) if side < 4 else np.hypot(stress[4],stress[5]))
        return float(np.mean(field)/1e6)

    def part(facets,material,stress=False,opacity=1):
        faces = [ids for _,_,ids in facets]
        ids = sorted({i for face in faces for i in face})
        index = {node:i for i,node in enumerate(ids)}
        return {"points":nodes[ids].ravel().tolist(),"faces":[[index[i] for i in face] for face in faces],
                "material":material,"opacity":opacity,
                **({"compression":[get_colour(i,side) for i,side,_ in facets]} if stress else {})}

    shell = list(surface.values())
    footprint = part(shell,"slabConcrete")
    context = [facet for facet in shell if centers[facet[0],2] < 0]
    outer = [facet for facet in shell if centers[facet[0],2] >= 0]
    stress_parts = [part(context,"slabConcrete"),part(outer,"slabConcrete",opacity=.25),
                    part(cut_faces,"slabConcrete",stress=True)]
    hole = opening(config,variant)
    if hole:
        left,right,south,north = hole
        z = config["slab_thickness_m"]+.002
        stress_parts.append({"material":"slabOpening",
                             "points":[left,south,z,right,south,z,right,north,z,left,north,z],
                             "faces":[[0,1],[1,2],[2,3],[3,0]]})
    return {"cad":[footprint,*architectural_context(config,variant,show_cut=False)],
            "result":{"parts":[*stress_parts,*architectural_context(config,variant,show_cut=True)]}}

def solve_model(config,variant):
    nodes,cells,_,displacement,metrics = solve_mesh(config,variant)
    result = visualise(config,variant,nodes,cells,displacement)
    result["result"].update(metrics)
    return result

def draw_case(stem,config):
    variant = config['opening']
    span,cut = config["half_span_m"],config["control_half_width_m"]
    core = config["column_side_m"]
    hole = opening(config,variant)
    scale = 122
    cx,cy = 480,370
    t,h = config["slab_thickness_m"],config["column_height_m"]

    def rect(x,y,width,height,style):
        return (f'<rect x="{cx+x*scale:g}" y="{cy+y*scale:g}" width="{width*scale:g}" '
                f'height="{height*scale:g}" class="{style}"/>')

    def sheet(view,title,ref,items):
        write_sheet(stem.with_name(stem.name+f"-{view}.svg"),title,ref,items,"Slab–Column Opening")

    plan = [rect(-span,-span,2*span,2*span,"roof"),
            rect(-core/2,-core/2,core,core,"wall"),
            f'<rect x="{cx-cut*scale:g}" y="{cy-cut*scale:g}" width="{2*cut*scale:g}" '
            f'height="{2*cut*scale:g}" fill="none" class="cut"/>',
            label(cx,cy-cut*scale-13,"Shear integration cut",anchor="middle"),
            *dimension(cx-span*scale,cy+span*scale,cx+span*scale,cy+span*scale,38,2*span)]
    if hole:
        left,right,south,north = hole
        plan.append(rect(left,-north,right-left,north-south,"glass"))
        plan.append(label(cx+(left+right)/2*scale,cy+68,"Service opening",anchor="middle"))
    sheet("plan","Slab plan and shear integration cut","SO-01",plan)
    elevation = [rect(-span,-t,2*span,t,"roof"),rect(-core/2,0,core,h,"wall"),
                 *dimension(cx-core*scale/2,cy+h*scale,cx+core*scale/2,cy+h*scale,38,core,millimetres=True)]
    sheet("elevation","Slab and column elevation","SO-02",elevation)
    section = elevation.copy()
    if hole:
        section[0:1] = [rect(-span,-t,hole[0]+span,t,"roof"),rect(hole[1],-t,span-hole[1],t,"roof")]
    for x in (-cut,cut):
        section.append(line(cx+x*scale,cy-t*scale-22,cx+x*scale,cy+12,"cut"))
    section.append(label(cx,cy-72,"Section through column and service opening",anchor="middle"))
    sheet("section","Section through slab thickness","SO-03",section)

def run_case(stem,step,mesh_path,result,config):
    draw_case(stem,config)
    variant = config["opening"]
    nodes,cells,size,displacement,metrics = solve_mesh(config,variant)
    span = 2000*config["half_span_m"]
    thickness = 1000*config["slab_thickness_m"]
    side = 1000*config["column_side_m"]
    height = 1000*config["column_height_m"]
    floor = cq.Solid.makeBox(span,span,thickness,cq.Vector(-span/2,-span/2,0))
    if hole := opening(config,variant):
        left,right,south,north = [1000*value for value in hole]
        floor = floor.cut(cq.Solid.makeBox(right-left,north-south,thickness+2,cq.Vector(left,south,-1)))
    column = cq.Solid.makeBox(side,side,height,cq.Vector(-side/2,-side/2,-height))
    write_step(step,architectural_context(config,variant,show_cut=False),
               (("slabConcrete_0",floor.fuse(column).clean()),))
    write_mesh(mesh_path,nodes,cells,5)
    elastic = elastic_matrix(config["young_modulus_pa"],config["poisson_ratio"])
    stress = [elastic@strain_matrix((0,0,0),dimensions)@displacement[(3*cell[:,None]+np.arange(3)).ravel()]
              for cell,dimensions in zip(cells,size,strict=True)]
    write_displacements(result,nodes,cells,12,displacement.reshape(-1,3),{"stress_Pa":stress})
    write_result(stem.with_name(stem.name+"-study-results.json"),metrics)
