# N-Notes Assets design direction

Owner direction: "minimalist", "unique and viewer friendly", "stickers should feel embedded, not bulky photo containers". Chosen direction: Swiss grid catalog.

## Identity

A visual asset catalog for people building note apps. The stickers are the content. The interface is a neutral grid around them.

## Reference

UI/UX Pro Max skill match: `minimalism-and-swiss-style`, verified from local `styles.csv`. Keywords: clean, spacious, functional, high contrast, geometric, grid-based, sans-serif, essential. Fonts: sans-serif only, no network font request.

## Dials

ENERGY 1 / RHYTHM 1 / MOTION 1. Uniqueness comes from the strict grid and the left rail, not from decoration or motion.

## Palette

- Paper `#96938B`: mid-tone neutral so white sticker borders and dark artwork both read. Checked: white borders 3.07:1, dark ink 5.98:1.
- Ink `#14141A`: text and hairlines.
- Secondary `#26262B`: inactive controls, 4.91:1 on paper.
- Accent `#0A2266`: active rail item and focus ring only, 4.77:1 on paper.

No gradient, no glow, no glass, no shadow.

## Typography

Sans-serif system stack only (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`). Display title 700 weight with tight tracking. All UI text same family. No serif, no monospace, no network font.

## Shape and elevation

Border radius 0 everywhere. Hairline rules at `#45433E` (3.22:1 on paper) where structure is needed. Stickers sit directly on the page with no panel, border, or backing box.

## Layout

Desktop: top masthead with title and search, then a two-column body. Left rail holds collection tabs and category buttons as vertical text items with a 3px accent marker for the active item. Right side is a strict responsive grid of sticker previews with name and Save link below. Mobile: rail becomes a horizontal scrolling bar above the grid, grid reflows to two columns then one as needed.

## States

Loading, empty, and error states are text with a real action. Counts come from the fetched JSON, never invented.

## Theme

One fixed mid-tone theme. A dark theme would hide dark artwork; a light theme hides white sticker lines. No toggle.

## Motion

None. Hover is a color change only. Reduced-motion rule is present as a safeguard.

## Decision reasons

- Left rail: keeps categories visible while browsing 653 assets, without a dropdown.
- Sharp edges: Swiss catalog character, set deliberately against the former soft-corner version.
- Mid-tone page: white sticker borders were invisible on near-white.
- Sans-serif only: clear, fast, and distinct from the previous editorial direction.
- No cards: stickers stay embedded in the page, as requested.
