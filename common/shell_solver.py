from hashlib import sha256
from math import isfinite
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from .elmer import elmer_runtime

SOURCE = ("https://raw.githubusercontent.com/ElmerCSC/elmerfem/a23fae0fe/"
          "fem/src/modules/FacetShellSolve.F90")
SOURCE_HASH = "b14981583a8038d97c09534ae631a7822bc52eba0690caa5e7728f3ab4952ab4"
CIRCULAR_TUBE = Path(__file__).with_name("circular_tube.f90")
SQUARE_COLUMN = Path(__file__).with_name("square_column.f90")

def write_elmer_shell_beam_mesh(gmsh_path: Path, mesh: Path) -> None:
    from collections import Counter

    lines = gmsh_path.read_text().splitlines()
    node_start = lines.index("$Nodes") + 2
    raw_nodes = lines[node_start:lines.index("$EndNodes")]
    nodes = [f"{tag} -1 {x} {y} {z}" for tag, x, y, z in map(str.split, raw_nodes)]
    start = lines.index("$Elements") + 2
    bulk, supports, element_by_node = [], [], {}
    counts = Counter()
    for line in lines[start:lines.index("$EndElements")]:
        values = list(map(int, line.split()))
        _, kind, tag_count, group = values[:4]
        connectivity = values[3 + tag_count:]
        if kind == 15 and group == 3:
            supports.append(connectivity[0])
            continue
        element = len(bulk) + 1
        if kind == 1 and group == 2:
            elmer_code = 202
        elif kind == 3 and group in (1, 3, 4, 5):
            elmer_code = 404
        else:
            raise ValueError(f"Unexpected element type or body in the shell and beam mesh: {kind}/{group}")
        for node in connectivity:
            element_by_node.setdefault(node, element)
        counts[elmer_code] += 1
        bulk.append(" ".join(map(str, [element, group, elmer_code, *connectivity])))
    if not supports or not counts[202] or not counts[404]:
        raise ValueError("The model needs shell quads, beam lines and fixed support points.")
    boundary = [f"{i} 3 {element_by_node[node]} 0 101 {node}"
                for i, node in enumerate(supports, start=1)]
    counts[101] = len(boundary)
    mesh.mkdir()
    header = [f"{len(nodes)} {len(bulk)} {len(boundary)}", str(len(counts))]
    header.extend(f"{code} {count}" for code, count in sorted(counts.items()))
    for name, rows in (("header", header), ("nodes", nodes), ("elements", bulk), ("boundary", boundary)):
        (mesh / f"mesh.{name}").write_text("\n".join(rows) + "\n", encoding="ascii")

def compile_beam_solver(work: Path, solver: Path, env: dict, beam_source: Path) -> None:
    with urlopen(SOURCE, timeout=30) as response:
        source = response.read()
    if sha256(source).hexdigest() != SOURCE_HASH:
        raise RuntimeError("Unexpected Elmer shell source checksum.")
    text = source.decode()
    extension = beam_source.read_text()
    marker = "   SUBROUTINE BulkAssembly"
    if text.count(marker) != 1:
        raise RuntimeError("Could not find the facet assembly routine.")
    text = text.replace(marker, extension + "\n" + marker)
    marker = "       IF( CurrentElement % TYPE % ElementCode /= 303"
    if text.count(marker) != 1:
        raise RuntimeError("Could not find the facet assembly loop.")
    text = text.replace(marker, """       IF (CurrentElement % TYPE % ElementCode == 202) THEN
         CALL AssembleBeam(CurrentElement)
         CYCLE
       END IF
""" + marker)
    (work / "ShellWithBeams.F90").write_text(text)
    compiler = solver.with_name("elmerf90")
    library_dir = compiler.parent.parent / "lib" / "elmersolver"
    subprocess.run([compiler, f"-L{library_dir}", "-o", "ShellWithBeams.so", "ShellWithBeams.F90"],
                   cwd=work, env=env, check=True)

def solve_shell_structure(mesh_path: Path, result_path: Path, settings: dict,
                          roof_thickness: float, support_size: float, roof_pressure_pa: float,
                          *, body_materials=None, native_mesh=None, beam_source: Path | None = None,
                          calculate_loads: bool = False, body_force_y=None, beam_widths=None, point_loads=None) -> None:
    young = settings["young_modulus_pa"]
    poisson = settings["poisson_ratio"]
    density = settings["density_kg_m3"]
    gravity = settings["gravity_m_s2"]
    if not all(isfinite(v) and v > 0 for v in (young, density, gravity)):
        raise ValueError("Young's modulus, density and gravity must be finite and positive.")
    if not -1 < poisson < 0.5 or not isfinite(roof_pressure_pa) or roof_pressure_pa < 0:
        raise ValueError("Invalid Poisson ratio or roof pressure.")

    custom_beams = beam_source is not None
    library = "./ShellWithBeams" if custom_beams else "FacetShellSolve"
    mumps_options = ("  Linear System Symmetric = Logical True\n"
                     "  Linear System Positive Definite = Logical True") if custom_beams else ""
    bodies = []
    materials = body_materials or [
        (roof_thickness, young, poisson, density, roof_pressure_pa, 0),
        (support_size, young, poisson, density, 0.0, 0),
    ]
    for index, (thickness, young, poisson, density, pressure, tube_wall) in enumerate(materials, start=1):
        tube_parameter = f"  Beam Wall Thickness = Real {tube_wall}" if tube_wall else ""
        width = (beam_widths or {}).get(index)
        section_width = f"  Beam Section Width = Real {width}" if width is not None else ""
        force_y = (body_force_y or {}).get(index, 0)
        concentrated = ""
        if index == 1 and point_loads:
            rows = [f"  Point Load({len(point_loads)},9) = Real"]
            rows.extend(f"    {x:.12g} {y:.12g} {z:.12g} 0 0 {force:.12g} 0 0 0"
                        for x,y,z,force in point_loads)
            concentrated = "\n".join(rows)
        bodies.append(f'''Body {index}
  Target Bodies(1) = {index}
  Equation = 1
  Material = {index}
  Body Force = {index}
End
Material {index}
  Density = Real {density}
  Youngs Modulus = Real {young}
  Poisson Ratio = Real {poisson}
  Thickness = Real {thickness}
{tube_parameter}
{section_width}
End
Body Force {index}
  Body Force 2 = Real {force_y}
  Body Force 3 = Real {-density * gravity - pressure / thickness}
{concentrated}
End
''')

    sif = f'''Header
  CHECK KEYWORDS Warn
  Mesh DB "." "mesh"
End
Simulation
  Coordinate System = Cartesian 3D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
End
{"".join(bodies)}
Boundary Condition 1
  Target Boundaries(1) = 3
  Deflection 1 = Real 0
  Deflection 2 = Real 0
  Deflection 3 = Real 0
  Deflection 4 = Real 0
  Deflection 5 = Real 0
  Deflection 6 = Real 0
End
Equation 1
  Active Solvers(2) = 1 2
End
Solver 1
  Equation = "Facet shell"
  Procedure = "{library}" "ShellSolver"
  Large Deflection = Logical False
  Nonlinear System Max Iterations = 1
  Linear System Solver = Direct
  Linear System Direct Method = Mumps
{mumps_options}
  Calculate Loads = Logical {str(calculate_loads)}
  Displace Mesh = Logical False
End
Solver 2
  Exec Solver = After Simulation
  Equation = "Result output"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = File "displacements"
  Vtu Format = Logical True
  Binary Output = Logical False
End
'''
    grid, solver, env = elmer_runtime()
    with TemporaryDirectory(prefix=".elmer-", dir=result_path.parent) as directory:
        work = Path(directory).resolve()
        (work / "shell.sif").write_text(sif, encoding="utf-8")
        if native_mesh is not None:
            native_mesh(work / "mesh")
        elif custom_beams:
            write_elmer_shell_beam_mesh(mesh_path, work / "mesh")
        else:
            subprocess.run([grid, "14", "2", str(mesh_path.resolve()), "-out", "mesh"],
                           cwd=work, env=env, capture_output=True, text=True, check=True)
        if custom_beams:
            compile_beam_solver(work, Path(solver), env, beam_source)
        run = subprocess.run([solver, "shell.sif"], cwd=work, env=env,
                             capture_output=True, text=True)
        if run.returncode or (custom_beams and "Beam element assembled" not in run.stdout):
            raise RuntimeError(run.stdout[-6000:] + run.stderr[-3000:])
        files = list(work.rglob("displacements*.vtu"))
        if len(files) != 1 or files[0].stat().st_size == 0:
            raise RuntimeError("Expected a single non-empty Elmer shell VTU.")
        files[0].replace(result_path)
