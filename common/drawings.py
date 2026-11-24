from html import escape

def line(x1, y1, x2, y2, style):
    return f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" class="{style}"/>'

def label(x, y, value, style="note", anchor="start", rotation=0):
    return (
        f'<text x="{x:g}" y="{y:g}" class="{style}" text-anchor="{anchor}" '
        f'transform="rotate({rotation} {x:g} {y:g})">{escape(value)}</text>'
    )

def dimension(x1, y1, x2, y2, offset, metres, *, millimetres=False):
    value = f"{metres * 1000:g} mm" if millimetres else f"{metres:.2f}"
    direction = 1 if offset > 0 else -1
    gap = 4 * direction
    overshoot = 5 * direction
    label_length = len(value) * 8
    clearance = 8
    if y1 == y2:
        y = y1 + offset
        elements = [
            line(x1, y1 + gap, x1, y + overshoot, "extension"),
            line(x2, y2 + gap, x2, y + overshoot, "extension"),
            line(x1, y, x2, y, "dimension"),
        ]
        if abs(x2 - x1) >= label_length + 2 * clearance:
            return elements + [label((x1 + x2) / 2, y - clearance, value, "measure", "middle")]
        end = max(x1, x2)
        return elements + [
            line(end, y, end + clearance + label_length, y, "dimension-tail"),
            label(end + clearance, y - clearance, value, "measure"),
        ]
    if x1 != x2:
        raise ValueError("Dimensions must be horizontal or vertical.")

    x = x1 + offset
    elements = [
        line(x1 + gap, y1, x + overshoot, y1, "extension"),
        line(x2 + gap, y2, x + overshoot, y2, "extension"),
        line(x, y1, x, y2, "dimension"),
    ]
    if abs(y2 - y1) >= label_length + 2 * clearance:
        return elements + [label(x - clearance, (y1 + y2) / 2, value, "measure", "middle", -90)]
    end = max(y1, y2)
    return elements + [
        line(x, end, x, end + clearance + label_length, "dimension-tail"),
        label(x - clearance, end + clearance, value, "measure", "end", -90),
    ]

def write_sheet(path, title, reference, elements, project="Concrete shelter"):
    body = "\n".join(elements)
    path.write_text(f"""<svg xml:lang="en" xmlns="http://www.w3.org/2000/svg" width="960" height="700" viewBox="0 0 960 700" role="img">
<title>{escape(title)} — {escape(project)}</title>
<defs>
  <marker id="tick" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="0">
    <path d="M2 8 L8 2" stroke="#356d72" stroke-width="1.2"/>
  </marker>
</defs>
<style>
  text {{ font-family: Arial, sans-serif; fill: #202e33; }}
  .title {{ font-size: 34px; font-weight: 700; }}
  .meta {{ font-size: 12px; letter-spacing: 2px; fill: #476269; }}
  .title-block-label {{ font-size: 9px; letter-spacing: 1.4px; fill: #476269; }}
  .title-block-value {{ font-size: 13px; font-weight: 700; }}
  .note {{ font-size: 14px; fill: #476269; }}
  .measure {{ font-size: 13px; font-weight: 700; fill: #275d63; paint-order: stroke; stroke: #f9f8f4; stroke-width: 4; }}
  .roof {{ fill: #e6eeeb; stroke: #567276; stroke-width: 1.2; }}
  .cut {{ stroke: #00847b; stroke-dasharray: 9 5; }}
  .glass {{ fill: #c8edf4; stroke: #438799; stroke-width: 1.4; }}
  .glass-line {{ stroke: #6bc7d9; stroke-width: 3; }}
  .wall {{ fill: #203d46; }}
  .ground {{ stroke: #6b7e82; stroke-width: 1.5; }}
  .extension {{ stroke: #91a7aa; stroke-width: 0.8; }}
  .dimension, .dimension-tail {{ stroke: #356d72; stroke-width: 0.9; }}
  .dimension {{ marker-start: url(#tick); marker-end: url(#tick); }}
</style>
<rect width="960" height="700" fill="#f9f8f4"/>
<path d="M64 125 H896" stroke="#c8d4d1"/>
{label(64, 53, project.upper(), "meta")}
{label(64, 103, title, "title")}
{body}
<rect x="64" y="655" width="832" height="37" fill="none" stroke="#c8d4d1"/>
<path d="M414 655 V692 M550 655 V692 M748 655 V692" stroke="#c8d4d1"/>
{label(76, 669, "PROJECT", "title-block-label")}
{label(76, 685, project, "title-block-value")}
{label(426, 669, "DRAWING NO.", "title-block-label")}
{label(426, 685, reference, "title-block-value")}
{label(562, 669, "STATUS", "title-block-label")}
{label(562, 685, "Concept design", "title-block-value")}
{label(760, 669, "DIMENSIONS", "title-block-label")}
{label(760, 685, "m unless noted", "title-block-value")}
</svg>
""", encoding="utf-8")
