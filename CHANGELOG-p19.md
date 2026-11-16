# AGRISCAN p19 — sidebar gradient, sign-in panel

## Why the gradient changed between pages

`.as-sidebar` is a flex child of `.as-shell`, so it stretched to whatever the page
content was. A `180deg` gradient then spanned about 900 px on the Map and over
2000 px on Overview — and only the first portion was ever on screen. Same colours,
different slice of the ramp, so it read as a different gradient on every page.

Fixed by pinning the sidebar to the viewport:

```css
.as-sidebar {
  position: sticky; top: 0; align-self: flex-start;
  height: 100vh; overflow-y: auto;
}
```

The gradient now always spans exactly the viewport. The navigation also stays in
view on long pages, which it did not before.

## Sign-in

- **Footer removed.** The school and group line is gone.
- **Description enlarged**: 16.5 px at 1.65 line height, heading to 30 px. It was
  the reason to read the panel and was the smallest text on it.
- **Background added.** A drawn contour pattern over the gradient, inline SVG, no
  external file. The server runs on a local machine with unreliable internet, so the
  page must not depend on fetching an image.
- Layout corrected: with the footer gone, `space-between` would have pinned the
  description to the bottom edge. Brand at the top, description centred.

## On the crash

I could not reproduce it. Backend 265 and frontend 15 pass, the build is clean, and
the three p18 page edits were class-name swaps only — `MapPage` was not among them,
so Leaflet is untouched.

To fix it I need the actual error. Either:

- the red text in the browser console, F12, Console tab, or
- the traceback in the PowerShell window running `python run.py`

A white screen with nothing in the console usually means the backend is down, which
on this machine has meant MySQL not started in XAMPP.
