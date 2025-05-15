# GAzebo Terrian Generator

A super easy to use GUI for downloading map tiles and generating 3d gazebo terrain.

<p align="center">
  <img src="gif/map-tiles-downloader.gif">
</p>

### Run Maptile downloader via command line
1. Navigate to `maptilesdownloader` directory.

    ```sh
    cd maptilesdownloader/src
    python server.py
    ```
2. To access application open up your web browser and navigate to `http://localhost:8080`.
3. The output map tiles will be in the `output\{timestamp}\` directory by default chnage it as per choice.


## Important Disclaimer

Downloading map tiles is subject to the terms and conditions of the tile provider. Some providers such as Google Maps have restrictions in place to avoid abuse, therefore before downloading any tiles make sure you understand their TOCs. I recommend not using Google, Bing, and ESRI tiles in any commercial application without their consent.

## License

This software is released under the [MIT License](LICENSE). Please read LICENSE for information on the
software availability and distribution.

Copyright (c) 2020 [Ali Ashraf](http://aliashraf.net)