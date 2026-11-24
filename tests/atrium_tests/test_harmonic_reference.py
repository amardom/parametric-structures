import cmath
from itertools import pairwise
from math import pi
import subprocess

import numpy as np
import pytest

from common.elmer import elmer_runtime
from projects.atrium import model

@pytest.mark.elmer
def test_harmonic_axial_bar_matches_analytical_resonance(load_case,tmp_path,monkeypatch,elmer_installed):
    case = load_case("atrium")
    young,density,force = 1e6,2500,10
    length,area,segments = 1,.01,24
    case["structural_model"].update(young_modulus_pa=young,density_kg_m3=density,poisson_ratio=0)
    case["loads"]["footfall_amplitude_n"] = force
    monkeypatch.setattr(model,"guard_mass",lambda geometry:0)
    points = np.array([(x,y,i*length/segments) for i in range(segments+1)
                       for x,y in ((0,0),(.1,0),(.1,.1),(0,.1))])
    mesh = tmp_path/"mesh"
    mesh.mkdir()
    (mesh/"mesh.header").write_text(f"{len(points)} {segments} 2\n2\n404 2\n808 {segments}\n")
    (mesh/"mesh.nodes").write_text("".join(f"{i} -1 {x:.12g} {y:.12g} {z:.12g}\n"
                                           for i,(x,y,z) in enumerate(points,1)))
    ring_ids = [range(4*i+1,4*i+5) for i in range(segments+1)]
    (mesh/"mesh.elements").write_text("".join(
        f"{i} 1 808 "+" ".join(map(str,(*bottom,*top)))+"\n"
        for i,(bottom,top) in enumerate(pairwise(ring_ids),1)
    ))
    (mesh/"mesh.boundary").write_text(f"1 1 1 0 404 1 2 3 4\n"
                                     f"2 3 {segments} 0 404 "+" ".join(map(str,ring_ids[-1]))+"\n")

    a,b = 2*pi*2,2*pi*12
    damping = case["structural_model"]["damping_ratio"]
    alpha,beta = 2*damping*a*b/(a+b),2*damping/(a+b)
    natural = (young/density)**.5/(4*length)

    def analytical_amplitude(frequency):
        omega = 2*pi*frequency
        modulus = young*(1+1j*omega*beta)
        wave = cmath.sqrt(density*(omega**2-1j*omega*alpha)/modulus)
        return abs(force*cmath.tan(wave*length)/(area*modulus*wave))

    _,solver,env = elmer_runtime()
    frequencies = natural+np.linspace(-.2,.2,17)
    measured = []
    for frequency in frequencies:
        (tmp_path/"bar.sif").write_text(model.sif(case,frequency,{2:area,3:area}))
        result = mesh/"response_t0001.vtu"
        result.unlink(missing_ok=True)
        run = subprocess.run([solver,"bar.sif"],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=30)
        assert run.returncode == 0 and result.is_file(),run.stdout[-3000:]+run.stderr
        output = model.read_response(result,points)
        axial = output["displacement"][-12:][2::3] + 1j*output["displacement im"][-12:][2::3]
        assert np.max(abs(axial-axial.mean())) < 1e-8
        measured.append(abs(axial.mean()))

    reference = [analytical_amplitude(frequency) for frequency in frequencies]
    assert frequencies[np.argmax(measured)] == pytest.approx(frequencies[np.argmax(reference)],abs=.026)
    assert max(measured) == pytest.approx(max(reference),rel=.02)
