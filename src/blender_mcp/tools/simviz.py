"""
Simulation-driven visualization.

Tools for turning CAE results into renderable scenes:

- bake_scalar_field_to_colors: paint per-vertex or per-face scalar values
  (temperatures, stresses, fluxes) onto a mesh via a chosen colormap.
- add_gradient_legend: place a world-space color bar with min/max labels.
- add_section_view: add a non-destructive boolean clipping modifier that
  shows a cross-section of an object.

Colormaps are 5-stop linear interpolations of matplotlib's canonical ramps;
values are in linear RGB so they display correctly under Blender's color
management.
"""

import json
import textwrap

from mcp.server.fastmcp import FastMCP, Context


# 5-stop approximations of common matplotlib colormaps, linear-RGB.
_COLORMAPS = {
    "viridis": [
        (0.267, 0.005, 0.329),
        (0.229, 0.322, 0.545),
        (0.127, 0.567, 0.551),
        (0.369, 0.788, 0.383),
        (0.993, 0.906, 0.144),
    ],
    "plasma": [
        (0.050, 0.029, 0.528),
        (0.451, 0.000, 0.660),
        (0.798, 0.280, 0.470),
        (0.989, 0.558, 0.200),
        (0.940, 0.975, 0.131),
    ],
    "inferno": [
        (0.002, 0.001, 0.014),
        (0.317, 0.071, 0.485),
        (0.731, 0.215, 0.331),
        (0.988, 0.532, 0.038),
        (0.988, 1.000, 0.645),
    ],
    "magma": [
        (0.002, 0.001, 0.014),
        (0.282, 0.081, 0.412),
        (0.716, 0.215, 0.475),
        (0.989, 0.539, 0.386),
        (0.987, 0.992, 0.750),
    ],
    "coolwarm": [
        (0.230, 0.299, 0.754),
        (0.566, 0.698, 0.894),
        (0.865, 0.865, 0.865),
        (0.898, 0.576, 0.458),
        (0.706, 0.016, 0.150),
    ],
    "jet": [
        (0.000, 0.000, 0.498),
        (0.000, 0.500, 1.000),
        (0.498, 1.000, 0.498),
        (1.000, 0.500, 0.000),
        (0.498, 0.000, 0.000),
    ],
}


def _colormap_literal(name: str) -> str:
    """Emit the colormap stops as a Python list literal for embedding."""
    stops = _COLORMAPS.get(name) or _COLORMAPS["viridis"]
    return repr(stops)


def register(mcp: FastMCP) -> None:
    from blender_mcp.server import _run_in_blender, _snippet_header

    def _dispatch(body: str) -> str:
        return json.dumps(_run_in_blender(_snippet_header() + body), indent=2)

    @mcp.tool()
    def bake_scalar_field_to_colors(
        ctx: Context,
        object_name: str,
        values: str,
        domain: str = "point",
        colormap: str = "viridis",
        vmin: float = 0.0,
        vmax: float = 0.0,
        attribute_name: str = "SimField",
        build_material: bool = True,
    ) -> str:
        """
        Paint a scalar field onto a mesh as a color attribute and (optionally)
        assign a material that visualizes it.

        Parameters:
        - object_name: Target mesh.
        - values: JSON list of floats. Length must equal:
                  * number of vertices, if domain="point"
                  * number of faces, if domain="face"
        - domain: "point" or "face".
        - colormap: viridis | plasma | inferno | magma | coolwarm | jet.
        - vmin, vmax: Value range mapped to 0..1. If vmin == vmax, auto-fit
                      from the data.
        - attribute_name: Name of the color attribute added to the mesh.
        - build_material: If True (default), also create/assign a material that
                          shows the attribute via a Color Attribute shader node.
        """
        cmap = _colormap_literal(colormap)
        body = textwrap.dedent(f'''
            import json as _json
            vals = _json.loads({values!r})
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}}); raise SystemExit
            mesh = obj.data
            domain = {domain!r}
            expected = len(mesh.vertices) if domain == "point" else len(mesh.polygons)
            if len(vals) != expected:
                _emit({{"error": f"expected {{expected}} values for domain {{domain!r}}, got {{len(vals)}}"}})
                raise SystemExit

            vmn, vmx = {vmin!r}, {vmax!r}
            if vmn == vmx:
                vmn, vmx = min(vals), max(vals)
                if vmn == vmx:
                    vmx = vmn + 1.0  # avoid div-by-zero on constant fields

            stops = {cmap}
            def _colorize(t):
                t = max(0.0, min(1.0, t))
                pos = t * (len(stops) - 1)
                i0 = int(pos)
                i1 = min(len(stops) - 1, i0 + 1)
                f = pos - i0
                r = stops[i0][0] * (1 - f) + stops[i1][0] * f
                g = stops[i0][1] * (1 - f) + stops[i1][1] * f
                b = stops[i0][2] * (1 - f) + stops[i1][2] * f
                return (r, g, b, 1.0)

            # Add / reuse color attribute
            attr_name = {attribute_name!r}
            ca = mesh.color_attributes.get(attr_name)
            if ca is None:
                domain_enum = "POINT" if domain == "point" else "FACE"
                ca = mesh.color_attributes.new(name=attr_name, type="FLOAT_COLOR", domain=domain_enum)

            # Write colors
            if domain == "point":
                for i, v in enumerate(vals):
                    t = (v - vmn) / (vmx - vmn)
                    ca.data[i].color = _colorize(t)
            else:  # face domain
                for i, v in enumerate(vals):
                    t = (v - vmn) / (vmx - vmn)
                    ca.data[i].color = _colorize(t)

            ca.active = True
            mesh.update()

            mat_name = None
            if {build_material!r}:
                mn = f"SimField_{{attr_name}}"
                mat = bpy.data.materials.get(mn) or bpy.data.materials.new(mn)
                mat.use_nodes = True
                nt = mat.node_tree
                for n in list(nt.nodes): nt.nodes.remove(n)
                out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (400, 0)
                bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (100, 0)
                bsdf.inputs["Roughness"].default_value = 0.8
                ca_node = nt.nodes.new("ShaderNodeVertexColor"); ca_node.location = (-200, 0)
                ca_node.layer_name = attr_name
                nt.links.new(ca_node.outputs["Color"], bsdf.inputs["Base Color"])
                nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
                if obj.data.materials:
                    obj.data.materials[0] = mat
                else:
                    obj.data.materials.append(mat)
                mat_name = mat.name

            _emit({{
                "object": obj.name,
                "attribute": attr_name,
                "domain": domain,
                "values_count": len(vals),
                "vmin": vmn, "vmax": vmx,
                "colormap": {colormap!r},
                "material": mat_name,
            }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def add_gradient_legend(
        ctx: Context,
        vmin: float = 0.0,
        vmax: float = 100.0,
        units: str = "K",
        colormap: str = "viridis",
        position: str = "[0,0,0]",
        length: float = 0.5,
        width: float = 0.05,
        orientation: str = "vertical",
        tick_count: int = 5,
        text_size: float = 0.025,
        name: str = "Legend",
    ) -> str:
        """
        Create a world-space color-bar legend for a scalar field.

        Parameters:
        - vmin, vmax: Value range (should match a prior bake_scalar_field_to_colors).
        - units: Suffix on the tick labels (e.g. "K", "°C", "MPa", "W").
        - colormap: Must match the colormap used when baking, or the colors will
                    not correspond to the rendered field.
        - position: JSON 3-tuple — world-space position of the bar's low-value end.
        - length, width: Physical dimensions of the bar (scene units).
        - orientation: "vertical" (low at bottom) or "horizontal" (low at left).
        - tick_count: Number of labeled ticks.
        - text_size: World-size of tick labels.
        """
        cmap = _colormap_literal(colormap)
        body = textwrap.dedent(f'''
            import json as _json, mathutils
            pos = mathutils.Vector(_json.loads({position!r}))
            L, W = {length!r}, {width!r}
            orient = {orientation!r}
            stops = {cmap}
            vmn, vmx = {vmin!r}, {vmax!r}

            # Build a subdivided plane to paint the gradient on
            if orient == "vertical":
                bpy.ops.mesh.primitive_plane_add(size=1, location=pos + mathutils.Vector((W/2, 0, L/2)))
                bar = bpy.context.active_object
                bar.scale = (W, 0.001, L); bpy.ops.object.transform_apply(scale=True)
                axis_key = "Z"
            else:
                bpy.ops.mesh.primitive_plane_add(size=1, location=pos + mathutils.Vector((L/2, 0, W/2)))
                bar = bpy.context.active_object
                bar.scale = (L, 0.001, W); bpy.ops.object.transform_apply(scale=True)
                axis_key = "X"
            bar.name = {name!r} + "_bar"

            # Subdivide along the long axis for smooth color
            bpy.context.view_layer.objects.active = bar
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            for _ in range(6):
                bpy.ops.mesh.subdivide(number_cuts=1)
            bpy.ops.object.mode_set(mode="OBJECT")

            def _colorize(t):
                t = max(0.0, min(1.0, t))
                p = t * (len(stops) - 1); i0 = int(p); i1 = min(len(stops) - 1, i0 + 1); f = p - i0
                return (
                    stops[i0][0]*(1-f) + stops[i1][0]*f,
                    stops[i0][1]*(1-f) + stops[i1][1]*f,
                    stops[i0][2]*(1-f) + stops[i1][2]*f,
                    1.0,
                )

            # Determine long-axis local extent (after scale apply, coords are world)
            # Find local min/max along the chosen axis
            coords = [v.co[{{"X":0, "Z":2}}[axis_key]] for v in bar.data.vertices]
            lo, hi = min(coords), max(coords)
            ca = bar.data.color_attributes.get("Legend") or bar.data.color_attributes.new(
                name="Legend", type="FLOAT_COLOR", domain="POINT")
            for i, v in enumerate(bar.data.vertices):
                t = (v.co[{{"X":0, "Z":2}}[axis_key]] - lo) / (hi - lo) if hi > lo else 0.0
                ca.data[i].color = _colorize(t)
            ca.active = True

            # Material using the color attribute
            mat = bpy.data.materials.new({name!r} + "_mat"); mat.use_nodes = True
            nt = mat.node_tree
            for n in list(nt.nodes): nt.nodes.remove(n)
            out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (400, 0)
            emit = nt.nodes.new("ShaderNodeEmission"); emit.location = (100, 0)
            ca_node = nt.nodes.new("ShaderNodeVertexColor"); ca_node.location = (-200, 0)
            ca_node.layer_name = "Legend"
            nt.links.new(ca_node.outputs["Color"], emit.inputs["Color"])
            nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
            bar.data.materials.append(mat)

            # Tick labels
            n = max(2, int({tick_count!r}))
            created_texts = []
            for i in range(n):
                t = i / (n - 1)
                val = vmn + t * (vmx - vmn)
                if orient == "vertical":
                    tp = pos + mathutils.Vector((W + {text_size!r}, 0, L * t))
                else:
                    tp = pos + mathutils.Vector((L * t, 0, W + {text_size!r}))
                td = bpy.data.curves.new(f"_legend_tick_{{i}}", type="FONT")
                td.body = f"{{val:.2f}} {{{units!r}}}"; td.size = {text_size!r}
                td.align_x = "LEFT" if orient == "vertical" else "CENTER"
                td.align_y = "CENTER"
                to = bpy.data.objects.new(f"{{{name!r}}}_tick_{{i}}", td)
                to.location = tp
                bpy.context.collection.objects.link(to)
                created_texts.append(to.name)

            _emit({{
                "bar": bar.name,
                "tick_labels": created_texts,
                "vmin": vmn, "vmax": vmx,
                "units": {units!r}, "colormap": {colormap!r},
                "orientation": orient,
            }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def add_section_view(
        ctx: Context,
        target_object: str,
        plane_origin: str = "[0,0,0]",
        plane_normal: str = "[1,0,0]",
        apply: bool = False,
        cap_material_id: str = "",
        name: str = "SectionCutter",
    ) -> str:
        """
        Add a half-space clipping modifier to `target_object`: everything on the
        +normal side of the plane is removed.

        Parameters:
        - target_object: Object to cut.
        - plane_origin: JSON 3-tuple — a point on the cutting plane.
        - plane_normal: JSON 3-tuple — plane normal. The half-space on the
                        +normal side is removed.
        - apply: If True, apply the modifier (destructive, no undo).
                 If False (default), leaves the modifier on the stack so you
                 can toggle or delete it later.
        - cap_material_id: If non-empty and `apply=True`, creates a simple flat
                           material with that name and assigns it to the cap
                           faces (best-effort — depends on boolean clean-up).
        """
        body = textwrap.dedent(f'''
            import json as _json, mathutils
            obj = bpy.data.objects.get({target_object!r})
            if obj is None:
                _emit({{"error": f"target_object {{{target_object!r}}} not found"}}); raise SystemExit

            origin = mathutils.Vector(_json.loads({plane_origin!r}))
            normal = mathutils.Vector(_json.loads({plane_normal!r})).normalized()

            # Build a large cube covering the +normal half-space.
            # Size it from the target's bounding diagonal × 4.
            bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
            diag = (bb[0] - bb[6]).length
            box_size = diag * 4 + 1

            bpy.ops.mesh.primitive_cube_add(size=box_size, location=(0,0,0))
            cutter = bpy.context.active_object
            cutter.name = {name!r}
            # Translate cutter so its -normal face passes through origin
            cutter.location = origin + normal * (box_size / 2)
            # Rotate cutter so its local +X aligns with plane_normal
            up = mathutils.Vector((0, 0, 1))
            if abs(normal.dot(up)) > 0.999:
                up = mathutils.Vector((0, 1, 0))
            right = normal
            forward = up.cross(right).normalized()
            up2 = right.cross(forward).normalized()
            mat = mathutils.Matrix((
                (right.x, up2.x, forward.x, 0),
                (right.y, up2.y, forward.y, 0),
                (right.z, up2.z, forward.z, 0),
                (0,0,0,1),
            )).transposed()
            cutter.rotation_euler = mat.to_euler()
            cutter.display_type = "WIRE"
            cutter.hide_render = True

            bpy.context.view_layer.objects.active = obj
            mod = obj.modifiers.new(name="SectionCut", type="BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.object = cutter
            mod.solver = "EXACT"

            applied_info = None
            if {apply!r}:
                bpy.ops.object.modifier_apply(modifier=mod.name)
                bpy.data.objects.remove(cutter, do_unlink=True)
                cutter = None
                # Cap material (best-effort)
                if {cap_material_id!r}:
                    cap_mat = bpy.data.materials.get({cap_material_id!r})
                    if cap_mat is None:
                        cap_mat = bpy.data.materials.new({cap_material_id!r})
                        cap_mat.use_nodes = True
                    if cap_mat.name not in (m.name for m in obj.data.materials):
                        obj.data.materials.append(cap_mat)
                    applied_info = {{"cap_material": cap_mat.name}}

            _emit({{
                "object": obj.name,
                "modifier": None if {apply!r} else mod.name,
                "cutter": cutter.name if cutter else None,
                "applied": {apply!r},
                "info": applied_info,
            }})
        ''').strip()
        return _dispatch(body)
