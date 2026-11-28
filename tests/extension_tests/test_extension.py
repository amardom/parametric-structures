from projects.extension.model import extension_mesh

def test_stiffeners_are_added_at_column_without_changing_other_cells(load_case,read_msh,tmp_path):
    case = load_case("extension")
    plain,stiffened = (tmp_path/name for name in ("plain.msh","stiffened.msh"))
    connection = case["connection"]
    extension_mesh(plain,case,connection)
    extension_mesh(stiffened,case,connection,stiffened=True)

    def panels(path):
        nodes,cells = read_msh(path)
        return [(kind,body,tuple(nodes[i] for i in ids)) for kind,body,ids in cells]

    baseline = panels(plain)
    updated = panels(stiffened)
    stiffeners = [points for kind,body,points in updated if (kind,body) == (3,5)]
    assert stiffeners
    assert baseline == [cell for cell in updated if cell[:2] != (3,5)]
    assert {x for panel in stiffeners for x,_,_ in panel} == {case["geometry"]["column_offset_m"]}

def test_loaded_shell_area_matches_the_column_footprint(load_case,read_msh,tmp_path):
    from pytest import approx

    case = load_case("extension")
    path = tmp_path/"extension.msh"
    extension_mesh(path,case)
    nodes,cells = read_msh(path)
    area = 0
    for kind,body,ids in cells:
        if (kind,body) == (3,4):
            xs,ys,_ = zip(*(nodes[i] for i in ids),strict=True)
            area += (max(xs)-min(xs))*(max(ys)-min(ys))
    assert area == approx(case["geometry"]["column_side_m"]**2)

def test_wall_supports_are_fixed_at_opposite_ends(load_case,read_msh,tmp_path):
    case = load_case("extension")
    path = tmp_path/"extension.msh"
    extension_mesh(path,case)
    nodes,cells = read_msh(path)
    fixed = {ids[0] for kind,body,ids in cells if (kind,body) == (15,3)}
    walls = [ids for kind,body,ids in cells if (kind,body) == (1,2)]
    g = case["geometry"]
    assert {nodes[i] for i in fixed} == {(0,0,-g["wall_height_m"]),(g["span_m"],0,-g["wall_height_m"])}
    assert len(walls) == 2
    assert all(len(set(ids)&fixed) == 1 for ids in walls)

def test_load_patch_follows_column_offset(load_case,read_msh,tmp_path):
    from pytest import approx

    case = load_case("extension")
    path = tmp_path/"extension.msh"
    g = case["geometry"]
    g["column_offset_m"] = g["span_m"]*.65
    extension_mesh(path,case)
    nodes,cells = read_msh(path)
    xs = [nodes[i][0] for kind,body,ids in cells if (kind,body) == (3,4) for i in ids]
    assert (min(xs),max(xs)) == approx((g["column_offset_m"]-g["column_side_m"]/2,
                                       g["column_offset_m"]+g["column_side_m"]/2))

def test_mirrored_column_offset_preserves_load_patch_area(load_case,read_msh,tmp_path):
    import numpy as np

    case = load_case("extension")
    g = case["geometry"]
    span = g["span_m"]
    patches = []
    for offset in (.25*span,.75*span):
        g["column_offset_m"] = offset
        path = tmp_path/f"offset-{offset:g}.msh"
        extension_mesh(path,case)
        nodes,cells = read_msh(path)
        loaded = [np.array([nodes[node] for node in ids])
                  for kind,body,ids in cells if (kind,body) == (3,4)]
        assert loaded
        patches.append(sorted(tuple(round(float(x),7) for x in point)
                              for face in loaded for point in face))
    assert sorted((round(span-x,7),y,z) for x,y,z in patches[0]) == patches[1]
