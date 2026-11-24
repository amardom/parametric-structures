import pytest

from projects.hypar.model import corners, wall_moment

def test_free_tips_are_opposite_and_wall_edge_is_level(load_case):
    case = load_case("hypar")
    g = case["geometry"]
    a,b,c,d = corners(g)
    assert a[0] == d[0] == a[2] == d[2] == 0
    assert b[0] == c[0] == g["projection_m"]
    assert c[2] == -b[2] == g["tip_rise_m"]

def test_uplift_in_either_half_contributes_same_wall_moment(load_case):
    case = load_case("hypar")
    case["loads"] = {"left_uplift_pa":0,"right_uplift_pa":0}
    gravity = wall_moment(case)
    case["loads"]["left_uplift_pa"] = 1000
    left = wall_moment(case)
    case["loads"] = {"left_uplift_pa":0,"right_uplift_pa":1000}
    assert wall_moment(case) == pytest.approx(left)
    assert left > gravity

def test_fixed_edge_nodes_cover_the_full_width(load_case):
    from projects.hypar.model import surface_cells

    case = load_case("hypar")
    plates,tubes,fixed = surface_cells(case)
    half = case["geometry"]["width_m"]/2
    assert fixed[0] == (0,-half,0)
    assert fixed[-1] == (0,half,0)
    roof_nodes = {point for _,panel in plates for point in panel}
    assert set(fixed) == {node for node in roof_nodes if node[0] == 0}
    assert all(not (a[0] == b[0] == 0) for a,b in tubes)

def test_wall_moment_increases_in_magnitude_with_cantilever_length(load_case):
    case = load_case("hypar")
    case["loads"] = dict.fromkeys(case["loads"],0)
    short = wall_moment(case)
    case["geometry"]["projection_m"] *= 2
    long = wall_moment(case)
    assert long < short < 0

def test_plate_mesh_contains_all_four_cad_corners(load_case):
    from projects.hypar.model import surface_cells

    case = load_case("hypar")
    plates,_,_ = surface_cells(case)
    nodes = {point for _,panel in plates for point in panel}
    assert set(corners(case["geometry"])) <= nodes
