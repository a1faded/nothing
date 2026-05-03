# Performance Flow Changes

This build changes the app from an "every widget change rebuilds the slate" flow to a cached, layered flow.

## Main changes

- Predictor filters are now inside an Apply Filters form.
  - Users can change multiple sliders/dropdowns without triggering repeated reruns.
  - The app reruns once after clicking **Apply Filters**.

- Expensive slate preparation is cached.
  - Base CSV loading is cached.
  - API signal pulls are cached with a short TTL.
  - Scored/enriched slate preparation is cached and reused across filter/sort display reruns.

- Added **Data / Performance Controls**.
  - **Refresh Live Data** clears Streamlit's data cache, increments a session refresh counter, and reruns.
  - Normal browsing uses cached data until TTL expiration or manual refresh.

- Non-predictor pages reuse the same cached slate builder.
  - Player Profile and Under Targets use the enriched cached slate.
  - Parlay Builder uses a lighter cached slate without Tank/proposition enrichment because the previous flow did not require those overlays.

## Deployment note

After deploying to Streamlit Cloud, use the app's **Refresh Live Data** button once or clear cache/reboot from Streamlit if you suspect stale data from an older build.
