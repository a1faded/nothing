# Sidebar Toggle Visibility Fix

This build keeps Streamlit's header visible because the sidebar open/close control is rendered inside the header on many Streamlit versions. The previous global CSS hid `header`, which could make the sidebar reopen button invisible after collapse.

The fix:
- hides only the default menu/footer, not the whole header
- keeps the header transparent so the dark custom UI remains intact
- styles multiple known Streamlit sidebar toggle selectors and aria-label variants
- makes the toggle larger, brighter, and high-z-index so it is easy to see on desktop and mobile

The app still includes main-page navigation and Predictor controls, so the sidebar is optional for mobile users.
