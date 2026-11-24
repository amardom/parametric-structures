from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

import numpy as np
from scipy.optimize import minimize

from .model import housing_mesh, solve_housing, volumes

def floor_displacements(case, result, mesh=None):
    piece = ET.parse(result).getroot().find("./UnstructuredGrid/Piece")
    points = np.fromstring(piece.find("./Points/DataArray").text,sep=" ").reshape(-1,3)
    data = piece.find("PointData")
    moves = np.column_stack([np.fromstring(data.find(f"DataArray[@Name='deflection {i}']").text,sep=" ")
                             for i in (1,2,3)])
    n,h = (case["geometry"][key] for key in ("storeys","storey_height_m"))
    by_floor = [moves[np.isclose(points[:,2],i*h),1].mean() for i in range(n+1)]
    drift = np.diff(by_floor)/h
    if not np.isfinite(drift).all() or abs(by_floor[0]) > 1e-10:
        raise ValueError("Invalid diaphragm displacement or base restraint.")
    output = {"roof_mm":float(by_floor[-1]*1000),"drifts":drift.tolist()}
    if mesh is not None:
        nodes = np.asarray(mesh[0])
        if len(points) != len(nodes) or not np.allclose(points,nodes,atol=1e-5,rtol=0):
            index = {tuple(np.round(point,5)): i for i,point in enumerate(points)}
            moves = moves[[index[tuple(np.round(point,5))] for point in nodes]]
        output["displacement"] = (moves*1000).round(5).ravel().tolist()
    return output

def optimize_housing(case):
    g = case["geometry"]
    minimum,maximum,baseline = (g[key] for key in
        ("minimum_thickness_m","maximum_thickness_m","baseline_thickness_m"))
    limit = case["loads"]["drift_limit"]
    fixed,areas = volumes(case)
    areas = np.asarray(areas)
    design0 = np.full(6,baseline)
    mesh = housing_mesh(case)
    cache = {}
    trace = []
    feasible = []

    def response(design, *, capture=False):
        key = tuple(float(x) for x in np.round(design,8))
        if not capture and key in cache:
            return cache[key]
        with TemporaryDirectory(prefix="housing-design-") as directory:
            result = Path(directory)/"housing.vtu"
            solve_housing(case,key,mesh,result)
            metrics = floor_displacements(case,result,mesh if capture else None)
        cache[key] = {k:v for k,v in metrics.items() if k != "displacement"}
        return metrics

    def volume(design):
        return float(fixed + areas @ design)

    def utilization(design):
        return np.asarray(response(design)["drifts"])/limit

    def report(design):
        metrics = response(design)
        peak = max(map(abs,metrics["drifts"]))
        trace.append({"volume_m3":volume(design),"peak_drift":peak})
        if peak <= limit*.999:
            feasible.append(np.copy(design))
        print(f"  {volume(design):.2f} m³ · drift {1000*peak:.5f} ‰",flush=True)

    base = response(design0,capture=True)
    lower = np.full(6,minimum)
    floor = response(lower)
    if max(map(abs,floor["drifts"])) <= limit:
        candidate = lower
        report(design0)
        report(candidate)
        method = "Minimum-thickness bound"
    else:
        report(design0)
        if not feasible:
            upper = np.full(6,maximum)
            report(upper)
            if not feasible:
                raise ValueError("The specified drift limit is infeasible at maximum thickness.")
        with ThreadPoolExecutor(max_workers=3) as workers:
            def jacobian(design):
                reference = utilization(design)
                step = np.where(design + .001 <= maximum,.001,-.001)
                perturbed = [design + row for row in np.diag(step)]
                return np.column_stack([(value-reference)/delta
                                        for value,delta in zip(workers.map(utilization,perturbed),step,strict=True)])

            def margins(design):
                u = utilization(design)
                return np.concatenate((.998-u,.998+u))

            def margin_jacobian(design):
                jac = jacobian(design)
                return np.vstack((-jac,jac))

            result = minimize(lambda x: volume(x)/volume(design0),feasible[0],
                              jac=lambda x: areas/volume(design0),method="SLSQP",
                              bounds=[(minimum,maximum)]*6,
                              constraints={"type":"ineq","fun":margins,"jac":margin_jacobian},
                              callback=report,options={"ftol":2e-5,"maxiter":14})
        report(result.x)
        candidate = min(feasible,key=volume)
        method = ("Sequential quadratic programming" if result.success
                  else "Sequential quadratic programming · Best verified iterate")

    continuous = response(candidate)
    candidate = np.clip(np.ceil((candidate-1e-8)/.005)*.005,minimum,maximum)
    evaluations = len(cache)+1
    final = response(candidate,capture=True)
    if max(map(abs,final["drifts"])) > limit*1.00001:
        raise RuntimeError("The verified design exceeds the study drift limit.")
    if volume(candidate) > volume(design0):
        raise RuntimeError("The optimised design uses more concrete than the baseline.")
    return {
        "uniform": {**base,"thickness_m":design0.tolist(),"volume_m3":volume(design0)},
        "optimized": {**final,"thickness_m":candidate.tolist(),"volume_m3":volume(candidate)},
        "history": trace, "evaluations":evaluations, "method":method,
        "continuous_peak_drift":max(map(abs,continuous["drifts"])),
        "drift_limit":limit,"fixed_volume_m3":fixed,"wall_area_m2":areas.tolist(),
        "minimum_thickness_m":minimum,"maximum_thickness_m":maximum,
    }
