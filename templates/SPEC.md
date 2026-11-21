# Nnotes template model, version 1

The compiled model is the file the app actually renders. The SVG is the authoring source and the
catalog preview; the model is what gives an online template the same customization as an offline
ruling. A note embeds the model on apply, so it never needs the network again.

## Pipeline

```
templates/svg/<id>.svg  ──compile_templates.py──▶  templates/model/<id>.json
templates/meta/<id>.json ─────────┘                        │
                                                          └──▶ generate_templates_json.py
                                                                  ▸ templates/templates_data.json
```

Run both scripts, in that order, from the repository root:

```bash
python compile_templates.py
python generate_templates_json.py
python compile_templates.py --check        # CI: models are current
python generate_templates_json.py --check  # CI: registry is current
```

`compile_templates.py` needs Python 3 and `fonttools` (`pip install fonttools`). Without a font it
leaves labels as text ops; those draw on screen but cannot be vector-exported. With a font it
outlines every glyph into vector contours.

## Source SVG conventions

Author at **1240 x 1754** (A4 at 150 dpi), transparent background, no external references. Colors
in the SVG are ignored by the compiler except `none` vs set — the app recolors all painted layers
with the page's pattern color. Stickers keep their authored colors.

Groups are recognized by their `id` prefix:

| Group id | Role in the model | Meaning |
|----------|-------------------|---------|
| `structural` | `structural` | Section rules, the spine of the page |
| `rule-<name>` | `rule` | Ruling lines; may be a repeat group |
| `guide` | `guide` | Hairlines that organize the eye |
| `label`, `label-<name>` | `label` | Text labels (outlined to paths) |
| `decor` | `decor` | Decorative vector art |
| `sticker-<id>` | none | Extracted as an editable page item |

An element's per-role alpha comes from its `stroke-opacity` / `fill-opacity` multiplied by any
`opacity`. Keep one alpha per group where possible: consecutive items with the same role and alpha
become one paint layer, and each layer costs one compositing pass.

Transform handling: `translate`, `scale`, `matrix` and `rotate` on groups and elements are applied.
Paths may use `M/L/H/V/C/S/Q/T/A/Z`; curves and arcs are flattened to polylines.

## Repeat groups (spacing)

Meta sidecar example:

```json
{
  "layout": {
    "primary": "schedule",
    "repeats": {
      "priorities": {"group": "rule-priorities", "anchor": 328, "base": 38, "limit": 452},
      "schedule":   {"group": "rule-schedule",   "anchor": 576, "base": 78, "limit": 1420},
      "todo":       {"group": "rule-todo",       "anchor": 576, "base": 34, "limit": 1100}
    }
  }
}
```

- `anchor` is the y of row 0; `base` is the authored row pitch; `limit` is the y past which rows
  are culled (usually the next section's top edge).
- The compiler snaps every item in a repeat group to its nearest row: `row = round((center - anchor) / base)`.
  The stored y is then **relative to that row's baseline**, so a checkbox stays 18 px above its line.
  An item more than `0.62 * base` away from a row is left absolute with a warning.
- The app computes `pitch = base * (spacing / primaryBase)`. All groups scale together, keeping the
  template's internal proportions. Increasing spacing gives fewer rows per section (rows past
  `limit` are not painted); decreasing it compresses them.
- `primary` names the group whose `base` seeds the spacing slider when the template is applied.
  Choose the section whose rhythm best represents the page — for the daily planner that is the
  schedule at 78 px.

## Model shape

```jsonc
{
  "format": "nnotes-template",
  "version": 1,
  "id": "daily-planner",
  "canvas": { "w": 1240, "h": 1754 },
  "spacing": { "primary": "schedule", "base": 78 },
  "repeat": {
    "schedule": { "anchor": 576, "base": 78, "limit": 1420, "rows": 11 }
  },
  "layers": [
    { "role": "structural", "alpha": 0.8,
      "items": [
        { "op": "poly", "pts": [60,180, 880,180], "w": 1.3 }
      ] },
    { "role": "rule", "alpha": 0.5,
      "items": [
        { "op": "rect", "rect": [748,558,20,20], "rx": 4, "w": 1.1, "rep": "todo", "row": 0 }
      ] },
    { "role": "label", "alpha": 0.9,
      "items": [
        { "op": "fill", "evenOdd": true,
          "contours": [[60,104, 62,101, /* … */]] }
      ] }
  ],
  "stickers": [
    { "id": "paperclip", "rect": [1135,27,18,62], "svg": "<svg …>…</svg>" }
  ]
}
```

### Ops

| `op` | Fields | Drawn as |
|------|--------|----------|
| `poly` | `pts: [x,y,…]`, `closed`, `w` | polyline or polygon stroke |
| `line` | `a`, `b`, `w` | straight stroke |
| `rect` | `rect: [x,y,w,h]`, `rx`, `w` | rounded/sharp rectangle stroke |
| `circle` | `c`, `rx`, `ry`, `w`, optionally `fill: true` | ellipse stroke or fill |
| `fill` | `contours: [[x,y,…], …]`, `evenOdd` | one multi-contour fill (glyph outlines, shapes with holes) |

Any op may carry `rep` (repeat name) and `row` (integer). All y coordinates of such an op are
relative to its row baseline; x coordinates are absolute.

### Stickers

A `sticker-<id>` group becomes a small standalone SVG whose `viewBox` is the group's bounding box,
plus that box in `rect` (template canvas coordinates). On apply the app scales the rect into page
space and inserts the SVG as an ordinary unlocked image item: selectable, movable, resizable and
deletable. Keep sticker artwork small and closed; strokes are flattened into polylines.

## Catalog entry

`generate_templates_json.py` adds these when a valid model exists:

```jsonc
{
  "modelUrl": "…/templates/model/<id>.json",
  "modelVersion": 1,
  "capabilities": ["recolor", "spacing", "blend", "stickers"],
  "spacingBase": 78,
  "spacingPrimary": "schedule"
}
```

If the model is missing or invalid the keys are omitted and the app falls back to downloading the
plain SVG, which still works but is not customizable.

## Versioning

The app accepts only `format: "nnotes-template"` and `version: 1`. A newer model is rejected and
the template falls back to the locked-SVG path — never a crash. When the contract changes, bump
`MODEL_VERSION`, keep the old compiler output available, and add a new reader branch in the app.

## Validation

The registry generator rejects a model when:

- `format` or `version` is wrong, or the canvas has no size;
- any repeat has no `anchor` or a non-positive `base`;
- any sticker lacks a 4-number `rect` or SVG source, or has an empty box.

The compiler reports off-grid items on stderr and skips them from repeat scaling, leaving them
absolute. Run both `--check` flags in CI so a hand-edited SVG can never silently diverge from its
model.
