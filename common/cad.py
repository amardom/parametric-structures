from pathlib import Path

import cadquery as cq

def export_step(model: cq.Assembly, path: Path) -> None:
    model.export(str(path))
