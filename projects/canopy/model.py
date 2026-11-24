import json
from math import isfinite, radians, tan

import cadquery as cq

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from .solid import LUG_HEIGHT, LUG_WIDTH, PIN_OFFSET, anchor_result, bolt_centres, mesh_solids, solve_anchor, tag_result, write_mesh

CANOPY_LEVEL = 2.40
FRAME = 0.055
HEAD_DIAMETER_FACTOR = 1.6
HEAD_HEIGHT = 0.011

def anchor_height(g, angle):
    return CANOPY_LEVEL + (g["canopy_depth_m"]-PIN_OFFSET) * tan(radians(angle))

def canopy_cad(g, angle):
    w, depth = g["canopy_width_m"], g["canopy_depth_m"]
    wall_t = g["wall_thickness_m"]
    z = anchor_height(g, angle)
    wall_top = z + g["bolt_half_height_m"] + g["edge_distance_m"]
    model = cq.Assembly(name="Canopy")
    concrete = cq.Color(.72, .70, .66)
    steel = cq.Color(.64, .32, .23)
    glass = cq.Color(.49, .74, .80, .35)

    def vector(*xyz):
        return cq.Vector(*(1000*v for v in xyz))

    def box(x,y,z,dx,dy,dz):
        return cq.Solid.makeBox(1000*dx,1000*dy,1000*dz,vector(x,y,z))

    def rod(a, b, radius):
        a, b = vector(*a), vector(*b)
        return cq.Solid.makeCylinder(1000*radius,(b-a).Length,a,b-a)

    wall = box(-2.15,-wall_t,0,4.3,wall_t,wall_top)
    wall = wall.cut(box(-.89,-wall_t-.01,-.01,1.78,wall_t+.02,2.24))
    model.add(wall, name="Concrete", color=concrete)
    model.add(box(-.88,-.025,0,1.76,.02,2.22), name="Glass_entrance", color=glass)
    model.add(box(-w/2,0,CANOPY_LEVEL+.012,w,depth,.014),name="Glass_canopy",color=glass)
    for i, y in enumerate((0, depth/2, depth-FRAME)):
        model.add(box(-w/2,y,CANOPY_LEVEL-FRAME/2,w,FRAME,FRAME),name=f"Frame_transverse_{i}",color=steel)

    for i, x in enumerate((-w/2+FRAME/2,w/2-FRAME/2)):
        model.add(box(x-FRAME/2,0,CANOPY_LEVEL-FRAME/2,FRAME,depth,FRAME),
                  name=f"Frame_edge_{i}",color=steel)
        model.add(rod((x,PIN_OFFSET,z),(x,depth,CANOPY_LEVEL),.009),name=f"Tie_{i}",color=steel)
        pw, ph, pt = (g[f"plate_{key}_m"] for key in ("width","height","thickness"))
        model.add(box(x-pw/2,0,z-ph/2,pw,pt,ph),name=f"Plate_{i}",color=steel)
        for j, sign in enumerate((-1,1)):
            side = x + sign*LUG_WIDTH/2 - .005
            model.add(box(side,pt,z-LUG_HEIGHT/2,.010,PIN_OFFSET+.012-pt,LUG_HEIGHT),
                      name=f"Cheek_{i}_{j}",color=steel)
        model.add(rod((x-LUG_WIDTH*.7,PIN_OFFSET,z),(x+LUG_WIDTH*.7,PIN_OFFSET,z),.010),
                  name=f"Pin_{i}",color=steel)
        for j,(dx,dz) in enumerate(bolt_centres(g),1):
            diameter = g["anchor_diameter_m"]
            model.add(rod((x+dx,-g["embedment_m"],z+dz),(x+dx,pt+.014,z+dz),diameter/2),
                      name=f"Bolt_{i}_{j}",color=steel)
            model.add(rod((x+dx,pt,z+dz),(x+dx,pt+HEAD_HEIGHT,z+dz),diameter*HEAD_DIAMETER_FACTOR/2),
                      name=f"Head_{i}_{j}",color=steel)
    return model

def draw_canopy(stem, g, angle):
    w, depth = g["canopy_width_m"], g["canopy_depth_m"]
    anchor_z = anchor_height(g, angle)
    scale = 95
    x, ground = 480, 540
    y = ground - CANOPY_LEVEL*scale
    anchor_y = ground - anchor_z*scale

    def rect(x,y,w,h,style):
        return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" class="{style}"/>'

    def sheet(kind, title, ref, parts):
        write_sheet(stem.with_name(f"{stem.name}-{kind}.svg"), title, ref, parts, "Canopy")

    plan = [rect(x-w*scale/2,260,w*scale,depth*scale,"glass"),
            line(x-205,260,x+205,260,"ground")]
    plan += dimension(x-w*scale/2,260+depth*scale,x+w*scale/2,260+depth*scale,45,w)
    plan += dimension(x+w*scale/2,260,x+w*scale/2,260+depth*scale,64,depth)
    sheet("plan","Canopy plan","CN-01",plan)

    elevation = [rect(x-205,anchor_y-10,410,ground-anchor_y+10,"roof"),
                 rect(x-.89*scale,ground-2.23*scale,1.78*scale,2.23*scale,"glass"),
                 line(x-w*scale/2,y,x+w*scale/2,y,"ground")]
    for pos in (x-w*scale/2,x+w*scale/2):
        elevation += [rect(pos-8,anchor_y-7,16,14,"wall"),line(pos,anchor_y,pos,y,"ground")]
    elevation += dimension(x-w*scale/2,ground,x+w*scale/2,ground,30,w)
    sheet("elevation","Entrance elevation","CN-02",elevation)

    face = 146
    outside = face + depth*scale
    section = [rect(face-27,anchor_y-10,27,ground-anchor_y+10,"wall"),
               line(face,y,outside,y,"glass-line"),line(face+PIN_OFFSET*scale,anchor_y,outside,y,"ground"),
               label(face+35,anchor_y+26,f"Tie rod {angle:g}°"),
               line(face-75,ground,outside+28,ground,"ground")]
    section += dimension(face,y,outside,y,45,depth)
    dx, dz, detail_scale = 455, 360, 720
    pw, ph = g["plate_width_m"]*detail_scale, g["plate_height_m"]*detail_scale
    left, right = dx-pw/2, dx+pw/2
    top, bottom = dz-ph/2, dz+ph/2
    half_span = g["bolt_half_span_m"]
    half_height = g["bolt_half_height_m"]
    top_bolt = dz-half_height*detail_scale
    edge = g["edge_distance_m"]
    edge_y = top_bolt-edge*detail_scale
    left_bolt, right_bolt = dx-half_span*detail_scale, dx+half_span*detail_scale
    diameter = g["anchor_diameter_m"]
    head = diameter*HEAD_DIAMETER_FACTOR

    section += [label(dx, 201, "Anchor plate elevation", anchor="middle"),
                line(left-12, edge_y, right+14, edge_y, "ground"),
                rect(left, top, pw, ph, "roof")]
    for bx, bz in bolt_centres(g):
        section.append(f'<circle cx="{dx+bx*detail_scale:g}" cy="{dz-bz*detail_scale:g}" '
                       f'r="{head*detail_scale/2:g}" class="wall"/>')
    section += dimension(left, bottom, right, bottom, 39, g["plate_width_m"], millimetres=True)
    section += dimension(left, top, left, bottom, -59, g["plate_height_m"], millimetres=True)
    section += dimension(left_bolt, top_bolt, right_bolt, top_bolt, -36, 2*half_span, millimetres=True)
    section += dimension(left_bolt, top_bolt, left_bolt, dz+half_height*detail_scale,
                         left-28-left_bolt, 2*half_height, millimetres=True)
    if g["bolts"] == 6:
        section.append(label(dx, bottom+68, f"3 rows at {half_height*1000:g} mm centres", anchor="middle"))
    section += dimension(right_bolt, top_bolt, right_bolt, edge_y,
                         right+39-right_bolt, edge, millimetres=True)

    cut_scale = 680
    wall_face, bolt_y = 809, 346
    concrete_back = wall_face-g["wall_thickness_m"]*cut_scale
    concrete_top = bolt_y-edge*cut_scale
    tip = wall_face-g["embedment_m"]*cut_scale
    plate = g["plate_thickness_m"]
    plate_face = wall_face+plate*cut_scale
    shank_r, head_r = diameter*cut_scale/2, head*cut_scale/2
    section += [label(729, 201, "Section through upper bolt", anchor="middle"),
                rect(concrete_back, concrete_top, wall_face-concrete_back, 137, "roof"),
                rect(wall_face, bolt_y-(g["plate_height_m"]/2-half_height)*cut_scale,
                     plate*cut_scale, ph*cut_scale/detail_scale, "wall"),
                rect(tip, bolt_y-shank_r, plate_face-tip, 2*shank_r, "wall"),
                rect(plate_face, bolt_y-head_r, HEAD_HEIGHT*cut_scale, 2*head_r, "wall"),
                line(tip-12, bolt_y, plate_face+HEAD_HEIGHT*cut_scale+12, bolt_y, "cut")]
    section += dimension(tip, bolt_y+shank_r, wall_face, bolt_y+shank_r, 76,
                         g["embedment_m"], millimetres=True)
    section += [label((tip+wall_face)/2, 449, "Embedment", anchor="middle"),
                label(645, 483, f"Bolt shank Ø{diameter*1000:g} mm"),
                label(645, 505, f"Head Ø{head*1000:g} × {HEAD_HEIGHT*1000:g} mm"),
                label(645, 527, f"Plate thickness {plate*1000:g} mm")]
    sheet("section","Section and anchor detail","CN-03",section)

def draw_case(stem, case):
    draw_canopy(stem, case["geometry"], case["loads"]["tie_angle_deg"])

def run_case(stem, step, mesh, result, case):
    g, loads = case["geometry"], case["loads"]
    angle = loads["tie_angle_deg"]
    if not all(isfinite(v) and v > 0 for v in (*g.values(), *loads.values())):
        raise ValueError("Canopy dimensions and tie load must be finite and positive.")
    if (type(g["bolts"]) is not int or g["bolts"] not in (4,6)
            or g["embedment_m"] >= g["wall_thickness_m"] or not 0 < angle < 90
            or g["plate_thickness_m"] >= PIN_OFFSET or g["canopy_depth_m"] <= PIN_OFFSET
            or 2*g["bolt_half_span_m"]+g["anchor_diameter_m"] >= g["plate_width_m"]
            or 2*g["bolt_half_height_m"]+g["anchor_diameter_m"] >= g["plate_height_m"]
            or g["bolt_half_height_m"]+g["edge_distance_m"] <= g["plate_height_m"]/2):
        raise ValueError("The bolts, plate, edge and tie must fit the canopy geometry.")
    fine = case["mesh"]["bolt_size_m"]
    if not isfinite(fine) or not 0 < fine <= case["mesh"]["element_size_m"]:
        raise ValueError("Invalid bolt mesh size.")
    draw_case(stem, case)
    export_step(canopy_cad(g,angle),step)
    data = mesh_solids(g,case["mesh"])
    write_mesh(mesh,data)
    force = solve_anchor(result,case,data)
    metrics = anchor_result(result,case,data,force)
    tag_result(result,data)
    stem.with_name(stem.name+"-anchor-results.json").write_text(json.dumps(metrics, indent=2)+"\n")
    print(f"Opening {metrics['opening_mm']} mm; force residual {metrics['imbalance_percent']} %",flush=True)
