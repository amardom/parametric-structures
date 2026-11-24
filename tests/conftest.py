import json
from pathlib import Path

import pytest

from common.elmer import elmer_runtime

PROJECTS = Path(__file__).resolve().parents[1] / "projects"

@pytest.fixture
def load_case():
    def load(project):
        (config,) = (path for path in (PROJECTS / project).glob("*.json")
                     if not path.name.endswith("-results.json"))
        return json.loads(config.read_text(encoding="utf-8"))
    return load

@pytest.fixture
def read_msh():
    def read(path):
        rows = path.read_text().splitlines()
        nodes = {}
        for row in rows[rows.index("$Nodes")+2:rows.index("$EndNodes")]:
            tag, *coords = row.split()
            nodes[int(tag)] = tuple(map(float,coords))
        cells = []
        for row in rows[rows.index("$Elements")+2:rows.index("$EndElements")]:
            _,kind,count,*fields = map(int,row.split())
            cells.append((kind,fields[0],tuple(fields[count:])))
        return nodes,cells
    return read

@pytest.fixture
def elmer_installed():
    try:
        elmer_runtime()
    except RuntimeError as error:
        pytest.skip(str(error))
