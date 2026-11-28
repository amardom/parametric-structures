import json
from pathlib import Path

import numpy as np
import pytest

from projects.vierendeel.model import SECTIONS, local_stiffness, section_properties, solve_frame, window_measures

CONFIG = Path(__file__).resolve().parents[2]/"projects"/"vierendeel"/"cantilever-building.json"

def test_beam_element_reproduces_cantilever_tip_deflection():
    length,young,shear,force = 3.,210e9,81e9,12500.
    section = SECTIONS["chord"]
    _,iy,_,_ = section_properties(*section)
    stiffness = local_stiffness(length,young,shear,section)
    load = np.array([0,0,-force,0,0,0])
    displacement = np.linalg.solve(stiffness[6:,6:],load)
    assert displacement[2] == pytest.approx(-force*length**3/(3*young*iy))

def test_asymmetric_loading_and_flexible_joints_increase_movement():
    config = json.loads(CONFIG.read_text())
    nodes,_,rigid = solve_frame(config,4,"rigid")
    _,_,flexible = solve_frame(config,4,"flexible")
    assert flexible[3,0,0][2] < rigid[3,0,0][2] < rigid[3,1,0][2] < 0
    assert sum(map(abs,window_measures(nodes,flexible))) > sum(map(abs,window_measures(nodes,rigid)))

    config["near_side_load_fraction"] = .5
    _,_,symmetric = solve_frame(config,4,"rigid")
    assert symmetric[3,0,0][2] == pytest.approx(symmetric[3,1,0][2])

def test_joint_spring_approaches_rigid_element_as_stiffness_increases():
    from projects.vierendeel.model import flexible_ends

    elastic = local_stiffness(3.2,210e9,81e9,SECTIONS["post"])
    nearly_rigid = flexible_ends(elastic,1e14)
    np.testing.assert_allclose(nearly_rigid,elastic,atol=1.0,rtol=1e-5)

def test_member_stiffness_does_not_resist_rigid_body_translation():
    k = local_stiffness(4,210e9,81e9,SECTIONS["chord"])
    translation = np.tile([1.,-2.,.5,0,0,0],2)
    np.testing.assert_allclose(k@translation,0,atol=1e-6)

def test_narrower_facade_bays_add_posts_without_extending_the_cantilever():
    from projects.vierendeel.model import frame

    config = json.loads(CONFIG.read_text())
    narrow,narrow_members = frame(config,3)
    wide,wide_members = frame(config,4)
    assert max(x for x,_,_ in narrow.values()) == max(x for x,_,_ in wide.values()) == config["length_m"]
    assert sum(kind == "post" for _,_,kind in narrow_members) == 20
    assert sum(kind == "post" for _,_,kind in wide_members) == 16

def test_balanced_gravity_load_produces_symmetric_frame_deflection(load_case):
    case = load_case("vierendeel")
    case["near_side_load_fraction"] = .5
    for joint in ("rigid","flexible"):
        nodes,_,motion = solve_frame(case,case["bay_width_m"],joint)
        for station,side,level in nodes:
            if side == 0:
                np.testing.assert_allclose(motion[station,side,level],
                                           motion[station,1,level]*[1,-1,1],atol=1e-10)
