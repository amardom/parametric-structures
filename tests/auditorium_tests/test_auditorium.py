import json
from math import dist, sqrt
from pathlib import Path

import pytest

from projects.auditorium.model import decay_time, reflection, reflection_paths

CONFIG = Path(__file__).resolve().parents[2]/"projects"/"auditorium"/"auditorium.json"

def test_flat_ceiling_reflection_is_symmetric_for_equal_height_endpoints():
    source,receiver = (1,1),(7,1)
    point = reflection(source,receiver,(0,4),(8,4))
    assert point == pytest.approx((4,4))
    assert dist(source,point) == pytest.approx(dist(receiver,point))
    assert reflection(source,receiver,(0,4),(3,4)) is None

def test_rear_absorption_reduces_reflection_gain_and_decay_without_moving_the_ray():
    case = json.loads(CONFIG.read_text())
    receiver = case["seats_m"][-1]
    untreated,treated = (
        next(path for path in reflection_paths(case,"folded",rear,receiver) if path["kind"] == "rear wall")
        for rear in ("reflective","absorptive")
    )
    assert untreated["points"] == treated["points"]
    assert untreated["delay_ms"] == treated["delay_ms"]
    absorption = case["absorption"]
    assert treated["gain"]/untreated["gain"] == pytest.approx(
        sqrt((1-absorption["rear_panels"][1])/(1-absorption["rear_wall"][1])))
    assert decay_time(case,"folded","absorptive") < decay_time(case,"folded","reflective")

def test_flat_ceiling_arrives_at_the_image_source_delay():
    case = json.loads(CONFIG.read_text())
    source = case["stage_source_m"]
    seat = case["seats_m"][1]
    path = next(path for path in reflection_paths(case,"flat","reflective",seat)
                if path["kind"] == "ceiling")
    image = (source[0],2*case["flat_ceiling_m"]-source[1])
    expected = 1000*(dist(image,seat)-dist(source,seat))/case["sound_speed_m_s"]
    assert path["delay_ms"] == pytest.approx(expected)

def test_rear_reflection_arrives_sooner_as_the_listener_moves_back():
    case = json.loads(CONFIG.read_text())
    delays = [next(path["delay_ms"] for path in reflection_paths(case,"folded","reflective",seat)
                   if path["kind"] == "rear wall") for seat in case["seats_m"]]
    assert delays[0] > delays[1] > delays[2] > 0

def test_plans_only_exports_all_selectable_variants(tmp_path,monkeypatch):
    from xml.etree import ElementTree

    from projects.auditorium.model import ROOFS, ROWS, WALLS
    from website import build_data

    monkeypatch.setattr(build_data,"WEBSITE",tmp_path)
    build_data.build_auditorium(plans_only=True)
    plans = tmp_path/"plans"/"auditorium"
    expected = {f"{roof}-{wall}-{row}-{view}.svg" for roof in ROOFS for wall in WALLS
                for row in ROWS for view in ("plan","elevation","section")}
    assert {path.name for path in plans.iterdir()} == expected
    for name in expected:
        assert ElementTree.parse(plans/name).getroot().tag.endswith("}svg")

def test_audio_keeps_the_direct_arrival_and_the_first_echo():
    import numpy as np

    from projects.auditorium.model import render_speech

    paths = [{"delay_ms":0,"gain":.5},{"delay_ms":20,"gain":.2}]
    samples = render_speech(1000,np.array([1.0]),paths,decay=1.0)
    assert samples[0] == pytest.approx(.5)
    assert samples[20] == pytest.approx(.2)
    assert np.linalg.norm(samples[55:]) == pytest.approx(.20)

def test_absorptive_treatment_shortens_all_three_decay_bands():
    case = json.loads(CONFIG.read_text())
    untreated = [decay_time(case,"flat","reflective",band) for band in range(3)]
    treated = [decay_time(case,"flat","absorptive",band) for band in range(3)]
    assert all(a < b for a,b in zip(treated,untreated,strict=True))
    assert treated[2]/untreated[2] < treated[0]/untreated[0]
