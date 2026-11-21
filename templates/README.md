# Nnotes page templates

Full-page SVG templates that the Nnotes app offers under **Page Styles > Page Pattern > Online**.
A template has two files: the SVG you author (also used as the preview) and a compiled vector model
the app renders. The model lets color, opacity, spacing, blend and line weight work exactly as they
do on an offline ruling, and lets embedded stickers be selected and removed. See [SPEC.md](SPEC.md)
for the full model contract.

## How the app finds these files

Source: `com.nnote.ui.TemplateCatalog` in the Nnotes app.

| Order | URL | What it reads |
|-------|-----|---------------|
| 1 | `templates/templates_data.json` | The catalog below |
| 2 | `templates_data.json` (repo root) | Fallback, unused here |
| 3 | GitHub API `contents/templates` | Any `*.svg` sitting directly in `templates/` |

The app then downloads the entry's `modelUrl`, embeds it in the note, and paints it as a
style-driven vector layer. `url` / `previewUrl` still matter: they drive the card preview and the
fallback path for older app builds, which stretch the SVG into a locked background.

> Because order 3 lists any `.svg` directly inside `templates/`, files live in `templates/svg/`
> instead. A subfolder is ignored by that listing, so nothing is ever listed twice.

## Layout

```
templates/
  templates_data.json   generated registry the app reads
  svg/                  authoring sources / previews (one SVG per template)
  model/                compiled models the app renders
  meta/                 optional per-template metadata sidecars
  README.md
  SPEC.md               model contract
compile_templates.py      SVG + meta -> model JSON
generate_templates_json.py model + meta -> registry
```

## Adding a template

1. Drop the SVG in `templates/svg/`, for example `templates/svg/weekly-review.svg`.
2. Add `templates/meta/weekly-review.json`. Include the `layout` block when the template has
   spacing-driven rows (see [SPEC.md](SPEC.md)):

   ```json
   {
     "title": "Weekly Review",
     "category": "Planners",
     "tags": ["weekly", "review", "goals"],
     "description": "Weekly page with goal slots and a reflection block.",
     "layout": {
       "primary": "goals",
       "repeats": {
         "goals": {"group": "rule-goals", "anchor": 320, "base": 38, "limit": 700}
       }
     }
   }
   ```

3. Rebuild the model and the registry, in that order:

   ```bash
   python compile_templates.py
   python generate_templates_json.py
   ```

Without a sidecar the generator derives `title` from the filename, sets `category` to `Basic`,
and builds `tags` from the title. It keeps values you hand edit in `templates_data.json` when a
sidecar is absent, so both routes work. A template with no compiled model still works as a frozen
SVG; it just cannot be customized.

## Authoring rules

The renderer is AndroidSVG, and the previews use Coil's SVG decoder. Keep files plain:

- Top level `<svg>` needs `width`, `height` and `viewBox`. The app reads them to size the image;
  without them the template is dropped silently.
- Author at **1240 x 1754**, which is A4 portrait at the app's default 150 dpi. Use
  `width="1240" height="1754" viewBox="0 0 1240 1754"`.
- Transparent background. Leave the paper white and let the app show it through.
- Self contained only: no external images, no `<image href>`, no webfonts, no `<style>` sheets,
  no scripts. Use presentation attributes and `<path>` / `<rect>` / `<line>` / `<circle>`.
- `<text>` is allowed and the compiler outlines it to vector paths when `fonttools` is installed,
  so labels survive PDF export. Keep to sans-serif weights 400 and 700.
- Wrap artwork in the role groups from [SPEC.md](SPEC.md): `structural`, `rule-<name>`, `guide`,
  `label`, `decor`, `sticker-<id>`. Group id drives both the paint role and repeat detection.
- Keep one opacity per group. Consecutive items with the same role and alpha become one paint
  layer; alternating opacities inside a group create many compositing passes.
- Keep to a light gray line system so hand ink stays dominant, roughly `#5d5d5d` for structural
  rules, `#7c7c7c` for writing lines, and `#6d6d6d` for labels. These colors are only for the SVG
  preview; the app recolors painted layers with the chosen pattern color.

## Metadata fields

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | Set from the filename. Stable; the offline cache is keyed by it |
| `title` | yes | Shown under the preview card |
| `category` | yes | See below |
| `tags` | no | Free form keywords |
| `description` | no | Short sentence |
| `url` | yes | Raw URL to the SVG preview / legacy fallback, generated for you |
| `previewUrl` | no | Defaults to `url` |
| `matchingPattern` | no | A ruling id, see below |
| `modelUrl` | no | Generated when `templates/model/<id>.json` exists |
| `modelVersion` | no | Generated from the model version |
| `capabilities` | no | Generated: recolor, spacing, blend, stickers |
| `spacingBase` / `spacingPrimary` | no | Generated from the model's primary repeat group |

### Categories

The app's category chips are fixed to `All`, `Basic`, `Academic` and `Planners`. A template only
appears under a chip when its `category` matches one of those names exactly. Any other value is
still reachable under `All`.

### matchingPattern

Optional. When set, applying the template also sets the page ruling to that pattern:

`lines`, `dots`, `grid`, `cornell`, `hex`, `music`, `isometric`, `planner`, `engineering`,
`daily_planner_1`, `daily_planner_2`, `weekly_planner_1`, `weekly_planner_2`, `monthly_planner_1`,
`monthly_planner_2`, `sprint_planner`, `kanban`.

Leave it out for a self contained template that already draws its own rulings, as
`daily-planner.svg` does. A compiled model always wins over `matchingPattern`; applying it sets the
page ruling to `none` so the template's own vector ruling is the only one painted. `matchingPattern`
is used only by the legacy locked-SVG fallback.

## Aspect ratio

The template is stretched to fit whatever page it is applied to. One SVG therefore only looks
right on matching proportions. The A series shares A4's ratio (210:297), so a 1240 x 1754 SVG
suits A4 and A5. Letter (215.9:279.4) and the slide sizes differ and will distort a template
authored for A4, and landscape pages will too. Either accept mild stretch or ship a variant per
ratio.

## Do not

- Do not put an `.svg` directly in `templates/` while also registering it in
  `templates_data.json`. The app appends the JSON catalog and the auto discovered files without
  de-duplicating, so the card would show twice.
- Do not put a JSON `null` in `assetPath`. The app reads that key as a string and would cache the
  literal text `null`. Omit unused keys instead, which the generator already does.

## Automation

`.github/workflows/generate.yml` still regenerates only the sticker and frame JSONs. To rebuild
this registry on push, add `templates/svg/**` to its `paths` list, run
`python generate_templates_json.py`, and add `templates/templates_data.json` to its `git add`.
