import json
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pytest

from projects.facade.model import stage_results
from website import build_data

CONFIG = Path(__file__).resolve().parents[2]/"projects"/"facade"/"historic-facade.json"

def test_props_engage_at_existing_position_and_wider_opening_settles_more():
    config = json.loads(CONFIG.read_text())
    differentials = []
    for width in config["gallery_widths_m"]:
        stations,sensors,states = stage_results(config,width)
        np.testing.assert_allclose(states[1],states[0],atol=1e-10)
        a,b = (2*stations.index(sensor) for sensor in sensors)
        motion = states[2]-states[0]
        assert motion[b] > motion[a]
        differentials.append(motion[b]-motion[a])
    assert differentials[1] > differentials[0] > 0

def test_each_stage_exports_three_drawings_and_a_result(tmp_path,monkeypatch):
    monkeypatch.setattr(build_data,"WEBSITE",tmp_path)
    build_data.build_facade(plans_only=False)
    text = (tmp_path/"facade-cases.js").read_text(encoding="utf-8")
    cases = json.loads(text.removeprefix("window.facadeCases = ").strip().removesuffix(";"))
    assert len(cases) == 8
    excavation = cases["7-excavation"]
    assert excavation["result"]["difference_mm"] == pytest.approx(
        excavation["result"]["b_mm"]-excavation["result"]["a_mm"])
    for key,variant in cases.items():
        assert variant["cad"] and variant["result"]["parts"]
        for view in ("plan","section","elevation"):
            path = tmp_path/"plans"/"facade"/f"{key}-{view}.svg"
            assert ElementTree.parse(path).getroot().tag.endswith("}svg")

def test_final_support_takes_load_from_props_at_current_position():
    from projects.facade.model import solve_stages

    states = solve_stages(np.zeros((1,1)),np.array([12.]),np.array([12.]),
                          np.array([0.]),np.array([6.]),np.array([24.]),np.zeros((1,1)))
    assert [float(state[0]) for state in states] == pytest.approx([1,1,3,3.5])

def test_temporary_props_only_appear_in_the_two_temporary_stages():
    from projects.facade.model import STAGES, parts

    config = json.loads(CONFIG.read_text())
    counts = [sum(part["material"] == "facadeProp" for part in parts(config,7,stage)) for stage in STAGES]
    assert counts == [0,2,2,0]

def test_excavation_differential_is_stable_when_station_spacing_is_halved():
    config = json.loads(CONFIG.read_text())
    def differential():
        stations,sensors,states = stage_results(config,7)
        a,b = [2*stations.index(sensor) for sensor in sensors]
        movement = states[2]-states[0]
        return movement[b]-movement[a]

    baseline = differential()
    config["element_size_m"] /= 2
    assert differential() == pytest.approx(baseline,rel=.02)

def test_scaled_line_load_scales_every_stage_movement(load_case):
    case = load_case("facade")
    width = case["gallery_width_m"]
    stations,sensors,states = stage_results(case,width)
    case["line_load_n_m"] *= 2
    double_stations,double_sensors,double_states = stage_results(case,width)
    assert double_stations == stations
    assert double_sensors == sensors
    np.testing.assert_allclose(double_states,2*np.asarray(states),rtol=1e-8,atol=1e-10)
