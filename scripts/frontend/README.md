# Frontend

Single-page web UI for the Gazebo Terrain Generator, served by the Flask backend at `http://localhost:8080`.

## Stack

- [MapLibre GL JS](https://maplibre.org/) — open-source map rendering (key-less fork of Mapbox GL JS); base imagery from ESRI World Imagery
- [Mapbox GL Draw](https://github.com/mapbox/mapbox-gl-draw) — polygon selection tool (used programmatically on top of MapLibre)
- [Nominatim](https://nominatim.org/) — OpenStreetMap place-name search / reverse geocoding
- [Turf.js](https://turfjs.org/) — client-side geospatial utilities
- [Toastify](https://github.com/apvarun/toastify-js) — toast notifications
- [Font Awesome](https://fontawesome.com/) — icons
- Vanilla JavaScript (no framework)

## Files

```
frontend/
  index.html   — Single HTML file with all modals and UI structure
  js/main.js   — All application logic
  css/main.css — All styles
```