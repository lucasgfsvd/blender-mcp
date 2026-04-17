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

## Tools

This fork ships the upstream tool surface **plus ~40 engineering-specific tools**
implemented on top of `execute_blender_code` (no `addon.py` changes — the
upstream addon keeps working). All new tools are Python-dispatched: each crafts
a `bpy` snippet, dispatches it over the socket, and parses a JSON result.

### Scene inspection & generic scripting
| Tool | Purpose |
|---|---|
| `get_scene_info` | Inspect current scene (objects, camera, lights) |
| `get_object_info` | Inspect a single object (transform, mesh, materials) |
| `get_viewport_screenshot` | Capture the 3D viewport as an image |
| `execute_blender_code` | Run arbitrary `bpy` Python — the escape hatch for anything not covered by a named tool |

### Parametric engineering primitives
| Tool | Purpose |
|---|---|
| **Mechanical** ||
| `slotted_plate` | Rectangular plate with linear array of oblong slots |
| `perforated_plate` | Plate with square or staggered circular-hole grid |
| `l_bracket` / `t_bracket` / `u_channel` | Standard bracket / channel profiles |
| `rounded_box` | Box with beveled edges (enclosure shape) |
| `bolt_hole_pattern` | PCD or grid bolt-hole drilling on an existing object |
| `swept_tube` | Polyline-path tube with optional wall thickness |
| `truss_node` | Spherical hub with radiating cylindrical struts |
| **Aerospace / space** ||
| `cylindrical_tank` | Barrel + ellipsoidal/hemispherical/flat domes, optional hollow shell |
| `spherical_tank` | Solid or shelled pressure sphere |
| `cone_frustum` | Cone or frustum with optional wall thickness |
| `torus` | Parameterized torus |
| `satellite_bus` | 6-panel rectangular bus, optional deployed solar wings |
| `cubesat` | Hollow CubeSat frame sized in U |
| `rover_chassis` | 4-wheel rover with parametric wheelbase/track/clearance |
| `lander_leg` | Splayed strut + footpad |
| `planetary_terrain_patch` | Perlin-noise heightfield for rover/lander backdrops |

### Mesh simplification & defeaturing
| Tool | Purpose |
|---|---|
| `decimate` | Collapse decimate by ratio |
| `decimate_planar` | Dissolve coplanar faces by angle |
| `keep_outer_shell` | Delete interior faces (radiation-prep) |
| `delete_small_objects` | Drop bolts/fasteners below bbox-diagonal threshold; dry-run by default |
| `separate_loose_parts` | Split disconnected components into one object each |
| `fill_holes` | Close small boundary loops |
| `merge_duplicates` | Merge coincident vertices (remove doubles) |
| `triangulate` | Convert quads/n-gons to triangles |
| `remesh_voxel` / `remesh_quad` | Uniform watertight remesh (FE/CFD prep) |

### Engineering material library (22 materials)
Curated library with thermal (`k`, `cp`, `ρ`, CTE), optical (`ε_IR`, `α_solar`),
structural (`E`, yield, ν), and Blender shader values. Values are written to
Blender custom properties so export scripts can read them straight from the
`.blend` file.

| Tool | Purpose |
|---|---|
| `list_materials` | List available materials; filter by category (metal, composite, polymer, coating, insulation) |
| `get_material_properties` | Full property record for one material, including sources |
| `apply_material` | Create / reuse a Blender material from the library and assign it to an object |

Shipped entries include Al 6061/7075, Ti-6Al-4V, SS 316L, Invar 36, OFHC Cu,
CFRP quasi-iso, Kapton HN, PEEK, PTFE, G10/FR4, Z93 white paint, Z306 black
paint, Silvered Teflon, Aluminized Kapton (VDA), Black Kapton, effective MLI,
aerogel, and more.

### Engineering views & annotations
| Tool | Purpose |
|---|---|
| `render_views` | Auto-frame orthographic front/top/right/iso views; render to a directory |
| `add_dimension` | Linear dimension between two world points with offset leader and text label |
| `label_components` | Callout labels with leader lines for named objects |
| `add_scale_bar` | World-space scale bar with tick marks |

### Simulation visualization
| Tool | Purpose |
|---|---|
| `bake_scalar_field_to_colors` | Paint per-vertex or per-face scalar values onto a mesh via a chosen colormap (viridis, plasma, inferno, magma, coolwarm, jet) |
| `add_gradient_legend` | World-space color bar with min/max labels and units |
| `add_section_view` | Non-destructive boolean half-space clip on a target object |

### Asset libraries (opt-in, require your own API keys)
| Tool | Purpose |
|---|---|
| `get_polyhaven_categories` / `search_polyhaven_assets` / `download_polyhaven_asset` / `set_texture` | Poly Haven HDRIs, textures, models |
| `search_sketchfab_models` / `get_sketchfab_model_preview` / `download_sketchfab_model` | Sketchfab asset library |
| `generate_hyper3d_model_via_text` / `_via_images` / `poll_rodin_job_status` / `import_generated_asset` | Hyper3D Rodin text/image-to-3D |
| `generate_hunyuan3d_model` / `poll_hunyuan_job_status` / `import_generated_asset_hunyuan` | Tencent Hunyuan3D text/image-to-3D |
| `get_polyhaven_status` / `get_sketchfab_status` / `get_hyper3d_status` / `get_hunyuan3d_status` | Check which integrations are enabled in the addon |

---

## What you can ask

With the engineering tools above, most CAE-adjacent tasks are one prompt. Claude
chains the named tools and falls back to `execute_blender_code` when the tool
set doesn't cover something. Examples by category:

### Building parametric hardware
- *"Make a 3U CubeSat with 1.5 mm walls, apply Aluminum 6061, then drill an 80 mm PCD bolt pattern with 6 M3 holes on the +Z face."*
- *"Build a 500 mm diameter pressurized tank with 2:1 ellipsoidal domes, 4 mm Ti-6Al-4V wall, 800 mm barrel."*
- *"Create a satellite bus 1 × 0.8 × 1.2 m with deployed solar wings, Z93 white paint on the +X face, Silvered Teflon on -X, Aluminized Kapton on the remaining four."*
- *"Build a 4-wheel rover chassis — 1.2 m wheelbase, 0.9 m track, 0.25 m ground clearance — and drop it on a 100 m Perlin-noise terrain patch."*
- *"Extrude a 200 mm L-bracket with a 10 mm inner-corner fillet and 3 mm wall."*
- *"Swept tube along these waypoints: [[0,0,0],[0.5,0,0],[0.5,0.3,0.1]] — 12 mm OD, 1 mm wall."*

### Defeaturing an imported CAD assembly
- *"Import `./bracket.stl`, separate loose parts, then delete any object whose bounding-box diagonal is below 3 mm. Show me the dry-run list first."*
- *"Keep only the outer shell of `HeatSink` for radiation analysis, then fill any holes up to 6 sides."*
- *"Decimate `MainBody` to ratio 0.3, triangulate, and report the final triangle count."*
- *"Remesh `Enclosure` at 2 mm voxel size so I can export a clean STL for Gmsh."*

### Scene inspection & debugging
- *"Screenshot the viewport and tell me whether the radiator panel is aligned with the coldplate."*
- *"List every mesh object with its bounding-box dimensions in mm, sorted by volume."*
- *"What library material is assigned to `Radiator`, and what ε_IR and α_solar did it get?"*

### Producing report figures
- *"Render front, top, right, and iso views of `Assembly` to `./figures/` at 1920×1080, transparent background."*
- *"Add a 100 mm scale bar next to `Plate`, and label `Heat Spreader`, `Fin Stack`, and `Coldplate` with leader lines."*
- *"Add a dimension between `Bolt1` and `Bolt2` showing the distance in mm."*

### Visualizing simulation results
- *"Here's a 1-D array of surface temperatures in K [per-face for `Radiator`]: bake them onto the mesh with viridis between 250 and 320 K, then add a gradient legend on the +X side of the scene."*
- *"Add a section view of `SatBus` through the XZ plane (normal +Y) — keep it as a modifier so I can toggle it."*

### Pulling in real assets (Poly Haven, Sketchfab)
- *"Find a brushed-aluminium PBR texture on Poly Haven and apply it to `CoolingFin`."*
- *"Search Sketchfab for 'cubesat 3U', show me a preview of the top result, and import it at 340 mm length."*

### AI-generated assets (Hyper3D Rodin / Hunyuan3D)
- *"Generate a 3D model of 'a wall-mounted condenser unit' with Hyper3D, scale to 400 mm, place against +Y wall."*

> ⚠️ Several tools are **destructive by design** (boolean modifier apply, remesh apply, interior-face deletion). Keep backups of `.blend` files you care about. `delete_small_objects` defaults to `dry_run=True` so you can preview before committing.

---

## Engineering-context roadmap

This fork exists because I use Blender alongside FreeCAD and Elmer/OpenFOAM for
thermal and mechanical engineering work (spacecraft TVAC, heat pipes, cold
plates, PCM design). Most of the engineering tool surface is now shipped (see
the **Tools** section above). What remains is the I/O and pipeline work.

### Outstanding

1. **VTK / XDMF / HDF5 result viewer** — load Elmer, OpenFOAM, or CalculiX
   result meshes as attribute-carrying point clouds or baked vertex-color
   meshes. Today you can pre-extract values into a 1-D array and use
   `bake_scalar_field_to_colors`; first-class result-file ingestion would
   remove that step.
2. **Gmsh `.msh` / `.geo` import/export** — so Claude can drive mesh refinement
   iterations directly.
3. **FreeCAD pipeline helpers** — probably *not* built into this fork; the
   cleaner architecture is for [`freecad-mcp`](https://github.com/lucasgfsvd/freecad-mcp)
   (companion project) to own CAD I/O (STEP/IGES, feature-aware defeaturing,
   fillets/chamfers). The model chains the two servers at runtime:
   *freecad-mcp opens the STEP and exports STL → blender-mcp imports it.*
4. **Solver drivers** — `elmer_run(case_dir)`, `compare_geometry(stl_before,
   stl_after, tolerance)` for regression sweeps. Out of scope until after the
   VTK viewer and a stable solver wrapper are in place.

### Shipped in this fork

- **Parametric primitives** — mechanical (slotted/perforated plates, brackets,
  channels, rounded boxes, bolt-hole patterns, swept tubes, truss nodes) and
  aerospace (cylindrical/spherical tanks, cones, tori, satellite buses,
  CubeSats, rover chassis, lander legs, terrain patches).
- **Mesh simplification / defeaturing** — decimate, planar decimate, interior
  face removal, small-object filtering, loose-part separation, hole fill, weld,
  triangulate, voxel/quad remesh.
- **Material library** — 22 aerospace materials with thermal/optical/structural
  metadata, applied as Blender custom properties for downstream simulation
  export.
- **Engineering views & annotations** — auto-framed orthographic renders,
  linear dimensions, component labels with leader lines, scale bars.
- **Simulation visualization** — scalar-field color baking (6 colormaps),
  world-space gradient legend, non-destructive section-view clipping.

---

## Running without Blender open

The MCP server will start and then log `Failed to connect to Blender: [WinError 10061]` — that's expected. Open Blender, click **Connect to MCP server** in the BlenderMCP sidebar, and future requests succeed. The server reconnects on the next tool call.

---

## License

MIT — see `LICENSE`. Original copyright © Siddharth Ahuja; fork modifications © lucasgfsvd. Both are permissively licensed; keep this `LICENSE` file in any redistribution.
