from xml.etree import ElementTree

import pytest

from main import PROJECTS

@pytest.mark.parametrize("project", [
    "atrium", "bridge", "brutalist", "cabin", "canopy", "extension",
    "gable", "house", "hypar", "observatory", "shelter", "terrace",
])
def test_case_exports_three_svg_drawings(project, load_case, tmp_path):
    case = load_case(project)
    PROJECTS[case["structural_model"]["model"]].draw_case(tmp_path / project,case)
    drawings = sorted(tmp_path.glob("*.svg"))
    assert [path.stem for path in drawings] == [f"{project}-{view}" for view in ("elevation","plan","section")]
    for path in drawings:
        svg = ElementTree.parse(path).getroot()
        assert svg.tag == "{http://www.w3.org/2000/svg}svg"
        assert svg.find("{http://www.w3.org/2000/svg}title").text
