# Blender MCP — Telemetry-Free Fork

Control Blender from Claude Desktop (or any MCP client) over a local socket. This is a fork of [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) with **all telemetry and third-party analytics removed**.

> **Attribution.** All original Blender-integration code is the work of **Siddharth Ahuja** ([@sidahuj](https://x.com/sidahuj)), released under MIT. This fork keeps the original `LICENSE` and only modifies the telemetry stack, packaging, and docs. If you find this useful, consider [sponsoring the original author](https://github.com/sponsors/ahujasid).

---

## What's different from upstream

- Deleted `src/blender_mcp/telemetry.py` and `src/blender_mcp/telemetry_decorator.py`.
- Stripped all `@telemetry_tool(...)` decorators and `record_startup()` calls from `server.py`.
- Removed the `telemetry_consent` addon preference, its UI panel, and the `get_telemetry_consent` RPC from `addon.py`.
- Dropped `supabase` and `tomli` from dependencies — no outbound HTTP to any analytics backend.
- Removed `TERMS_AND_CONDITIONS.md` and the in-addon "View Terms" button (they only existed to cover data collection).

Net result: this package talks to **exactly three things** — the local MCP client over stdio, the Blender addon over `localhost:9876`, and any asset/model-gen API *you explicitly enable* (Poly Haven, Sketchfab, Hyper3D Rodin, Tencent Hunyuan3D). No hidden egress.

---

## Architecture

```
Claude Desktop  <-- stdio -->  blender-mcp server  <-- TCP:9876 -->  Blender addon  <-- bpy -->  scene
```

- `src/blender_mcp/server.py` — the MCP server process (launched by your client via `uvx`).
- `addon.py` — the Blender-side listener; install it once, then click **Connect to MCP server** in the 3D Viewport sidebar.

---

## Quick start

### Prerequisites
- Blender 3.0+ (tested on 5.1)
- Python 3.10+ (bundled with modern Blender is fine)
- [`uv`](https://astral.sh/uv/) installed and on PATH

### 1. Install the addon in Blender
Grab [`addon.py`](addon.py) from this repo (GitHub → *Raw* → save), then in Blender:
- *Edit → Preferences → Add-ons → Install...* → select the saved `addon.py`
- Enable the checkbox next to "Interface: Blender MCP"
- In the 3D Viewport press **N** → **BlenderMCP** tab → **Connect to MCP server**

### 2. Install the MCP server

Pre-install as a persistent `uv` tool (recommended — no `git` required at client startup):

```bash
uv tool install git+https://github.com/lucasgfsvd/blender-mcp
```

This places `blender-mcp.exe` (or `blender-mcp` on \*nix) under your `uv` tool bin. Upgrade later with `uv tool upgrade blender-mcp`.

### 3. Point your MCP client at it

**Claude Desktop** (`claude_desktop_config.json`) — direct exe, no git needed at spawn:

```json
{
  "mcpServers": {
    "blender": {
      "command": "C:\\Users\\YOU\\.local\\bin\\blender-mcp.exe",
      "args": []
    }
  }
}
```

On macOS/Linux the command is typically `~/.local/bin/blender-mcp`.

<details>
<summary>Alternative: on-demand via <code>uvx</code> (requires <code>git</code> on PATH)</summary>

```json
{
  "mcpServers": {
    "blender": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lucasgfsvd/blender-mcp", "blender-mcp"]
    }
  }
}
```

Heads-up: on Windows, MCP subprocesses don't always inherit `git.exe` on PATH and this form will fail with `Git executable not found`. Prefer the pre-installed form above.
</details>

Restart the client. The server will launch on demand, connect to Blender on `localhost:9876`, and expose the full tool surface.

---

## Built-in tools

| Tool | Purpose |
|---|---|
| `get_scene_info` | Inspect current scene (objects, camera, lights) |
| `get_object_info` | Inspect a single object (transform, mesh, materials) |
| `get_viewport_screenshot` | Capture the 3D viewport as an image |
| `execute_blender_code` | Run arbitrary `bpy` Python inside Blender — the workhorse for modeling/editing |
| `get_polyhaven_categories` / `search_polyhaven_assets` / `download_polyhaven_asset` / `set_texture` | Poly Haven HDRIs, textures, models |
| `search_sketchfab_models` / `get_sketchfab_model_preview` / `download_sketchfab_model` | Sketchfab asset library |
| `generate_hyper3d_model_via_text` / `_via_images` / `poll_rodin_job_status` / `import_generated_asset` | Hyper3D Rodin text/image-to-3D |
| `generate_hunyuan3d_model` / `poll_hunyuan_job_status` / `import_generated_asset_hunyuan` | Tencent Hunyuan3D text/image-to-3D |
| `get_polyhaven_status` / `get_sketchfab_status` / `get_hyper3d_status` / `get_hunyuan3d_status` | Check which integrations are enabled in the addon |

All external-service tools are **opt-in** via toggles in the addon sidebar, and require your own API keys.

---

## What you can ask

Because `execute_blender_code` lets the model run arbitrary `bpy` Python in the live session, you can describe geometry and edits in natural language and let Claude translate them. A few categories with representative prompts:

### Modeling from scratch
- *"Build a 100 × 100 × 20 mm heat-spreader plate with four M3 through-holes on an 80 mm bolt circle, centered at the origin."*
- *"Extrude a 200 mm L-bracket with a 10 mm fillet on the inner corner and a 4 mm wall thickness."*
- *"Array this bolt 8 times around the Z axis at 50 mm radius."*
- *"Create a 6×6 honeycomb lattice inside the current cube using Geometry Nodes."*

### Editing the current scene
- *"Select the cube, subdivide it twice, then shade smooth."*
- *"Move the camera so the assembly fills the frame from the front-right iso angle at 30° elevation."*
- *"Add a sun light from +Z at 5 kW/m² and a fill area light from −X at 500 W."*
- *"Parent all mesh objects named `Fin_*` to an empty called `FinStack`."*

### Inspecting & debugging
- *"Screenshot the viewport and tell me whether the radiator panel is aligned with the coldplate."* — uses `get_viewport_screenshot`
- *"List every mesh object in the scene with its bounding-box dimensions in mm, sorted by volume."* — uses `get_scene_info` + `get_object_info`
- *"What materials are assigned to `CoolingFin`, and what's the base colour of each?"*

### Pulling in real assets (Poly Haven, Sketchfab)
- *"Find a brushed-aluminium PBR texture on Poly Haven and apply it to `CoolingFin`."*
- *"Search Sketchfab for 'cubesat 3U', show me a preview of the top result, and import it at 340 mm length."*
- *"Load a studio HDRI for the world background at strength 0.6."*

### AI-generated assets (Hyper3D Rodin / Hunyuan3D)
- *"Generate a 3D model of 'a wall-mounted condenser unit' with Hyper3D, then scale it to 400 mm and place it against the +Y wall."*
- *"Turn this photo of a bracket (`C:/tmp/bracket.jpg`) into a 3D mesh via Hunyuan3D and import it."*

### Rendering for reports
- *"Render the current scene at 1920×1080 with Cycles, 128 samples, save to `plate_iso.png`."*
- *"Set up an orthographic camera and render front, top, and right views to `figures/` at 300 DPI equivalent."*

> ⚠️ `execute_blender_code` is powerful — Claude can delete objects, overwrite materials, or run anything the Blender session could. Keep backups of `.blend` files you care about, and review generated code before green-lighting destructive operations.

---

## Engineering-context roadmap

This fork exists because I use Blender alongside FreeCAD and Elmer/OpenFOAM for thermal and mechanical engineering work (spacecraft TVAC, heat pipes, cold plates, PCM design). The upstream addon is great for art and asset pipelines; the roadmap below is where I'd like to take it for CAE use. Contributions welcome.

### 1. Engineering-grade import/export
- **STEP / IGES bridge** — round-trip through FreeCAD's headless CLI, so Claude can say "open this `.step`, add a 3 mm fillet on the heat-spreader edge, export back."
- **VTK / XDMF / HDF5 viewer** — load Elmer, OpenFOAM, or CalculiX result meshes as attribute-carrying point clouds or baked vertex-color meshes for publication renders.
- **Gmsh `.msh` + `.geo`** — import/export so Claude can drive mesh refinement iterations.

### 2. Parametric primitives for thermal hardware
- `make_cold_plate(w, d, h, fin_count, fin_thickness, fin_pitch)` — procedural fin arrays.
- `make_heat_pipe(d_outer, wall, length, bends=[...])` — swept profile along a path.
- `make_pcm_enclosure(w, d, h, wall, fill_ratio)` — honeycomb/foam lattice fill via geometry nodes.
- `make_radiator_panel(area, facesheet_t, core_type, core_t)` — sandwich panels with correct thickness stack.

### 3. Simulation-driven visualization
- `bake_scalar_field_to_colors(object, values, colormap="viridis", range=[a,b])` — take a 1-D array of per-vertex or per-face scalars (temperatures, stresses, fluxes) and bake it as vertex color or texture with proper scale bar.
- `add_gradient_legend(min, max, units, colormap)` — auto-place a color-bar in world space for renders.
- `add_section_view(plane_origin, plane_normal)` — clipping plane with cap shader for cross-section figures.

### 4. Standard engineering views & drawings
- `render_iso_views(object, output_dir)` — auto-frame front/top/side/iso at fixed orthographic scale for report figures.
- `add_dimension(a, b, offset, units="mm")` — DXF-style linear dimension annotation as world-space text and line.
- `label_components(mapping)` — auto-callout labels with leader lines (for exploded views).

### 5. FreeCAD / Elmer pipeline helpers
- `freecad_exec(script_py)` — run a FreeCAD Python script headlessly from Claude, return exported STEP/STL path.
- `elmer_run(case_dir)` — trigger an Elmer case and return the results path for subsequent visualization.
- `compare_geometry(stl_before, stl_after, tolerance)` — Hausdorff-style diff for regression checks on parametric sweeps.

### 6. Material library with physics metadata
- Ship a small JSON library (Al 6061, Cu C101, Ti 6Al-4V, kapton, FR4…) mapped to Blender materials + carrying `{k, cp, rho, epsilon_IR, alpha_solar}` as custom properties. Lets simulation tools read them straight from the `.blend`.

---

## Running without Blender open

The MCP server will start and then log `Failed to connect to Blender: [WinError 10061]` — that's expected. Open Blender, click **Connect to MCP server** in the BlenderMCP sidebar, and future requests succeed. The server reconnects on the next tool call.

---

## License

MIT — see `LICENSE`. Original copyright © Siddharth Ahuja; fork modifications © lucasgfsvd. Both are permissively licensed; keep this `LICENSE` file in any redistribution.
