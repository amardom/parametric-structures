from math import isfinite

import cadquery as cq

from common.cad import export_step
from common.drawings import dimension, label, line, write_sheet
from .thermal import SLAT_DEPTH, SLAT_SPACING, glazing, solve_heat

SILL = .62

def check(case):
    g,w,u = case["geometry"],case["windows"],case["use"]
    dimensions = (*g.values(),w["main_width_m"],w["main_height_m"],w["north_width_m"],w["north_height_m"],
                  w["u_value_w_m2k"],u["air_changes_per_hour"])
    if not all(isfinite(x) and x > 0 for x in dimensions):
        raise ValueError("Cabin dimensions and ventilation must be positive and finite.")
    if w["main_facade"] not in ("south","west") or not 0 < w["solar_factor"] <= 1:
        raise ValueError("Invalid primary window orientation or solar factor.")
    wall = g["concrete_m"]+g["insulation_m"]
    if any(width+2*wall >= g["side_m"] or height+SILL >= g["height_m"]
           for width,height in glazing(case).values()):
        raise ValueError("Windows must fit inside the cabin walls.")

def cabin_cad(case):
    g = case["geometry"]
    half,height = g["side_m"]/2,g["height_m"]
    concrete,insulation = g["concrete_m"],g["insulation_m"]
    wall = concrete+insulation
    model = cq.Assembly(name="Thermal_cabin")
    cement = cq.Color(.72,.70,.64)
    glass = cq.Color(.27,.45,.47,.55)
    wood = cq.Color(.55,.40,.27)

    def solid(x,y,z,dx,dy,dz):
        return cq.Solid.makeBox(*(1000*v for v in (dx,dy,dz)),cq.Vector(*(1000*v for v in (x,y,z))))

    for face,rotation in (("south",0),("east",90),("north",180),("west",270)):
        def oriented(shape):
            return shape.rotate((0,0,0),(0,0,1),rotation)
        inset = wall if face in ("east","west") else 0
        panel = solid(-half+inset,-half,0,2*(half-inset),wall,height)
        opening = glazing(case).get(face)
        if opening is not None:
            width,opening_height = opening
            cutout = solid(-width/2,-half-.002,SILL,width,wall+.004,opening_height)
            panel = panel.cut(cutout)
            glass_panel = solid(-width/2,-half+wall*.53,SILL,width,.035,opening_height)
            model.add(oriented(glass_panel),name=f"Window_{face}",color=glass)
            frame = solid(-width/2-.035,-half+.03,SILL-.035,width+.07,.10,opening_height+.07)
            frame = frame.cut(solid(-width/2+.04,-half+.02,SILL+.04,width-.08,.12,opening_height-.08))
            model.add(oriented(frame),name=f"Frame_{face}",color=wood)
            if face == case["windows"]["main_facade"] and case["windows"]["shaded"]:
                for i in range(1,int(opening_height/SLAT_SPACING)+1):
                    blade = solid(-width/2-.11,-half-SLAT_DEPTH,SILL+i*SLAT_SPACING,width+.22,SLAT_DEPTH,.028)
                    model.add(oriented(blade),name=f"Shade_{i}",color=wood)
                for i,x in enumerate((-width/2-.105,width/2+.07)):
                    support = solid(x,-half-SLAT_DEPTH,SILL,.035,.035,opening_height)
                    model.add(oriented(support),name=f"Shade_support_{i}",color=wood)
        model.add(oriented(panel),name=f"Wall_{face}",color=cement)
    model.add(solid(-half,-half,height,2*half,2*half,wall),name="Roof",color=cement)
    model.add(solid(-half,-half,-wall,2*half,2*half,wall),name="Floor",color=cement)
    return model

def draw_case(stem,case):
    check(case)
    g,w = case["geometry"],case["windows"]
    side,height = g["side_m"],g["height_m"]
    wall = g["concrete_m"]+g["insulation_m"]
    scale = min(390/side,300/(height+wall))
    x,y = 480,355
    r = side*scale/2
    left,right,top,bottom = x-r,x+r,y-r,y+r

    def rect(x,y,width,height,style):
        return f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" class="{style}"/>'

    def sheet(suffix,title,number,items):
        write_sheet(stem.with_name(stem.name+f"-{suffix}.svg"),title,number,items,"Thermal Cabin")

    inset = wall*scale
    plan = [rect(left,top,2*r,2*r,"wall"),
            rect(left+inset,top+inset,2*(r-inset),2*(r-inset),"roof"),
            line(right+70,top+35,right+70,top,"ground"),
            line(right+64,top+9,right+70,top,"ground"),line(right+76,top+9,right+70,top,"ground"),
            label(right+70,top-12,"N",anchor="middle"),
            *dimension(left,bottom,right,bottom,45,side)]
    for face,(width,_) in glazing(case).items():
        half = width*scale/2
        if face == "west":
            plan.append(rect(left,y-half,inset,2*half,"glass"))
        else:
            plan.append(rect(x-half,top if face == "north" else bottom-inset,2*half,inset,"glass"))
    if w["shaded"]:
        half = (w["main_width_m"]/2+.11)*scale
        if w["main_facade"] == "south":
            plan.append(rect(x-half,bottom,2*half,SLAT_DEPTH*scale,"roof"))
        else:
            plan.append(rect(left-SLAT_DEPTH*scale,y-half,SLAT_DEPTH*scale,2*half,"roof"))
    sheet("plan","Cabin plan","TC-01",plan)

    base = 520
    roof = base-height*scale
    width,window_h = (w[key]*scale for key in ("main_width_m","main_height_m"))
    sill = base-SILL*scale
    elevation = [rect(left,roof,2*r,height*scale,"roof"),rect(left,roof-inset,2*r,inset,"wall"),
                 rect(x-width/2,sill-window_h,width,window_h,"glass"),
                 *dimension(left,base,right,base,47,side),
                 *dimension(right,roof,right,base,41,height)]
    if w["shaded"]:
        for i in range(1,int(w["main_height_m"]/SLAT_SPACING)+1):
            elevation.append(line(x-width/2-9,sill-i*SLAT_SPACING*scale,
                                  x+width/2+9,sill-i*SLAT_SPACING*scale,"ground"))
    sheet("elevation",w["main_facade"].title()+" elevation","TC-02",elevation)

    section = [rect(left,base,2*r,inset,"roof"),rect(left,roof-inset,2*r,inset,"roof"),
               rect(right-inset,roof,inset,height*scale,"roof"),
               rect(left,roof,inset,sill-window_h-roof,"roof"),
               rect(left,sill,inset,base-sill,"roof"),
               line(left+inset/2,sill-window_h,left+inset/2,sill,"glass-line"),
               *dimension(left,base+inset,right,base+inset,41,side)]
    if w["shaded"]:
        for i in range(1,int(w["main_height_m"]/SLAT_SPACING)+1):
            level = sill-i*SLAT_SPACING*scale
            section.append(line(left-SLAT_DEPTH*scale,level,left,level,"ground"))
    sheet("section","Section through main glazing","TC-03",section)

def run_case(stem,step,mesh,result,case):
    draw_case(stem,case)
    export_step(cabin_cad(case),step)
    return solve_heat(case,mesh,result)
