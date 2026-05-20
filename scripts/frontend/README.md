# Frontend

Single-page web UI for the Gazebo Terrain Generator, served by the Flask backend at `http://localhost:8080`.

## Stack

- [Mapbox GL JS](https://docs.mapbox.com/mapbox-gl-js/) — map rendering and satellite imagery
- [Mapbox GL Draw](https://github.com/mapbox/mapbox-gl-draw) — polygon selection tool
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