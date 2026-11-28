import json
from pathlib import Path

import numpy as np
import pytest

from projects.slab.model import CORNERS, solve_model, strain_matrix

CONFIG = Path(__file__).resolve().parents[2]/"projects"/"slab"/"slab-opening.json"

def test_brick_recovers_a_uniform_vertical_shear_strain():
    dimensions = np.array([.11,.17,.06])
    coords = (CORNERS+1)*dimensions/2
    displacement = np.zeros_like(coords)
    displacement[:,2] = .002*coords[:,0]
    strain = strain_matrix((.2,-.3,.4),dimensions)@displacement.ravel()
    np.testing.assert_allclose(strain,[0,0,0,0,0,.002],atol=1e-14)

def test_opening_redistributes_vertical_shear_at_the_same_column_reaction():
    config = json.loads(CONFIG.read_text())
    baseline,near = (solve_model(config,variant)["result"] for variant in ("none","near"))
    assert baseline["shares"] == pytest.approx([25]*4)
    assert near["reaction_kn"] == pytest.approx(baseline["reaction_kn"])
    assert sum(near["shares"]) == pytest.approx(100)
    assert near["shares"][1] < baseline["shares"][1]
    assert near["shares"][2] == pytest.approx(near["shares"][3])

def test_through_opening_removes_exact_hole_volume_at_either_position():
    from projects.slab.model import mesh

    config = json.loads(CONFIG.read_text())
    volumes = [np.prod(mesh(config,state)[2],axis=1).sum() for state in ("none","near","far")]
    hole_volume = config["opening_width_m"]*config["opening_length_m"]*config["slab_thickness_m"]
    assert np.asarray(volumes[0])-volumes[1:] == pytest.approx([hole_volume,hole_volume])

def test_duct_leaves_analysis_cut_clear_and_is_absent_without_opening():
    from projects.slab.model import architectural_context

    config = json.loads(CONFIG.read_text())
    assert [part["material"] for part in architectural_context(config,"none",show_cut=False)] == ["slabPlinth"]
    duct = next(part for part in architectural_context(config,"near",show_cut=True)
                if part["material"] == "slabDuct")
    assert max(duct["points"][2::3]) < 0

def test_cut_shear_excludes_the_load_applied_inside_the_cut():
    config = json.loads(CONFIG.read_text())
    result = solve_model(config,"none")["result"]
    loaded_fraction_inside = (config["control_half_width_m"]/config["half_span_m"])**2
    assert result["shear_kn"] == pytest.approx(result["reaction_kn"]*(1-loaded_fraction_inside))

def test_near_opening_interrupts_the_east_cut_while_far_opening_does_not(load_case):
    from projects.slab.model import mesh

    config = load_case("slab")
    cut = config["control_half_width_m"]
    for variant in ("near","far"):
        nodes,cells,_ = mesh(config,variant)
        faces = nodes[cells[:,[1,5,6,2]]]
        face_centres = faces.mean(axis=1)
        on_east_cut = np.all(np.isclose(faces[:,:,0],cut),axis=1) & (np.abs(face_centres[:,1]) < cut)
        east = faces[on_east_cut]
        area = sum(np.ptp(face[:,1])*np.ptp(face[:,2]) for face in east)
        opening_width_on_cut = config["opening_length_m"] if variant == "near" else 0
        assert area == pytest.approx((2*cut-opening_width_on_cut)*config["slab_thickness_m"])
