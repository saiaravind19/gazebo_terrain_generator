// Center point management for the map
let centerPoint = null;
let boundingBox = null;

function initializeCenterPoint(map) {
    // Create a draggable marker for the center point
    centerPoint = new mapboxgl.Marker({
        draggable: true,
        color: '#FF0000'
    });

    // Hide initially
    centerPoint.remove();

    // Handle when the rectangle is drawn
    map.on('draw.create', function (e) {
        if (e.features[0].geometry.type === 'Polygon') {
            const bounds = turf.bbox(e.features[0]);
            boundingBox = bounds;

            // Calculate center
            const center = [
                (bounds[0] + bounds[2]) / 2, // longitude
                (bounds[1] + bounds[3]) / 2  // latitude
            ];

            // Show and position the center point
            centerPoint.setLngLat(center)
                      .addTo(map);

            updatePointLocation(center[1], center[0]);
            updateCoordinatesDisplay(center[1], center[0]);
        }
    });

    // Update position when marker is dragged
    centerPoint.on('dragend', function() {
        const lngLat = centerPoint.getLngLat();
        
        // Ensure point stays within bounds
        if (boundingBox) {
            const lat = Math.min(Math.max(lngLat.lat, boundingBox[1]), boundingBox[3]);
            const lng = Math.min(Math.max(lngLat.lng, boundingBox[0]), boundingBox[2]);
            
            centerPoint.setLngLat([lng, lat]);
            updatePointLocation(lat, lng);
            updateCoordinatesDisplay(lat, lng);
        }
    });
}

function updateCoordinatesDisplay(lat, lng) {
    const coordsDiv = document.getElementById('coordinates');
    if (!coordsDiv) {
        const div = document.createElement('div');
        div.id = 'coordinates';
        div.className = 'coordinates-display';
        div.innerHTML = `
            <h4>Center Point</h4>
            <p>Latitude: <span id="point-lat">${lat.toFixed(6)}</span></p>
            <p>Longitude: <span id="point-lng">${lng.toFixed(6)}</span></p>
        `;
        document.body.appendChild(div);
    } else {
        document.getElementById('point-lat').textContent = lat.toFixed(6);
        document.getElementById('point-lng').textContent = lng.toFixed(6);
    }
}

function updatePointLocation(lat, lng) {
    fetch('/update-point', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            latitude: lat,
            longitude: lng
        })
    })
    .then(response => response.json())
    .then(data => console.log('Point updated:', data))
    .catch(error => console.error('Error:', error));
}
