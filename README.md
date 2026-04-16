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
Clone this repo, then:
- *Edit → Preferences → Add-ons → Install...* → select `addon.py`
- Enable the checkbox next to "Interface: Blender MCP"
- In the 3D Viewport press **N** → **BlenderMCP** tab → **Connect to MCP server**

### 2. Point your MCP client at this fork

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "blender": {
      "command": "C:\\Users\\YOU\\.local\\bin\\uvx.exe",
      "args": [
        "--from",
        "git+https://github.com/lucasgfsvd/blender-mcp",
        "blender-mcp"
      ]
    }
  }
}
```

On macOS/Linux replace `command` with `uvx` and adjust path.

Restart the client. The server will launch on demand, connect to Blender on `localhost:9876`, and expose the full tool surface.

---

## Built-in tools

| Tool | Purpose |
|---|---|
| `get_scene_info` | Inspect current scene (objects, camera, lights) |
| `get_object_info` | Inspect a single object (transform, mesh, materials) |
| `get_viewport_screenshot` | Capture the 3D viewport as an image |
| `execute_blender_code` | Run arbitrary `bpy` Python inside Blender |
| `get_polyhaven_*` / `download_polyhaven_asset` | Poly Haven HDRIs/textures/models |
| `search_sketchfab_models` / `download_sketchfab_model` | Sketchfab asset library |
| `generate_hyper3d_model_via_text` / `_via_images` | Hyper3D Rodin text/image-to-3D |
| `poll_rodin_job_status` / `import_generated_asset` | Retrieve generated assets |

All external-service tools are **opt-in** via toggles in the addon sidebar, and require your own API keys.

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
