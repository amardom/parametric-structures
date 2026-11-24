from html.parser import HTMLParser
from itertools import product
import json
from pathlib import Path
import re
from xml.etree import ElementTree

import pytest

WEBSITE = Path(__file__).resolve().parents[2] / "website"

class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.routes = set()
        self.scripts = []

    def handle_starttag(self,tag,attributes):
        attributes = dict(attributes)
        href = attributes.get("href","")
        if tag == "a" and href.startswith("#"):
            self.routes.add(href[1:])
        if tag == "script" and "src" in attributes:
            self.scripts.append(attributes["src"].split("?",1)[0])

@pytest.fixture(scope="module")
def website():
    page = PageLinks()
    page.feed((WEBSITE/"index.html").read_text(encoding="utf-8"))
    source = (WEBSITE/"viewer.js").read_text(encoding="utf-8")
    groups = re.findall(
        r'^  (\w+): \{\n    planFolder: "(\w+)",.*?^    options: (.*?),\n'
        r'    selected: (.*?),\n    cases: window\.(\w+)(\?\.variants)?,',
        source,re.MULTILINE | re.DOTALL,
    )
    projects = {}
    for route,folder,options,selected,global_name,nested in groups:
        keys = {"-".join(map(str,values)) for values in product(
            *([option[0] for option in group] for group in json.loads(options))
        )}
        projects[route] = (folder,keys,"-".join(json.loads(selected)),global_name,nested)
    return page,projects

def test_navigation_has_one_route_per_project(website):
    page,projects = website
    source_projects = {p.parent.name for p in (WEBSITE.parent/"projects").glob("*/*.json")
                       if not p.name.endswith("-results.json")}
    assert page.routes == set(projects) == source_projects

def test_default_variants_and_script_order(website):
    page,projects = website
    viewer = page.scripts.index("viewer.js")
    for route,(_,keys,selected,_,_) in projects.items():
        assert selected in keys,route
        script = "cases.js" if route == "shelter" else f"{route}-cases.js"
        assert page.scripts.index(script) < viewer,route
    assert page.scripts.index("depth-renderer.js") < viewer

def test_generated_data_and_drawings_match_selectable_variants(website):
    _,projects = website
    if not any(WEBSITE.glob("*cases.js")):
        pytest.skip("Generate the website with python website/build_data.py.")
    for route,(folder,keys,_,global_name,nested) in projects.items():
        name = "cases.js" if route == "shelter" else f"{route}-cases.js"
        prefix = f"window.{global_name} = "
        text = (WEBSITE/name).read_text(encoding="utf-8").strip()
        assert text.startswith(prefix) and text.endswith(";"),name
        payload = json.loads(text[len(prefix):-1])
        variants = payload["variants"] if nested else payload
        assert set(variants) == keys,route
        if route == "observatory":
            assert payload["geometry"] and payload["baseline"] in keys
        for key,variant in variants.items():
            if route != "observatory":
                assert variant["cad"],(route,key)
            if route == "cabin":
                assert len(variant["frames"]) == 73,(route,key)
            else:
                assert variant["result"],(route,key)
            for view in ("plan","elevation","section"):
                path = WEBSITE/"plans"/folder/f"{key}-{view}.svg"
                assert ElementTree.parse(path).getroot().tag == "{http://www.w3.org/2000/svg}svg",path
            if route == "terrace":
                assert (WEBSITE/"plans"/folder/f"{key}-cracking.svg").is_file()
    assert (WEBSITE/"plans"/"extension"/"comparison.svg").is_file()
    assert (WEBSITE/"extension-details.js").is_file()

def test_viewer_id_selectors_have_unique_html_targets():
    class PageIds(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []

        def handle_starttag(self,tag,attributes):
            element_id = dict(attributes).get("id")
            if element_id is not None:
                self.ids.append(element_id)

    page = PageIds()
    page.feed((WEBSITE/"index.html").read_text(encoding="utf-8"))
    source = (WEBSITE/"viewer.js").read_text(encoding="utf-8")
    targets = set(re.findall(r'(?:querySelector\("#|getElementById\(")([\w-]+)',source))
    assert targets
    assert len(page.ids) == len(set(page.ids))
    assert targets <= set(page.ids)

def test_thermal_slider_covers_the_generated_hours():
    path = WEBSITE/"cabin-cases.js"
    if not path.is_file():
        pytest.skip("Generate the thermal case with python website/build_data.py cabin.")
    source = path.read_text(encoding="utf-8").strip()
    cases = json.loads(source.split(" = ",1)[1].removesuffix(";"))
    markup = (WEBSITE/"index.html").read_text(encoding="utf-8")
    (slider,) = re.findall(r'<input\b[^>]*\bid="cabin-hour"[^>]*>',markup)
    low,high,current = (int(re.search(rf'\b{attribute}="(\d+)"',slider).group(1))
                        for attribute in ("min","max","value"))
    assert low <= current <= high
    for variant in cases.values():
        frames = variant["frames"]
        assert [frame["hour"] for frame in frames] == list(range(low,high+1))
        assert variant["peak"] == max(frames,key=lambda frame:frame["air"])
