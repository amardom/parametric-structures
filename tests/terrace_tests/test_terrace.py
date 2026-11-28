import math
from xml.etree import ElementTree

import pytest

from projects.terrace import model

def test_railing_nodal_forces_match_its_weight(load_case,tmp_path):
    case = load_case("terrace")
    _,loads = model.terrace_mesh(case,tmp_path/"terrace.msh")
    radius = case["geometry"]["radius_m"]
    assert all(math.hypot(x,y) == pytest.approx(radius) and z == 0 for x,y,z,_ in loads)
    assert sum(force for *_,force in loads) == pytest.approx(
        -model.railing_mass(case)*case["structural_model"]["gravity_m_s2"])

@pytest.mark.elmer
def test_balcony_reactions_balance_slab_pressure_and_railing(load_case,tmp_path,elmer_installed):
    case = load_case("terrace")
    result = tmp_path/"terrace.vtu"
    model.run_case(tmp_path/"terrace",tmp_path/"terrace.step",tmp_path/"terrace.msh",result,case)
    piece = ElementTree.parse(result).find("./UnstructuredGrid/Piece")
    points = list(map(float,piece.find("Points/DataArray").text.split()))
    reactions = list(map(float,piece.find("PointData/DataArray[@Name='deflection loads 3']").text.split()))
    total = sum(r for y,r in zip(points[1::3],reactions,strict=True) if abs(y) < 1e-6)
    radius = case["geometry"]["radius_m"]
    expected = math.pi*radius**2/2*model.strip_pressure(case)
    expected += model.railing_mass(case)*case["structural_model"]["gravity_m_s2"]
    assert total == pytest.approx(expected,rel=.001)

def test_added_reinforcement_increases_cracked_stiffness_at_same_cracking_moment(load_case):
    case = load_case("terrace")
    moment,cracked_ratio = model.section(case)
    case["reinforcement"]["top_area_mm2_per_m"] *= 1.5
    stronger_moment,stronger_ratio = model.section(case)
    assert stronger_moment == pytest.approx(moment)
    assert 0 < cracked_ratio < stronger_ratio < 1

def test_rail_mass_matches_the_step_geometry(load_case):
    case = load_case("terrace")
    parts = [shape for shape,name,_,_ in model.terrace_cad(case) if name.rsplit("/",1)[-1].startswith("Railing_")]
    assert len(parts) > 1
    assert sum(part.Volume() for part in parts)*1e-9*model.STEEL_DENSITY == pytest.approx(model.railing_mass(case))

def test_diameter_is_the_only_fixed_boundary(load_case,read_msh,tmp_path):
    path = tmp_path/"terrace.msh"
    model.terrace_mesh(load_case("terrace"),path)
    nodes,cells = read_msh(path)
    fixed = {i for kind,body,ids in cells if (kind,body) == (1,3) for i in ids}
    assert fixed
    assert fixed == {i for i,(_,y,_) in nodes.items() if abs(y) < 1e-9}

def test_strip_pressure_combines_surface_load_and_slab_self_weight(load_case):
    case = load_case("terrace")
    initial = model.strip_pressure(case)
    density = case["structural_model"]["density_kg_m3"]
    gravity = case["structural_model"]["gravity_m_s2"]
    case["geometry"]["slab_thickness_m"] += .05
    case["loads"]["surface_pressure_pa"] += 1000
    assert model.strip_pressure(case)-initial == pytest.approx(1000+.05*density*gravity)
