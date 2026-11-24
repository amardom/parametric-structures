import os
from pathlib import Path
from shutil import which
import sys
from xml.etree import ElementTree as ET

def elmer_runtime():
    env = os.environ.copy()
    elmer_grid = which("ElmerGrid")
    elmer_solver = which("ElmerSolver")
    if not (elmer_grid and elmer_solver):
        prefix = Path(sys.prefix) / "elmer" / "usr"
        elmer_grid = prefix / "bin" / "ElmerGrid"
        elmer_solver = prefix / "bin" / "ElmerSolver"
        if not (elmer_grid.is_file() and elmer_solver.is_file()):
            raise RuntimeError("ElmerGrid and ElmerSolver must be installed.")
        elmer_home = prefix / "share" / "elmersolver"
        env["ELMER_HOME"] = str(prefix)
        env["ELMER_LIB"] = str(elmer_home / "lib")
        library_paths = [str(prefix / "lib" / "x86_64-linux-gnu"), str(elmer_home / "lib")]
        if env.get("LD_LIBRARY_PATH"):
            library_paths.append(env["LD_LIBRARY_PATH"])
        env["LD_LIBRARY_PATH"] = os.pathsep.join(library_paths)
    env.setdefault("OMP_NUM_THREADS", "1")
    return elmer_grid, elmer_solver, env

def add_displacement_vector(result: Path) -> None:
    tree = ET.parse(result)
    data = tree.find("./UnstructuredGrid/Piece/PointData")
    components = [data.find(f"DataArray[@Name='deflection {i}']").text.split() for i in (1, 2, 3)]
    displacement = ET.SubElement(data, "DataArray", type="Float64", Name="displacement",
                                 NumberOfComponents="3", format="ascii")
    displacement.text = "\n" + "\n".join(" ".join(row) for row in zip(*components, strict=True)) + "\n"
    data.set("Vectors", "displacement")
    tree.write(result, encoding="utf-8", xml_declaration=True)
