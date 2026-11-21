# Nnotes page templates

Full-page SVG templates that the Nnotes app offers under **Page Styles > Page Pattern > Online**.
The app downloads this catalog at runtime and paints the chosen SVG as a locked, full-page
background on the current page.

## How the app finds these files

Source: `com.nnote.ui.TemplateCatalog` in the Nnotes app.

| Order | URL | What it reads |
|-------|-----|---------------|
| 1 | `templates/templates_data.json` | The catalog below |
| 2 | `templates_data.json` (repo root) | Fallback, unused here |
| 3 | GitHub API `contents/templates` | Any `*.svg` sitting directly in `templates/` |

The app then downloads each entry's `url`, caches it, and stretches the image to the page size.

> Because order 3 lists any `.svg` directly inside `templates/`, files live in `templates/svg/`
> instead. A subfolder is ignored by that listing, so nothing is ever listed twice.

## Layout

```
templates/
  templates_data.json   generated registry the app reads
  svg/                  the page templates (one SVG per template)
  meta/                 optional per-template metadata sidecars
  README.md
```

## Adding a template

1. Drop the SVG in `templates/svg/`, for example `templates/svg/weekly-review.svg`.
2. Optionally add `templates/meta/weekly-review.json`:

   ```json
   {
     "title": "Weekly Review",
     "category": "Planners",
     "tags": ["weekly", "review", "goals"],
     "description": "Weekly page with goal slots and a reflection block."
   }
   ```

3. Rebuild the registry:

   ```bash
   python generate_templates_json.py
   ```

Without a sidecar the generator derives `title` from the filename, sets `category` to `Basic`,
and builds `tags` from the title. It keeps values you hand edit in `templates_data.json` when a
sidecar is absent, so both routes work.

## Authoring rules

The renderer is AndroidSVG, and the previews use Coil's SVG decoder. Keep files plain:

- Top level `<svg>` needs `width`, `height` and `viewBox`. The app reads them to size the image;
  without them the template is dropped silently.
- Author at **1240 x 1754**, which is A4 portrait at the app's default 150 dpi. Use
  `width="1240" height="1754" viewBox="0 0 1240 1754"`.
- Transparent background. Leave the paper white and let the app show it through.
- Self contained only: no external images, no `<image href>`, no webfonts, no `<style>` sheets,
  no scripts. Use presentation attributes and `<path>` / `<rect>` / `<line>` / `<circle>`.
- `<text>` is allowed for labels and uses system fonts, but text to path is safer for exact
  placement. Avoid exotic CSS.
- Keep to a light gray line system so hand ink stays dominant, roughly `#5d5d5d` for structural
  rules, `#7c7c7c` for writing lines, and `#6d6d6d` for labels.

## Metadata fields

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | Set from the filename. Stable; the offline cache is keyed by it |
| `title` | yes | Shown under the preview card |
| `category` | yes | See below |
| `tags` | no | Free form keywords |
| `description` | no | Short sentence |
| `url` | yes | Raw URL to the SVG, generated for you |
| `previewUrl` | no | Defaults to `url` |
| `matchingPattern` | no | A ruling id, see below |

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
`daily-planner.svg` does. When it is omitted the page ruling is set to `none` on apply.

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
