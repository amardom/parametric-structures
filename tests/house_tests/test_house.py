import pytest

from projects.house.model import house_mesh

def test_column_connects_base_and_both_slabs(load_case,read_msh,tmp_path):
    case = load_case("house")
    g = case["geometry"]
    path = tmp_path/"house.msh"
    house_mesh(path,g,.75)
    nodes,cells = read_msh(path)
    column = {i for kind,body,ids in cells if (kind,body) == (1,2) for i in ids}
    base = {i for kind,body,ids in cells if (kind,body) == (15,3) for i in ids}
    floor = {i for kind,body,ids in cells if (kind,body) == (3,1) for i in ids}
    roof = {i for kind,body,ids in cells if (kind,body) == (3,4) for i in ids}
    for group,height in ((base,0),(floor,g["storey_height_m"]),(roof,2*g["storey_height_m"])):
        (node,) = column & group
        assert nodes[node] == pytest.approx((g["width_m"]-g["column_setback_m"],g["depth_m"]-g["column_setback_m"],height))

def test_glass_door_fits_its_opening_in_the_lower_facade(load_case):
    from projects.house.model import house_cad

    g = load_case("house")["geometry"]
    parts = {name.rsplit("/",1)[-1]:shape for shape,name,_,_ in house_cad(g)}
    door = parts["Door_glass"]
    bounds = door.BoundingBox()
    assert (bounds.xmin+bounds.xmax)/2000 == pytest.approx(g["door_center_m"])
    front = parts["Glass_front_1"]
    assert front.intersect(door).Volume() == pytest.approx(0,abs=1e-5)

def test_setback_moves_both_cad_column_segments_together(load_case):
    from projects.house.model import house_cad

    g = load_case("house")["geometry"]
    g["column_setback_m"] += .4
    columns = [shape for shape,name,_,_ in house_cad(g) if name.rsplit("/",1)[-1].startswith("Column_")]
    assert len(columns) == 2
    for column in columns:
        bounds = column.BoundingBox()
        assert (bounds.xmin+bounds.xmax)/2000 == pytest.approx(g["width_m"]-g["column_setback_m"])
        assert (bounds.ymin+bounds.ymax)/2000 == pytest.approx(g["depth_m"]-g["column_setback_m"])

def test_wall_shells_reach_both_slab_levels(load_case,read_msh,tmp_path):
    g = load_case("house")["geometry"]
    path = tmp_path/"house.msh"
    house_mesh(path,g,.75)
    nodes,cells = read_msh(path)
    walls = {i for kind,body,ids in cells if (kind,body) == (3,3) for i in ids}
    for body in (1,4):
        slab = {i for kind,group,ids in cells if (kind,group) == (3,body) for i in ids}
        shared = [nodes[i] for i in walls & slab]
        assert len({x for x,_,_ in shared}) > 1
        assert len({y for _,y,_ in shared}) > 1
