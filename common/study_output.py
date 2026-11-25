import json

import cadquery as cq
import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkUnstructuredGrid
from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridWriter

def write_step(path, parts, solids=()):
    assembly = cq.Assembly(name="Study")
    for name, shape in solids:
        assembly.add(shape, name=name)
    for index, part in enumerate(parts):
        points = [cq.Vector(*point) for point in np.asarray(part["points"]).reshape(-1, 3)*1000]
        faces, edges = [], []
        for ids in part["faces"]:
            vertices = [points[i] for i in ids]
            if len(vertices) == 2:
                edges.append(cq.Edge.makeLine(*vertices))
            else:
                wire = cq.Wire.makePolygon(vertices, close=True)
                faces.append(cq.Face.makeFromWires(wire))
        if faces:
            shell = cq.Shell.makeShell(faces)
            edges.append(cq.Solid.makeSolid(shell) if shell.Closed() else shell)
        if edges:
            assembly.add(cq.Compound.makeCompound(edges), name=f"{part['material']}_{index}")
    assembly.export(str(path))

def write_mesh(path, points, cells, gmsh_type):
    with path.open("w", encoding="utf-8") as file:
        file.write(f"$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n{len(points)}\n")
        for index, point in enumerate(points, 1):
            file.write(f"{index} " + " ".join(str(value) for value in point) + "\n")
        file.write(f"$EndNodes\n$Elements\n{len(cells)}\n")
        for index, cell in enumerate(cells, 1):
            file.write(f"{index} {gmsh_type} 0 " + " ".join(str(node+1) for node in cell) + "\n")
        file.write("$EndElements\n")

def write_displacements(path, points, cells, vtk_type, displacement, cell_fields=None):
    vtk_points = vtkPoints()
    vtk_points.SetData(numpy_to_vtk(np.asarray(points, dtype=float), deep=True))
    vtk_cells = vtkCellArray()
    vtk_cells.SetData(numpy_to_vtkIdTypeArray(np.arange(len(cells)+1, dtype=np.int64)*cells.shape[1], deep=True),
                      numpy_to_vtkIdTypeArray(np.asarray(cells, dtype=np.int64).ravel(), deep=True))
    grid = vtkUnstructuredGrid()
    grid.SetPoints(vtk_points)
    grid.SetCells(vtk_type, vtk_cells)
    values = numpy_to_vtk(np.ascontiguousarray(displacement, dtype=float), deep=True)
    values.SetName("displacement")
    grid.GetPointData().SetVectors(values)
    for name, field in (cell_fields or {}).items():
        values = numpy_to_vtk(np.ascontiguousarray(field, dtype=float), deep=True)
        values.SetName(name)
        grid.GetCellData().AddArray(values)
    writer = vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    if writer.Write() != 1:
        raise OSError(f"Could not write {path}")

def write_result(path, values):
    path.write_text(json.dumps(values, separators=(",", ":"), allow_nan=False), encoding="utf-8")
