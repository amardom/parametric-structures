import pytest

from projects.brutalist.model import ACCESS_HEIGHT, ACCESS_Y, housing_mesh, volumes

def test_core_accesses_remove_wall_area_from_mesh_and_objective(load_case):
    case = load_case("brutalist")
    def core_wall_area(openings):
        nodes,cells,_ = housing_mesh(case,core_openings=openings)
        area = 0
        for body,a,b,c,d in cells:
            if body in (2,4,6):
                p,q,r = (nodes[i-1] for i in (a,b,c))
                area += (abs(q[0]-p[0])+abs(q[1]-p[1]))*(r[2]-q[2])
        return area

    closed,opened = core_wall_area(False),core_wall_area(True)
    assert closed-opened == pytest.approx(2*case["geometry"]["storeys"]*(ACCESS_Y[1]-ACCESS_Y[0])*ACCESS_HEIGHT)
    _,areas = volumes(case)
    assert sum(areas[::2]) == pytest.approx(opened)

def test_adding_three_storeys_extends_each_thickness_band_equally(load_case):
    case = load_case("brutalist")
    fixed,areas = volumes(case)
    case["geometry"]["storeys"] += 3
    larger_fixed,larger_areas = volumes(case)
    increments = [new-old for old,new in zip(areas,larger_areas,strict=True)]
    assert increments[0] > 0 and increments[1] > 0
    assert increments == pytest.approx(increments[:2]*3)
    assert (larger_fixed-fixed)/3 == pytest.approx(fixed/(case["geometry"]["storeys"]-3))

def test_shell_mesh_is_fixed_only_at_ground_level(load_case):
    nodes,cells,supports = housing_mesh(load_case("brutalist"))
    assert supports
    assert set(supports) == {i for i,(_,_,z) in enumerate(nodes,1) if z == 0}
    assert all(node in cells[parent-1][1:] for node,parent in supports.items())

def test_floor_shells_leave_the_core_shaft_clear(load_case):
    from projects.brutalist.model import CORE, SLAB_AREA

    nodes,cells,_ = housing_mesh(load_case("brutalist"))
    area_by_level = {}
    for body,*ids in cells:
        if body != 1:
            continue
        xs,ys,zs = zip(*(nodes[i-1] for i in ids),strict=True)
        assert len(set(zs)) == 1
        assert min(xs) >= CORE/2 or max(xs) <= -CORE/2 or min(ys) >= CORE/2 or max(ys) <= -CORE/2
        area_by_level[zs[0]] = area_by_level.get(zs[0],0)+(max(xs)-min(xs))*(max(ys)-min(ys))
    assert len(area_by_level) == load_case("brutalist")["geometry"]["storeys"]
    assert all(area == pytest.approx(SLAB_AREA) for area in area_by_level.values())

def test_band_area_changes_match_wall_area_of_added_storeys(load_case):
    case = load_case("brutalist")
    case["geometry"]["storeys"] = 6
    _,areas = volumes(case)
    case["geometry"]["storeys"] = 7
    _,extended = volumes(case)
    assert extended[:2] == pytest.approx([1.5*area for area in areas[:2]])
    assert extended[2:] == pytest.approx(areas[2:])
