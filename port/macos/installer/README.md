# macOS installer background

`background.svg` is a deterministic 680 × 440 point design. Pale panels support
Finder's native black labels: **Halo OG.app** centered at **(160, 220)** and the
**Applications** alias at **(520, 220)**, both with a **96 point** icon size.
The heading and instruction sit above the icons; the arrow connects their
centers without entering either icon region. Finder supplies the icon labels.
Each panel is 192 × 163 points, from y=153 to y=316, with a 16 point corner radius.

Render with the native macOS SVG decoder; no extra packages or fonts are needed:

```sh
swift -module-cache-path build/macos/installer-module-cache \
  port/macos/installer/render_background.swift \
  port/macos/installer/background.svg build/macos/installer/background.png 1
swift -module-cache-path build/macos/installer-module-cache \
  port/macos/installer/render_background.swift \
  port/macos/installer/background.svg build/macos/installer/background@2x.png 2
```

The scale argument accepts `1` or `2` and defaults to `2`. The PNG records its
680 × 440 point size (72 DPI at 1x; 144 DPI at 2x). Use scale `1` if the consuming
Finder layout requires literal pixel dimensions. Raster output uses the system's
Helvetica Neue font and native SVG renderer; macOS font/renderer revisions can
change rasterization while the vector layout remains fixed.

`tools/macos_dmg.py` renders both scales and combines them into the hidden
`.background.tiff` inside the DMG. Its Finder metadata uses that background
for the icon-view window. Do not add baked app or folder icons to the SVG.
