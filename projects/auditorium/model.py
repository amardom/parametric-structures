from itertools import pairwise
from math import dist, sqrt
import subprocess

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

from common.study_output import write_result, write_step
from common.drawings import dimension, label, line, write_sheet

ROWS = ("front","middle","back")
ROOFS = ("flat","folded")
WALLS = ("reflective","absorptive")
PHRASE = ("Good morning.", "Please take a seat.", "The presentation will begin shortly.")
BAND_SPLITS_HZ = (500,2000)
RAY_COLOURS = {"direct":"audDirect","ceiling":"audCeiling","rear wall":"audRear",
               "floor":"audOther","front wall":"audOther"}
BOX_FACES = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]

def floor_height(x):
    return max(0,x-3)*.065

def ceiling_profile(case, roof):
    if roof == "flat":
        return [(0,case["flat_ceiling_m"]),(case["length_m"],case["flat_ceiling_m"])]
    return [tuple(point) for point in case["folded_ceiling_m"]]

def walls(case, roof, rear, band=1):
    profile = ceiling_profile(case,roof)
    absorptions = {name:values[band] for name,values in case["absorption"].items()}
    ceiling = "ceiling_panels" if rear == "absorptive" else "ceiling"
    left,right = profile[0],profile[-1]
    return [
        *((a,b,"ceiling",absorptions[ceiling]) for a,b in pairwise(profile)),
        ((0,0),left,"front wall",absorptions["front_wall"]),
        ((case["length_m"],floor_height(case["length_m"])),right,"rear wall",
         absorptions["rear_panels" if rear == "absorptive" else "rear_wall"]),
        ((0,0),(3,0),"floor",absorptions["floor"]),
        ((3,0),(case["length_m"],floor_height(case["length_m"])),"floor",absorptions["floor"]),
    ]

def reflection(source, receiver, a, b):
    dx,dz = b[0]-a[0],b[1]-a[1]
    normal = (-dz,dx)
    projected = sum((s-v)*n for s,v,n in zip(source,a,normal,strict=True))/(dx*dx+dz*dz)
    image = tuple(s-2*projected*n for s,n in zip(source,normal,strict=True))
    ray = tuple(r-i for r,i in zip(receiver,image,strict=True))
    denominator = sum(v*n for v,n in zip(ray,normal,strict=True))
    if abs(denominator) < 1e-9:
        return None
    t = sum((v-i)*n for v,i,n in zip(a,image,normal,strict=True))/denominator
    point = tuple(i+t*r for i,r in zip(image,ray,strict=True))
    u = ((point[0]-a[0])*dx+(point[1]-a[1])*dz)/(dx*dx+dz*dz)
    if 0 < t < 1 and 0 < u < 1:
        return point
    return None

def reflection_paths(case, roof, rear, receiver, band=1):
    source = tuple(case["stage_source_m"])
    speed = case["sound_speed_m_s"]
    wall_segments = walls(case,roof,rear,band)
    direct = dist(source,receiver)
    paths = [{"kind":"direct","points":[source,receiver],"delay_ms":0,"gain":2/direct}]
    for a,b,kind,absorption in wall_segments:
        point = reflection(source,receiver,a,b)
        if point is None:
            continue
        length = dist(source,point)+dist(point,receiver)
        paths.append({"kind":kind,"points":[source,point,receiver],"delay_ms":1000*(length-direct)/speed,
                      "gain":2*sqrt(1-absorption)/length})
    return sorted(paths,key=lambda path:path["delay_ms"])

def decay_time(case, roof, rear, band=1):
    boundaries = walls(case,roof,rear,band)
    width,length = case["width_m"],case["length_m"]
    section = sum((b[0]-a[0])*(a[1]+b[1])/2 for a,b in pairwise(ceiling_profile(case,roof)))
    section -= (length-3)*floor_height(length)/2
    absorption = sum(dist(a,b)*width*factor for a,b,_,factor in boundaries)
    absorption += 2*section*case["absorption"]["side_walls"][band]
    return .161*section*width/absorption

def geometry(case, roof, rear, paths=None):
    length,width = case["length_m"],case["width_m"]
    profile = ceiling_profile(case,roof)
    parts = []

    def prism(a,b,z0,z1,y0,y1,material,thickness=None):
        if thickness is not None:
            z0,z1 = z0+thickness,z1+thickness
        points = [a[0],y0,a[1],b[0],y0,b[1],b[0],y1,b[1],a[0],y1,a[1],
                  a[0],y0,z0,b[0],y0,z1,b[0],y1,z1,a[0],y1,z0]
        parts.append({"material":material,"points":points,"faces":BOX_FACES})

    for a,b in pairwise(profile):
        prism(a,b,a[1],b[1],0,width,"roof",.18)
        if rear == "absorptive":
            for start in (.12,1.9,3.68,5.46,7.24):
                prism((a[0],a[1]-.085),(b[0],b[1]-.085),a[1],b[1],
                      start,min(start+1.64,width),"audPanel")
    for x0,x1 in ((0,3),(3,length)):
        prism((x0,floor_height(x0)-.22),(x1,floor_height(x1)-.22),
              floor_height(x0),floor_height(x1),0,width,"wall")
    for a,b in pairwise(profile):
        prism((a[0],floor_height(a[0])),(b[0],floor_height(b[0])),a[1],b[1],width,width+.17,"wall")
    end_height = profile[-1][1]
    prism((length,floor_height(length)),(length+.17,floor_height(length)),end_height,end_height,
          0,width,"audPanel" if rear == "absorptive" else "wall")
    prism((.6,0),(3.2,0),.16,.16,1,width-1,"timber")
    for row in range(10):
        x = 4.4+row*1.17
        z = floor_height(x)
        for seat in range(8):
            y = .85+seat*1.03
            prism((x,z+.31),(x+.40,z+.31),z+.45,z+.45,y,y+.65,"audSeat")
            prism((x+.40,z+.36),(x+.49,z+.36),z+.86,z+.86,y,y+.65,"audSeat")
    if paths is not None:
        middle = width/2
        for path in paths:
            points = [v for x,z in path["points"] for v in (x,middle,z)]
            parts.append({"material":RAY_COLOURS[path["kind"]],"points":points,
                          "faces":[[i,i+1] for i in range(len(points)//3-1)]})
    return parts

def draw_case(stem,case):
    roof,rear = case["roof"],case["treatment"]
    receiver = case["seats_m"][ROWS.index(case["row"])]
    paths = reflection_paths(case,roof,rear,receiver)
    profile = ceiling_profile(case,roof)
    length,width = case["length_m"],case["width_m"]
    x0,y0,scale = 106,390,43
    sx = lambda x:x0+scale*x
    sy = lambda z:y0-scale*z

    def svg_rect(x,y,w,h,style):
        return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" class="{style}"/>'

    def sheet(view,title,ref,items):
        write_sheet(stem.with_name(stem.name+f"-{view}.svg"),title,ref,items,"Folded Auditorium")

    plan = [svg_rect(sx(0),180,length*scale,width*scale,"roof"),
            svg_rect(sx(.6),210,2.6*scale,width*scale-60,"wall")]
    for row in range(10):
        for seat in range(8):
            plan.append(svg_rect(sx(4.4+row*1.17),218+seat*43,15,22,"wall"))
    plan += dimension(sx(0),180,sx(length),180,-31,length)
    sheet("plan","Auditorium seating plan","AU-01",plan)
    elevation = [svg_rect(sx(3),195,width*scale,200,"roof"),
                 label(sx(3)+width*scale/2,295,"Absorptive lining" if rear == "absorptive" else "Reflective rear wall",anchor="middle"),
                 *dimension(sx(3),395,sx(3)+width*scale,395,36,width)]
    sheet("elevation","Rear wall elevation","AU-02",elevation)

    colours = {"direct":"#197164","ceiling":"#ba571e","rear wall":"#784cb0",
               "floor":"#859096","front wall":"#859096"}
    section = []
    for a,b,kind,_ in walls(case,roof,rear):
        if rear == "absorptive" and kind in ("ceiling","rear wall"):
            section.append(f'<path d="M{sx(a[0]):g} {sy(a[1]):g}L{sx(b[0]):g} {sy(b[1]):g}" '
                           'stroke="#3d827a" stroke-width="5"/>')
        else:
            section.append(line(sx(a[0]),sy(a[1]),sx(b[0]),sy(b[1]),"ground"))
    for row in range(10):
        x=4.4+row*1.17
        z=floor_height(x)
        section.append(svg_rect(sx(x),sy(z+.4),.44*scale,.13*scale,"wall"))
    for path in paths:
        points = " ".join(f"{sx(x):g},{sy(z):g}" for x,z in path["points"])
        strength = path["gain"]/paths[0]["gain"]
        section.append(f'<polyline points="{points}" fill="none" stroke="{colours[path["kind"]]}" '
                       f'stroke-width="{1+1.6*strength:.2f}" opacity="{.35+.65*strength:.2f}"/>')
    for (x,z),name in ((case["stage_source_m"],"Speaker"),(receiver,"Listener")):
        section.extend([f'<circle cx="{sx(x):g}" cy="{sy(z):g}" r="4" fill="#203d46"/>',
                        label(sx(x),sy(z)-12,name,anchor="middle")])
    for x,kind,description in ((0,"direct","Direct sound"),(4,"ceiling","Ceiling"),(8,"rear wall","Rear wall"),(12,"floor","Other surfaces")):
        section.extend([f'<path d="M{sx(x):g} 484h23" stroke="{colours[kind]}" stroke-width="2"/>',
                        label(sx(x)+30,489,description)])
    if not any(path["kind"] == "ceiling" for path in paths):
        section.append(label(sx(0),522,"No first-order ceiling reflection reaches this seat."))
    else:
        section.append(label(sx(0),522,"First-order paths in the room centreline."))
    sheet("section","Longitudinal acoustic section","AU-03",section)

def render_speech(rate,speech,paths,decay):
    tail_start = round(.055*rate)
    impulse = np.zeros(tail_start+int(np.ceil(decay*rate)))
    time = np.arange(len(impulse)-tail_start)/rate
    noise = np.random.default_rng(9173).uniform(-1,1,len(time))*10**(-3*time/decay)
    impulse[tail_start:] = noise * .20 * sqrt(decay/(noise@noise))
    for path in paths:
        impulse[round(path["delay_ms"]*rate/1000)] += path["gain"]
    return fftconvolve(speech,impulse)

def split_speech(rate,speech):
    low,lower_mid = [sosfilt(butter(2,hz,fs=rate,output="sos"),speech) for hz in BAND_SPLITS_HZ]
    return low,lower_mid-low,speech-lower_mid

def encode_listening_sample(path_bands,decays,reference_level):
    rate = 22050
    phrases = []
    for phrase in PHRASE:
        source = subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-f","lavfi","-i",
                                 f"flite=voice=slt:text={phrase}","-ac","1","-ar",str(rate),"-f","s16le","-"],
                                check=True,capture_output=True).stdout
        phrases.extend((np.frombuffer(source,dtype="<i2").astype(float)/32768,np.zeros(round(.48*rate))))
    speech = np.concatenate(phrases[:-1])
    bands = split_speech(rate,speech)
    clips = [render_speech(rate,signal,paths,decay)
             for signal,paths,decay in zip(bands,path_bands,decays,strict=True)]
    audio = np.zeros(max(map(len,clips)))
    for clip in clips:
        audio[:len(clip)] += clip
    gain = reference_level / np.max(np.abs(speech))
    pcm = (np.clip(audio*gain,-1,1)*32767).astype("<i2")
    encoded = subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-f","s16le","-ar",str(rate),
                              "-ac","1","-i","-","-codec:a","libmp3lame","-b:a","48k","-f","mp3","-"],
                             input=pcm.tobytes(),check=True,capture_output=True).stdout
    return encoded

def run_case(stem,step,_mesh,result,case):
    draw_case(stem,case)
    roof,rear = case["roof"],case["treatment"]
    receiver = case["seats_m"][ROWS.index(case["row"])]
    write_step(step,geometry(case,roof,rear))
    path_bands = [reflection_paths(case,roof,rear,receiver,band) for band in range(3)]
    decays = [decay_time(case,roof,rear,band) for band in range(3)]
    audio = encode_listening_sample(path_bands,decays,case["speech_reference_level"])
    stem.with_name(stem.name+"-speech.mp3").write_bytes(audio)
    write_result(result,{"paths":path_bands[1],"rt60_s":decays[1],"decay_bands_s":decays})
