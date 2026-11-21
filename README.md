
## Sourced CC0 stickers

`freesvg_stickers_data.json` is a separate catalog of CC0 stickers from FreeSVG.org. Those SVGs
live in `stickers/` with a `freesvg_` prefix and are excluded from the original `stickers_data.json`
so the website keeps both sets separate. Every source, author and license is recorded in
[ATTRIBUTION.md](../ATTRIBUTION.md) and in the catalog entry.

Rebuild the catalogs with:

```bash
python generate_json.py
```
