import pytest

from projects.canopy.solid import bolt_centres

@pytest.mark.parametrize("count",[4,6])
def test_anchor_layout_adds_a_middle_row_symmetrically(count,load_case):
    geometry = load_case("canopy")["geometry"]
    geometry["bolts"] = count
    centres = set(bolt_centres(geometry))
    assert len(centres) == count
    assert all((-x,z) in centres and (x,-z) in centres for x,z in centres)
    assert sum(z == 0 for x,z in centres) == (2 if count == 6 else 0)

def test_anchor_height_preserves_the_specified_tie_angle(load_case):
    from math import atan2,degrees

    from projects.canopy.model import CANOPY_LEVEL, PIN_OFFSET, anchor_height

    case = load_case("canopy")
    geometry = case["geometry"]
    angle = 35
    rise = anchor_height(geometry,angle)-CANOPY_LEVEL
    run = geometry["canopy_depth_m"]-PIN_OFFSET
    assert degrees(atan2(rise,run)) == pytest.approx(angle)

def test_higher_tie_angle_raises_the_anchor(load_case):
    from projects.canopy.model import anchor_height

    geometry = load_case("canopy")["geometry"]
    low,nominal,high = (anchor_height(geometry,angle) for angle in (30,45,60))
    assert low < nominal < high

def test_larger_bolt_edge_distance_raises_wall_without_moving_anchor(load_case):
    from projects.canopy.model import anchor_height, canopy_cad

    g = load_case("canopy")["geometry"]
    initial_anchor = anchor_height(g,45)
    def wall_top():
        (wall,) = (shape for shape,name,_,_ in canopy_cad(g,45) if name.rsplit("/",1)[-1] == "Concrete")
        return wall.BoundingBox().zmax/1000

    before = wall_top()
    g["edge_distance_m"] += .04
    assert wall_top()-before == pytest.approx(.04)
    assert anchor_height(g,45) == initial_anchor
