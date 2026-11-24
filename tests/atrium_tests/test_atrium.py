from math import dist, radians

import pytest

from projects.atrium import model

def test_guardrail_mass_matches_cad(load_case):
    case = load_case("atrium")
    guardrail = [(shape,name) for shape,name,_,_ in model.geometry(case) if "Guard_" in name]
    assert any("Guard_glass" in name for _,name in guardrail)
    expected = sum(shape.Volume()*1e-9*(2500 if "Guard_glass" in name else 7850) for shape,name in guardrail)
    assert model.guard_mass(case["geometry"]) == pytest.approx(expected)

def test_hanger_is_a_spring_in_harmonic_solver(load_case,tmp_path):
    case = load_case("atrium")
    _,_,areas,_ = model.native_mesh(case,tmp_path/"mesh",tmp_path/"atrium.msh")
    deck_area = areas[2]
    assert deck_area > 0
    solver_input = model.sif(case,5.25,areas)
    assert "Harmonic Mode = Logical True" in solver_input
    assert "Frequency = Real 5.25" in solver_input
    assert "Spring 3 = Real" in solver_input

def test_guardrails_add_their_mass_to_the_deck_in_elmer(load_case,tmp_path):
    case = load_case("atrium")
    _,_,areas,_ = model.native_mesh(case,tmp_path/"mesh",tmp_path/"atrium.msh")
    deck = case["geometry"]
    volume = deck["radius_m"]*radians(deck["angle_deg"])*deck["width_m"]*deck["deck_depth_m"]
    density_line = next(line for line in model.sif(case,5,areas).splitlines() if "Density = Real" in line)
    density = float(density_line.split()[-1])
    assert (density-case["structural_model"]["density_kg_m3"])*volume == pytest.approx(model.guard_mass(deck))

def test_landing_starts_at_each_deck_end(load_case):
    g = load_case("atrium")["geometry"]
    for end in (0,1):
        a,b,c,d = model.landing_outline(g,end)
        assert a == model.deck_point(g,end,0)[:2]
        assert b == model.deck_point(g,end,1)[:2]
        assert dist(a,b) == pytest.approx(g["width_m"])
        assert dist(a,d) == pytest.approx(model.LANDING_LENGTH)
        assert dist(b,c) == pytest.approx(model.LANDING_LENGTH)

def test_exterior_faces_omit_shared_hex_face():
    faces = model.outer_faces([(1,2,3,4,5,6,7,8),(2,9,10,3,6,11,12,7)])
    assert len(faces) == 10
    assert {1,2,5,6} not in [set(face) for face in faces]
