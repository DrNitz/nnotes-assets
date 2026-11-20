# N-Notes Assets design direction

Owner direction, in their words: "the Ui and design should be minimalist soft corners the stickers should feel as if they are embeded not bulky photo container".

## Identity

A practical catalog of stickers and frames for people building note apps. The assets are the subject. The interface stays out of their way.

## Dials

ENERGY 1 / RHYTHM 1 / MOTION 1.

## Palette

- Paper `#F6F5F1`: page background, chosen so light sticker artwork sits on a calm neutral without a panel behind it.
- Ink `#14141A`: primary text.
- Secondary `#565660`: labels and inactive controls.
- Accent `#2F5BD8`: active tab, focus ring, and link underlines only. It comes from the N-Notes logo family, used at the key moment instead of across every surface.

Neutral white is used for the search field only.

Contrast checked with the antislop-human script: ink on paper 16.82:1, secondary on paper 6.65:1, white on accent 5.82:1. All pass normal text.

## Typography

System UI stack (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`). Reason: no network font request, and the neutral voice keeps attention on the artwork. Heading weight 650 with slight negative tracking.

## Shape and elevation

Radius 10 to 12px on inputs and category chips, 0 on tab underlines. One hairline rule under the header. No cards, no shadows, no blur, no gradients. Stickers sit directly on the page with no container, border, or backing panel.

## Layout

No hero. A masthead with title and one line of plain description, a search field, row of collection tabs, scrollable category chips, then a single responsive grid of assets. Section rhythm is deliberately uniform because this is a catalog, not a landing page.

## States

Loading, empty, and error states are text with a real action. No fabricated numbers or content. Asset counts come from the fetched JSON.

## Theme

Light only. Reason: the stickers are authored on light backgrounds and a dark theme would change how the artwork is perceived. No theme toggle.

## Motion

None. Hover is a color change only. Non-essential motion is absent, so reduced-motion needs no exception beyond resetting transitions.

## Decision reasons

- No photo containers: the owner asked for embedded stickers.
- No dark default: artwork color fidelity matters more than a "tech" look.
- System font: avoids a render-blocking font request.
- Search at top: the fastest path into 653 assets.
