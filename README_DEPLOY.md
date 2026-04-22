# Streamlit deployment notes

This app is set up for Streamlit Community Cloud.

## Required secret
Add this in your app Secrets:

```toml
rapidapi_key = "YOUR_TANK01_RAPIDAPI_KEY"
```

You can also use an environment variable named `RAPIDAPI_KEY` for local runs.

## Entrypoint
Use `app.py` as the main file.

## Dependencies
This repo now includes `requirements.txt` for Streamlit Cloud installs.
