from pathlib import Path

from common.drawings import dimension, label, line, write_sheet

def rectangle(x, y, width, height, style="roof"):
    return f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" class="{style}"/>'

def draw_concrete_plans(geometry: dict, output_stem: Path) -> None:
    width, depth, total_height = geometry["roof"]["max"]
    left_x, _, _ = geometry["front_opening"]["min"]
    right_x, _, clear_height = geometry["front_opening"]["max"]

    window = geometry.get("rear_window")
    scale = min(560 / width, 280 / depth)
    x0, y0 = 170, 475
    x1, y1 = x0 + width * scale, y0 - depth * scale
    plan = [rectangle(x0, y1, width * scale, depth * scale)]
    for wall in geometry["walls"].values():
        xa, ya, _ = wall["min"]
        xb, yb, _ = wall["max"]
        plan.append(rectangle(x0 + xa * scale, y0 - yb * scale,
                              (xb - xa) * scale, (yb - ya) * scale, "wall"))
    if window is not None:
        xa, ya, _ = window["min"]
        xb, yb, _ = window["max"]
        center_y = y0 - (ya + yb) * scale / 2
        plan.append(line(x0 + xa * scale, center_y, x0 + xb * scale, center_y, "glass-line"))
        plan.append(label(x0 + (xa + xb) * scale / 2, y1 + 31, "High-level window", "note", "middle"))
    cut_y = y0 - depth * scale / 2
    plan.extend([
        line(x0 - 30, cut_y, x1 + 30, cut_y, "cut"),
        label(x0 - 42, cut_y + 4, "A", "note", "end"),
        label(x1 + 42, cut_y + 4, "A"),
        label((x0 + x1) / 2, y0 + 70, "OPEN FRONT", "meta", "middle"),
    ])
    plan.extend(dimension(x0, y1, x1, y1, -48, width))
    plan.extend(dimension(x0, y1, x0, y0, -75, depth))
    plan.extend(dimension(x0 + left_x * scale, y0, x0 + right_x * scale, y0,
                          34, right_x - left_x))
    write_sheet(
        output_stem.with_name(output_stem.name + "-plan.svg"), "Plan",
        "SH-01", plan,
    )

    scale = min(560 / width, 235 / total_height)
    x0, floor_y = 168, 492
    x1 = x0 + width * scale
    top_y = floor_y - total_height * scale
    soffit_y = floor_y - clear_height * scale
    left = x0 + left_x * scale
    right = x0 + right_x * scale
    cap = rectangle(x0, top_y, width * scale, soffit_y - top_y)
    ground = line(x0 - 22, floor_y, x1 + 22, floor_y, "ground")
    left_wall = rectangle(x0, soffit_y, left - x0, floor_y - soffit_y)
    right_wall = rectangle(right, soffit_y, x1 - right, floor_y - soffit_y)
    elevation = [
        f'<rect x="{left:g}" y="{soffit_y:g}" width="{right-left:g}" '
        f'height="{floor_y-soffit_y:g}" fill="#e4e6e2"/>',
        cap, left_wall, right_wall, ground,
    ]
    if window is not None:
        xa, _, sill = window["min"]
        xb = window["max"][0]
        glass_left = x0 + xa * scale
        glass_right = x0 + xb * scale
        sill_y = floor_y - sill * scale
        elevation.append(rectangle(glass_left, soffit_y, glass_right - glass_left,
                                   sill_y - soffit_y, "glass"))
        elevation.extend(dimension(glass_left, soffit_y, glass_right, soffit_y, -28, xb - xa))
        if abs((xa + xb)/2 - width/2) > 1e-6:
            if xa < width - xb:
                elevation.extend(dimension(x0, soffit_y, glass_left, soffit_y, -28, xa))
            else:
                elevation.extend(dimension(glass_right, soffit_y, x1, soffit_y, -28, width-xb))
        elevation.append(label((glass_left + glass_right) / 2, sill_y + 22,
                               "Rear window", "note", "middle"))
    elevation.extend(dimension(left, floor_y, right, floor_y, 42, right_x - left_x))
    elevation.extend(dimension(x0, top_y, x0, floor_y, -57, total_height))
    write_sheet(
        output_stem.with_name(output_stem.name + "-elevation.svg"), "Front elevation",
        "SH-02", elevation,
    )

    section = [cap, left_wall, right_wall, ground, label(x0, floor_y + 70, "FINISHED FLOOR LEVEL ±0.00", "meta")]
    if window is not None:
        xa, _, sill = window["min"]
        xb = window["max"][0]
        glass_left = x0 + xa * scale
        glass_right = x0 + xb * scale
        sill_y = floor_y - sill * scale
        section.append(rectangle(glass_left, soffit_y, glass_right - glass_left,
                                  sill_y - soffit_y, "glass"))
        section.extend(dimension(glass_right, soffit_y, glass_right, sill_y, 34, clear_height - sill))
    section.extend(dimension(x0, soffit_y, x0, floor_y, -57, clear_height))
    section.extend(dimension(x1, top_y, x1, soffit_y, 60, total_height - clear_height))
    section.extend(dimension(x0, floor_y, x1, floor_y, 38, width))
    write_sheet(
        output_stem.with_name(output_stem.name + "-section.svg"), "Section A–A",
        "SH-03", section,
    )
