import pytest

from projects.cabin import thermal

def test_louvres_reduce_west_window_solar_gain(load_case):
    case = load_case("cabin")
    case["windows"]["main_facade"] = "west"
    _,solar,unshaded = thermal.weather_at(case,16*3600)
    case["windows"]["shaded"] = True
    _,shaded_solar,shaded = thermal.weather_at(case,16*3600)
    assert shaded_solar == solar
    assert 0 < shaded < unshaded

@pytest.mark.elmer
def test_isothermal_cabin_stays_at_initial_temperature(load_case,tmp_path,monkeypatch,elmer_installed):
    case = load_case("cabin")
    case["use"]["internal_gains_w"] = 0
    case["weather"]["ground_c"] = 23
    monkeypatch.setattr(thermal,"weather_at",lambda case,time:(23,dict.fromkeys(thermal.FACADES,0),0))
    frames = thermal.solve_heat(case,tmp_path/"cabin.msh",tmp_path/"cabin.vtu")
    assert len(frames) == 73
    assert all(frame["air"] == pytest.approx(23,abs=.001) for frame in frames)

def test_window_orientation_changes_afternoon_gain_at_same_outdoor_temperature(load_case):
    case = load_case("cabin")
    case["windows"].update(main_facade="south",shaded=False)
    outdoor,solar,south = thermal.weather_at(case,17*3600)
    case["windows"]["main_facade"] = "west"
    west_outdoor,west_solar,west = thermal.weather_at(case,17*3600)
    assert (west_outdoor,west_solar) == (outdoor,solar)
    assert west > south

def test_midnight_has_no_solar_gain(load_case):
    case = load_case("cabin")
    _,solar,gain = thermal.weather_at(case,24*3600)
    assert solar == dict.fromkeys(thermal.FACADES,0)
    assert gain == 0

def test_weather_repeats_each_simulated_day(load_case):
    case = load_case("cabin")
    for hour in (0,8,12,17,23):
        assert thermal.weather_at(case,hour*3600) == thermal.weather_at(case,(hour+24)*3600)

def test_glazing_solar_factor_scales_transmission_only(load_case):
    case = load_case("cabin")
    original,irradiance,gain = thermal.weather_at(case,15*3600)
    assert gain > 0
    case["windows"]["solar_factor"] *= .5
    outdoor,solar,transmitted = thermal.weather_at(case,15*3600)
    assert outdoor == original
    assert solar == irradiance
    assert transmitted == pytest.approx(gain/2)
