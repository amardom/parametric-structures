from math import ceil

import numpy as np

from common.study_output import write_displacements, write_mesh, write_result, write_step
from common.drawings import dimension, label, line, write_sheet

STAGES = ("existing", "underpinning", "excavation", "permanent")
STAGE_NOTES = {
    "existing": "The existing strip footing bears on the ground.",
    "underpinning": "Temporary supports are installed before the ground is removed.",
    "excavation": "The temporary supports carry the facade while the gallery is excavated.",
    "permanent": "A permanent transfer beam and two end walls take over before the temporary supports are removed.",
}
FACES = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]

def opening(config, width):
    center = config["gallery_center_m"]
    return center-width/2,center+width/2

def stage_results(config, width):
    length = config["length_m"]
    left,right = opening(config,width)
    temporary = (left+.8,right-.8)
    sensors = (2.,config["gallery_center_m"])
    stations = sorted({*np.linspace(0,length,ceil(length/config["element_size_m"])+1),
                       left,right,*temporary,*sensors})
    matrix = np.zeros((2*len(stations),)*2)
    transfer = np.zeros_like(matrix)
    load = np.zeros(len(matrix))
    ground = np.zeros(len(matrix))
    remaining = np.zeros(len(matrix))
    for i,(a,b) in enumerate(zip(stations,stations[1:])):
        span = b-a
        dofs = np.arange(2*i,2*i+4)
        element = np.array([
            [12,6*span,-12,6*span],[6*span,4*span**2,-6*span,2*span**2],
            [-12,-6*span,12,-6*span],[6*span,2*span**2,-6*span,4*span**2],
        ])
        element /= span**3
        matrix[np.ix_(dofs,dofs)] += config["foundation_rigidity_nm2"]*element
        if left < (a+b)/2 < right:
            transfer[np.ix_(dofs,dofs)] += config["transfer_rigidity_nm2"]*element
        load[dofs] += config["line_load_n_m"]*span/12*np.array([6,span,6,-span])
        vertical = dofs[::2]
        spring = config["ground_stiffness_n_m2"]*span/2
        ground[vertical] += spring
        if (a+b)/2 <= left or (a+b)/2 >= right:
            remaining[vertical] += spring

    def support(points, stiffness):
        springs = np.zeros_like(load)
        for x in points:
            springs[2*stations.index(x)] = stiffness
        return springs

    props = support(temporary,config["temporary_stiffness_n_m"])
    walls = support((left,right),config["permanent_stiffness_n_m"])
    return stations, sensors, solve_stages(matrix,load,ground,remaining,props,walls,transfer)

def solve_stages(matrix,load,ground,remaining,props,walls,transfer):
    existing = np.linalg.solve(matrix+np.diag(ground),load)
    installed = np.linalg.solve(matrix+np.diag(ground+props),load+props*existing)
    excavated = np.linalg.solve(matrix+np.diag(remaining+props),load+props*installed)
    permanent = np.linalg.solve(matrix+transfer+np.diag(remaining+walls),load+walls*excavated+transfer@excavated)
    return (existing,installed,excavated,permanent)

def parts(config,width,stage,stations=None,motion=None):
    length = config["length_m"]
    left,right = opening(config,width)
    depth = config["gallery_depth_m"]
    solids = []

    def box(x0,x1,y0,y1,z0,z1,material,moves=False,top_moves=False):
        points = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
                  (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
        if motion is not None and (moves or top_moves):
            points = [(x,y,z-35*np.interp(x,stations,motion) if moves or z == z1 else z)
                      for x,y,z in points]
        solids.append({"material":material,"points":[round(v,5) for xyz in points for v in xyz],"faces":FACES})

    def bendable_band(x0,x1,y0,y1,z0,z1,material):
        cuts = [x0,*(x for x in (stations if stations is not None else []) if x0 < x < x1),x1]
        for a,b in zip(cuts,cuts[1:]):
            box(a,b,y0,y1,z0,z1,material,True)

    for z0,z1 in ((0,.7),(2.25,2.95),(4.4,5.05)):
        bendable_band(0,length,0,.55,z0,z1,"facadeStone")
    bays = [1.65,4.33,7,9.67,12.35]
    piers = [(0,bays[0]-.58),*((a+.58,b-.58) for a,b in zip(bays,bays[1:])),(bays[-1]+.58,length)]
    for a,b in piers:
        for sill,head in ((.7,2.25),(2.95,4.4)):
            box(a,b,0,.55,sill,head,"facadeStone",True)
    for x in bays:
        for sill,head in ((.7,2.25),(2.95,4.4)):
            box(x-.58,x+.58,.11,.17,sill,head,"facadeGlass",True)
    bendable_band(-.1,length+.1,-.10,.66,4.91,5.15,"facadeStone")
    bendable_band(-.12,length+.12,-.08,.68,-.40,0,"facadeFooting")
    if stage in ("existing","underpinning"):
        box(-.8,length+.8,.08,3.2,-depth-.45,-.4,"facadeSoil")
    else:
        box(-.8,left,0,3.2,-depth-.45,-.4,"facadeSoil")
        box(right,length+.8,0,3.2,-depth-.45,-.4,"facadeSoil")
        box(left,right,.08,3.2,-depth-.45,-depth,"facadeSoil")
    if stage in ("underpinning","excavation"):
        for x in (left+.8,right-.8):
            box(x-.12,x+.12,-.18,.20,-depth,-.40,"facadeProp",top_moves=True)
    if stage == "permanent":
        for x in (left,right):
            box(x-.18,x+.18,-.17,2.6,-depth,-.83,"facadeFooting",top_moves=True)
        bendable_band(left-.18,right+.18,-.17,2.6,-.83,-.40,"facadeFooting")
        box(left,right,-.17,2.6,-depth,-depth+.18,"facadeFooting")
    if motion is not None:
        for x,material in ((2.,"facadeGaugeA"),(config["gallery_center_m"],"facadeGaugeB")):
            box(x-.13,x+.13,-.15,-.08,.2,.46,material,True)
    return solids

def draw_case(stem,config):
    width,stage = config['gallery_width_m'],config['stage']
    scale = 44
    origin,floor = 154,400
    left,right = opening(config,width)
    length,depth = config["length_m"],config["gallery_depth_m"]

    def rect(x,z,width,height,style):
        return (f'<rect x="{origin+x*scale:g}" y="{floor-(z+height)*scale:g}" '
                f'width="{width*scale:g}" height="{height*scale:g}" class="{style}"/>')

    def sheet(suffix,title,number,items):
        write_sheet(stem.with_name(stem.name+f"-{suffix}.svg"),title,number,items,"Historic Facade · Underbuild Study")

    plan = [rect(0,0,length,.55,"wall"),rect(left,-2.6,width,2.6,"roof"),
            label(origin+(left+right)/2*scale,floor+82,"Gallery footprint",anchor="middle"),
            *dimension(origin+left*scale,530,origin+right*scale,530,26,width)]
    sheet("plan","Foundation plan","HF-01",plan)
    elevation = [rect(0,0,length,5.15,"roof")]
    for x in (1.65,4.33,7,9.67,12.35):
        for z in (.7,2.95):
            elevation.append(rect(x-.58,z,1.16,1.5,"glass"))
    for name,x in (("A",2),("B",config["gallery_center_m"])):
        elevation.extend([line(origin+x*scale,floor,origin+x*scale,floor+28,"extension"),
                          label(origin+x*scale,floor+47,name,anchor="middle")])
    sheet("elevation","Facade elevation · Monitoring points","HF-02",elevation)
    solids = parts(config,width,stage)
    styles = {"facadeStone":"roof","facadeGlass":"glass","facadeFooting":"wall",
              "facadeSoil":"roof","facadeProp":"glass"}
    section = []
    for solid in solids:
        xyz = solid["points"]
        xs,zs = xyz[::3],xyz[2::3]
        shape = rect(min(xs),min(zs),max(xs)-min(xs),max(zs)-min(zs),styles[solid["material"]])
        section.append(shape)
    section += [label(origin,581,STAGE_NOTES[stage]),
                *dimension(origin+left*scale,568,origin+right*scale,568,48,width)]
    sheet("section","Longitudinal cut through the gallery","HF-03",section)

def run_case(stem,step,mesh,result,config):
    width,stage = config["gallery_width_m"],config["stage"]
    draw_case(stem,config)
    write_step(step,parts(config,width,stage))
    stations,sensors,states = stage_results(config,width)
    readings = []
    for state in states:
        movement = (state-states[0])[::2]
        a,b = [float(np.interp(x,stations,movement)*1000) for x in sensors]
        readings.append({"a_mm":a,"b_mm":b,"difference_mm":abs(b-a)})
    index = STAGES.index(stage)
    points = np.zeros((len(stations),3))
    points[:,0] = stations
    cells = np.column_stack((np.arange(len(stations)-1),np.arange(1,len(stations))))
    movement = np.zeros_like(points)
    movement[:,2] = -(states[index]-states[0])[::2]
    write_mesh(mesh,points,cells,1)
    write_displacements(result,points,cells,3,movement)
    write_result(stem.with_name(stem.name+"-study-results.json"),
                 {**readings[index],"history":readings,"note":STAGE_NOTES[stage]})
