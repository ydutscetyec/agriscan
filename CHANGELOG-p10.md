# AGRISCAN p10 — Detections page and Overview resilience

## Detections

The filter block took about 200 px before any data was visible, and eight controls
were always open when most sessions use one.

- **Quick filters.** All, Awaiting review, Low confidence, Verified. One click to the
  views a technician actually opens; previously four interactions through the panel.
- **Advanced filters collapse** behind a "More filters" button that shows how many are
  active, with a Clear filters chip beside it.
- **Result line** above the table: showing 51-100 of 340, how many filters are on, and
  a note when severity is being filtered within the page rather than by the server.
- **Status as a left rule** on each row, in the same colour vocabulary as the map
  markers, so a list can be scanned without reading every badge.
- **Confidence as a short bar** beside the figure. Comparing lengths is faster than
  comparing digits, and the number is still there.
- Pagination controls hide when there is only one page.

### The empty state was misleading

It said "No detections match these filters" even with no filters set and nothing in the
database, which blames the user's filters for an empty system. The page now asks how many
detections exist at all and says which case it is:

- Nothing in the database: explains that no images have been processed, links to Upload.
- Filters match nothing: says how many exist in total and offers to clear them.

## Overview

One failing endpoint used to blank the whole page with "Internal server error."

The two calls are now independent. If the fields summary fails, the pipeline panel is
replaced by a message naming the error and pointing at the backend window, and the
charts and counters below still render. If detections fail, that is reported separately.

This does not fix the underlying 500. It makes the page say what broke instead of
showing nothing.

## Tests

Backend 265 passing, frontend 15 passing, build clean.
