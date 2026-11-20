# N-Notes Assets design direction

Owner direction, in their words: "the Ui and design should be minimalist soft corners the stickers should feel as if they are embeded not bulky photo container".

## Identity

A practical catalog of stickers and frames for people building note apps. The assets are the subject. The interface stays out of their way.

Premium is expressed as editorial restraint: a serif display title, generous whitespace, and hairline rules. No glass, glow, gradient, or extra radius. The word "premium" is a direction for the design, not marketing copy on the page.

## Dials

ENERGY 1 / RHYTHM 1 / MOTION 1. Premium here means craft and restraint, not louder motion or more decoration.

## Palette

- Paper `#96938B`: page background, a mid-tone chosen so both white die-cut borders and dark artwork read on it. Near-white made white sticker lines disappear.
- Ink `#14141A`: primary text.
- Secondary `#26262B`: labels and inactive controls.
- Accent `#0A2266`: active tab, focus ring, and link underlines only. Deepened from the logo blue so it stays legible on the mid-tone page.

Neutral white is used for the search field only.

Contrast checked with the antislop-human script: ink on paper 5.98:1, secondary on paper 4.91:1, accent on paper 4.77:1, white sticker borders on paper 3.07:1. All text passes 4.5:1 and white borders pass the 3:1 non-text bar.

## Typography

System UI stack for controls (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`). Reason: no network font request, and the neutral voice keeps attention on the artwork. Display title uses a local serif stack (Georgia, "Times New Roman", serif) to give the catalog an editorial, print feel without a network font. Asset names use the same serif, smaller.

## Shape and elevation

Radius 10px on inputs and category chips, 0 on tab underlines. Hairline rules under the masthead and above the footer, both at 3:1 against the page. No cards, no shadows, no blur, no gradients. Stickers sit directly on the page with no container, border, or backing panel. Generous vertical spacing between groups, tighter spacing inside a group.

## Layout

No hero. A masthead with title and one line of plain description, a search field, row of collection tabs, scrollable category chips, then a single responsive grid of assets. Section rhythm is deliberately uniform because this is a catalog, not a landing page.

## States

Loading, empty, and error states are text with a real action. No fabricated numbers or content. Asset counts come from the fetched JSON.

## Theme

One fixed mid-tone theme. Reason: sticker artwork includes both white die-cut borders and dark ink, and only a mid-tone page keeps both visible. A dark theme would hide dark details; a light theme hides white lines. No theme toggle.

## Motion

None. Hover is a color change only. Non-essential motion is absent, so reduced-motion needs no exception beyond resetting transitions.

## Decision reasons

- No photo containers: the owner asked for embedded stickers.
- No dark default: artwork color fidelity matters more than a "tech" look.
- Mid-tone page, not near-white: white sticker borders were invisible on a light page. Checked at 3.07:1 against the new paper tone.
- Serif display title: gives the catalog an editorial voice; system fonts keep the page fast and offline-safe.
- Hairline rules at 3.22:1: define structure without building boxes around stickers.
- System font: avoids a render-blocking font request.
- Search at top: the fastest path into 653 assets.
