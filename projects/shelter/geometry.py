from math import isfinite

def build_concrete_geometry(dimensions: dict) -> dict:
    width = dimensions["width_m"]
    depth = dimensions["depth_m"]
    height = dimensions["clear_height_m"]
    wall = dimensions["wall_thickness_m"]
    roof = dimensions["roof_thickness_m"]

    for name in ("width_m", "depth_m", "clear_height_m", "wall_thickness_m", "roof_thickness_m"):
        value = dimensions[name]
        if type(value) not in (int, float) or not isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a finite positive number.")
    if width <= 2 * wall or depth <= wall:
        raise ValueError("The walls must leave a clear interior.")

    rear_wall_y = depth - wall
    right_wall_x = width - wall
    geometry = {
        "walls": {
            "left": {"min": (0, 0, 0), "max": (wall, rear_wall_y, height)},
            "right": {"min": (right_wall_x, 0, 0), "max": (width, rear_wall_y, height)},
            "rear": {"min": (0, rear_wall_y, 0), "max": (width, depth, height)},
        },
        "roof": {"min": (0, 0, height), "max": (width, depth, height + roof)},
        "floor": {"min": (wall, 0, 0), "max": (right_wall_x, rear_wall_y, 0)},
        "front_opening": {"min": (wall, 0, 0), "max": (right_wall_x, 0, height)},
    }

    if "rear_window" in dimensions:
        window = dimensions["rear_window"]
        opening = window["width_m"]
        sill = window["sill_height_m"]
        offset = window.get("offset_m", 0.0)
        if not all(type(v) in (float, int) and isfinite(v) for v in (opening, sill, offset)):
            raise ValueError("Window dimensions must be finite numbers.")
        if not (0 < opening < width - 2 * wall and abs(offset) < (width-opening)/2-wall
                and 0 < sill < height and wall >= 0.012):
            raise ValueError("The window must fit between the side walls, above the floor.")
        geometry["rear_window"] = {
            "min": ((width - opening) / 2 + offset, rear_wall_y, sill),
            "max": ((width + opening) / 2 + offset, depth, height),
        }
    return geometry
