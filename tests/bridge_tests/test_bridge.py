import pytest

from projects.bridge.model import bridge_mesh

def test_hanger_loss_removes_one_midspan_hanger(load_case,read_msh,tmp_path):
    case = load_case("bridge")
    case["hangers"]["count_per_side"] = 5
    intact,damaged = (tmp_path/name for name in ("intact.msh","damaged.msh"))
    bridge_mesh(intact,case)
    bridge_mesh(damaged,case,remove_midspan_hanger=True)

    def hangers(path):
        nodes,cells = read_msh(path)
        return {tuple(nodes[node] for node in ids) for kind,body,ids in cells if (kind,body) == (1,2)}

    original,remaining = hangers(intact),hangers(damaged)
    assert len(original) == 10
    assert remaining < original
    (removed,) = original-remaining
    assert removed[0] == pytest.approx((case["geometry"]["span_m"]/2,-case["geometry"]["deck_width_m"]/2,0))

def test_hangers_are_symmetric_about_the_arch_crown(load_case):
    from projects.bridge.model import arch_height, hanger_stations

    case = load_case("bridge")
    geometry = case["geometry"]
    span = geometry["span_m"]
    hangers = hanger_stations(case)
    for left,right in zip(hangers,reversed(hangers),strict=True):
        assert 0 < left < span
        assert left+right == pytest.approx(span)
        assert arch_height(geometry,left) == pytest.approx(arch_height(geometry,right))
    assert arch_height(geometry,span/2)-arch_height(geometry,0) == pytest.approx(geometry["arch_rise_m"])

def test_hanger_loss_requires_a_midspan_hanger(load_case,tmp_path):
    case = load_case("bridge")
    case["hangers"]["count_per_side"] = 4
    with pytest.raises(ValueError,match="requires a hanger at midspan"):
        bridge_mesh(tmp_path/"bridge.msh",case,remove_midspan_hanger=True)

def test_deck_nodes_are_shared_by_every_hanger(load_case,read_msh,tmp_path):
    path = tmp_path/"bridge.msh"
    bridge_mesh(path,load_case("bridge"))
    nodes,cells = read_msh(path)
    deck = {i for kind,body,ids in cells if (kind,body) == (3,1) for i in ids}
    hangers = [ids for kind,body,ids in cells if (kind,body) == (1,2)]
    assert hangers
    for bottom,top in hangers:
        assert bottom in deck and top not in deck
        assert nodes[bottom][:2] == nodes[top][:2]
        assert nodes[top][2] > 0

def test_hanger_mesh_reaches_the_arch_axis_and_deck(load_case,read_msh,tmp_path):
    from projects.bridge.model import arch_height

    case = load_case("bridge")
    path = tmp_path/"bridge.msh"
    bridge_mesh(path,case)
    nodes,cells = read_msh(path)
    hangers = [ids for kind,body,ids in cells if (kind,body) == (1,2)]
    arch_nodes = {node for kind,body,ids in cells if (kind,body) == (3,3) for node in ids}
    assert hangers
    for a,b in hangers:
        low,high = sorted((a,b),key=lambda node:nodes[node][2])
        x,y,z = nodes[low]
        assert z == 0
        assert high in arch_nodes
        assert nodes[high] == pytest.approx((x,y,arch_height(case["geometry"],x)))
