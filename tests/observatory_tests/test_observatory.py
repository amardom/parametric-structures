import pytest

from projects.observatory.model import observatory_case_mesh

def test_reducing_transverse_arches_preserves_base_and_glass_mass(load_case):
    case = load_case("observatory")
    g = case["geometry"]
    g["transverse_arches"] = 8
    nodes,members,_,_,supports,glass = observatory_case_mesh(case)
    g["transverse_arches"] = 4
    fewer_nodes,fewer_members,_,_,fewer_supports,fewer_glass = observatory_case_mesh(case)
    assert len(fewer_members) < len(members)
    assert {nodes[i-1] for i in supports} == {fewer_nodes[i-1] for i in fewer_supports}
    assert sum(glass.values()) == pytest.approx(sum(fewer_glass.values()),rel=.001)

def test_entrance_opening_removes_base_supports_below_door(load_case):
    case = load_case("observatory")
    nodes,_,_,_,supports,_ = observatory_case_mesh(case)
    base = [nodes[i-1] for i in supports]
    radius = (case["geometry"]["diameter_m"]-case["geometry"]["wall_thickness_m"])/2
    half_door = case["geometry"]["door_width_m"]/2
    edge = (radius**2-half_door**2)**.5
    assert base
    assert all(z == 0 and x <= edge+1e-7 for x,y,z in base)
    assert max(x for x,y,z in base) == pytest.approx(edge)

def test_interior_arch_count_must_be_even(load_case):
    case = load_case("observatory")
    case["geometry"]["interior_arches"] = 5
    with pytest.raises(ValueError,match="even number"):
        observatory_case_mesh(case)

def test_circular_rib_area_equals_outer_area_minus_void():
    from math import pi
    from projects.observatory.model import tube_area

    diameter,wall = .06,.004
    assert tube_area(diameter,wall) == pytest.approx(pi/4*(diameter**2-(diameter-2*wall)**2))
