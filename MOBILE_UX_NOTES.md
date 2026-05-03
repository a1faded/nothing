# Mobile UX Update

This build moves the critical Predictor filters out of Streamlit's sidebar and into the main page.

## Why

Streamlit's sidebar is difficult to open and use on phones. The app now has:

- Main-page navigation at the top of every page
- Main-page Predictor Controls & Filters expander
- Sidebar retained for desktop navigation/status, but no longer required for core mobile usage

## Behavior

- Use the top `App Navigation` dropdown on mobile.
- On the Predictor page, open `Controls & Filters` to change target, park/game-condition toggles, lineup filters, stat filters, team filters, exclusions, sorting, and display count.
- Existing scoring, Tank BvP/splits, game logs, profile pages, and exports are unchanged.
