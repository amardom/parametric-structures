import pytest

from projects.gable.model import gable_dimensions, gable_mesh, loading

def test_uplift_requires_a_roof_overhang(load_case):
    case = load_case("gable")
    case["geometry"]["projection_m"] = 0
    case["loads"]["corner_uplift_pa"] = 1000
    with pytest.raises(ValueError,match="projecting roof"):
        loading(case)

def test_wind_zone_is_in_the_overhang(load_case,read_msh,tmp_path):
    case = load_case("gable")
    width,depth,eave,rise,*_ = gable_dimensions(case)
    path = tmp_path/"gable.msh"
    gable_mesh(path,width,depth,eave,rise,.6,projection=1)
    nodes,cells = read_msh(path)
    zone = [ids for kind,body,ids in cells if (kind,body) == (3,3)]
    assert zone
    assert all(-1.01 <= nodes[i][1] <= .001 for ids in zone for i in ids)

def test_four_fixed_nodes_are_the_column_feet(load_case,read_msh,tmp_path):
    width,depth,eave,rise,*_ = gable_dimensions(load_case("gable"))
    path = tmp_path/"gable.msh"
    gable_mesh(path,width,depth,eave,rise,.7)
    nodes,cells = read_msh(path)
    fixed = {nodes[ids[0]] for kind,body,ids in cells if (kind,body) == (15,3)}
    columns = {nodes[i] for kind,body,ids in cells if (kind,body) == (1,2) for i in ids}
    assert fixed == {(x,y,0) for x in (0,width) for y in (0,depth)}
    assert fixed <= columns

def test_roof_ridge_spans_the_full_building_depth(load_case,read_msh,tmp_path):
    width,depth,eave,rise,*_ = gable_dimensions(load_case("gable"))
    path = tmp_path/"gable.msh"
    gable_mesh(path,width,depth,eave,rise,.7)
    nodes,cells = read_msh(path)
    ridge = [nodes[i] for kind,body,ids in cells if (kind,body) == (3,1)
             for i in ids if nodes[i][2] == pytest.approx(eave+rise)]
    assert ridge
    assert all(x == pytest.approx(width/2) for x,_,_ in ridge)
    assert min(y for _,y,_ in ridge) == pytest.approx(0)
    assert max(y for _,y,_ in ridge) == pytest.approx(depth)

def test_negative_roof_pressure_is_rejected(load_case):
    case = load_case("gable")
    case["loads"]["roof_pressure_pa"] = -1
    with pytest.raises(ValueError,match="non-negative"):
        loading(case)
