# ImageGen assets for Lumen

## Mode

Built-in ImageGen was used in generation mode. The target reference guided palette, density, silhouette, and contrast; no reference artwork was copied into the generated files. Each sheet used a flat `#ff00ff` chroma background, which was removed locally to produce RGBA PNG assets.

## Prompt set

### ChatBoks lockup

> Create a compact horizontal desktop-app logo lockup for ChatBoks: a small isometric chat cube followed by the exact text "ChatBoks". Use restrained cyan, blue-gray, graphite, and soft off-white, with crisp technical geometry, subtle metallic depth, no bloom, no extra text, and a flat #ff00ff chroma-key background. The result must remain legible at 23 px high inside a dense near-black AI workstation header.

### Agent role symbols

> Create a precise 2x2 sprite sheet of four compact role symbols for a dark desktop AI console. Top-left Claude: aperture/radiating analysis symbol. Top-right Codex: wireframe cube. Bottom-left Spark: angular lightning symbol. Bottom-right Orchestrator: routing nodes. Use a consistent cyan/slate line language, restrained glow, square safe areas, no letters, no labels, no overlap, and a flat #ff00ff chroma-key background. Each symbol must remain recognizable at 18 px.

### Agent portraits

> Create a precise 2x2 sprite sheet of four distinct synthetic operator portraits for a compact desktop AI console: analytical Claude, technical Codex, energetic Spark, and coordinating Orchestrator. Front-facing dark graphite robotic busts, restrained cyan/teal accents, consistent camera and crop, transparent-ready silhouette, no text, no overlap, and a flat #ff00ff chroma-key background. Each portrait must read clearly in a 32 px square avatar tile.

## Final runtime files

- `mobile_remote/www/assets/lumen-chatboks-lockup.png`
- `mobile_remote/www/assets/lumen-claude-symbol.png`
- `mobile_remote/www/assets/lumen-codex-symbol.png`
- `mobile_remote/www/assets/lumen-spark-symbol.png`
- `mobile_remote/www/assets/lumen-orchestrator-symbol.png`
- `mobile_remote/www/assets/lumen-claude-avatar.png`
- `mobile_remote/www/assets/lumen-codex-avatar.png`
- `mobile_remote/www/assets/lumen-spark-avatar.png`
- `mobile_remote/www/assets/lumen-orchestrator-avatar.png`
- `C:/Users/R/Desktop/The Core/apps/Lumen OverlayV2Claude/LumenV3/lumen/public/chatboks-lockup-lumen.png`

All runtime images are RGBA PNGs with transparent corners. The role symbols are normalized to 256 x 256, the portraits to 512 x 512, and the lockup to 674 x 192.
