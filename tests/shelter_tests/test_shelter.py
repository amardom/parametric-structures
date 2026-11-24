import pytest

from projects.shelter.geometry import build_concrete_geometry
from projects.shelter.model import generate_shell_mesh

def test_window_translates_with_offset_and_leaves_a_mesh_opening(load_case,read_msh,tmp_path):
    case = load_case("shelter")
    original = build_concrete_geometry(case["geometry"])["rear_window"]
    case["geometry"]["rear_window"]["offset_m"] += .9
    geometry = build_concrete_geometry(case["geometry"])
    window = geometry["rear_window"]
    left,y0,sill = window["min"]
    right,y1,_ = window["max"]
    assert left-original["min"][0] == pytest.approx(.9)
    assert right-original["max"][0] == pytest.approx(.9)
    path = tmp_path/"shelter.msh"
    generate_shell_mesh(geometry,path,.6)
    nodes,cells = read_msh(path)
    rear_cells = [tuple(nodes[i] for i in ids) for kind,body,ids in cells if (kind,body) == (3,2)
                  and all(abs(nodes[i][1]-(y0+y1)/2)<1e-7 for i in ids)]
    assert rear_cells
    for panel in rear_cells:
        x,_,z = (sum(axis)/len(panel) for axis in zip(*panel,strict=True))
        assert not (left < x < right and z > sill)

def test_window_cannot_cross_a_side_wall(load_case):
    dimensions = load_case("shelter")["geometry"]
    dimensions["rear_window"]["offset_m"] = (dimensions["width_m"]-dimensions["rear_window"]["width_m"])/2
    with pytest.raises(ValueError,match="fit between the side walls"):
        build_concrete_geometry(dimensions)

def test_cad_glazing_stays_inside_shifted_rear_opening(load_case):
    from projects.shelter.model import build_concrete_cad_model

    dimensions = load_case("shelter")["geometry"]
    dimensions["rear_window"]["offset_m"] = .7
    geometry = build_concrete_geometry(dimensions)
    parts = {name.rsplit("/",1)[-1]:shape for shape,name,_,_ in build_concrete_cad_model(geometry)}
    glazing = parts["Rear_glass"]
    bounds = glazing.BoundingBox()
    window = geometry["rear_window"]
    assert bounds.xmin/1000 == pytest.approx(window["min"][0])
    assert bounds.xmax/1000 == pytest.approx(window["max"][0])
    assert glazing.intersect(parts["Wall_rear"]).Volume() == pytest.approx(0,abs=1e-5)

def test_roof_shell_connects_all_three_walls(load_case,read_msh,tmp_path):
    geometry = build_concrete_geometry(load_case("shelter")["geometry"])
    path = tmp_path/"shelter.msh"
    generate_shell_mesh(geometry,path,.6)
    nodes,cells = read_msh(path)
    roof = {i for kind,body,ids in cells if (kind,body) == (3,1) for i in ids}
    walls = {i for kind,body,ids in cells if (kind,body) == (3,2) for i in ids}
    shared = [nodes[i] for i in roof & walls]
    thickness = geometry["walls"]["left"]["max"][0]
    width,depth,_ = geometry["roof"]["max"]
    for axis,coordinate in ((0,thickness/2),(0,width-thickness/2),(1,depth-thickness/2)):
        assert sum(point[axis] == pytest.approx(coordinate) for point in shared) > 2
