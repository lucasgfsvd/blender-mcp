"""
Engineering views, dimensions, and annotations.

Tools for producing report figures from a scene:

- render_views: orthographic front/top/right/iso renders at fixed frames
- add_dimension: linear dimension between two world points with offset + text
- label_components: callout text with leader lines for named objects
- add_scale_bar: world-space scale bar with tick labels
"""

import json
import os
import textwrap

from mcp.server.fastmcp import FastMCP, Context


def register(mcp: FastMCP) -> None:
    from blender_mcp.server import _run_in_blender, _snippet_header

    def _dispatch(body: str) -> str:
        return json.dumps(_run_in_blender(_snippet_header() + body), indent=2)

    @mcp.tool()
    def render_views(
        ctx: Context,
        output_dir: str,
        target_object: str = "",
        views: str = "front,top,right,iso",
        width: int = 1920,
        height: int = 1080,
        samples: int = 64,
        engine: str = "BLENDER_EEVEE_NEXT",
        margin: float = 1.3,
        transparent_bg: bool = True,
        filename_prefix: str = "view",
    ) -> str:
        """
        Render multiple orthographic views of the scene (or a specific object)
        to PNG files. Automatically frames the target.

        Parameters:
        - output_dir: Absolute path to the output directory. Created if missing.
        - target_object: Object to frame. Empty = frame the whole visible scene.
        - views: Comma-separated subset of: front, back, left, right, top,
                 bottom, iso (+X+Y+Z), iso_back (-X-Y+Z).
        - width, height: Render resolution in pixels.
        - samples: Render samples (Cycles) or AA samples (EEVEE Next).
        - engine: "BLENDER_EEVEE_NEXT" (default) or "CYCLES".
        - margin: Frame-fit padding (1.0 = tight). Default 1.3.
        - transparent_bg: Film alpha off → transparent PNG background.
        - filename_prefix: Output filename stem (appended with view name).

        Returns list of rendered filepaths.
        """
        # Normalize path for the generated code (JSON-safe string literal).
        out_dir = os.path.abspath(output_dir)
        body = textwrap.dedent(f'''
            import math, os, mathutils
            os.makedirs({out_dir!r}, exist_ok=True)

            views_raw = [v.strip() for v in {views!r}.split(",") if v.strip()]
            target_name = {target_object!r}

            # Compute bounding box center and radius
            if target_name:
                target = bpy.data.objects.get(target_name)
                if target is None:
                    _emit({{"error": f"target_object {{target_name!r}} not found"}})
                    raise SystemExit
                verts_world = [target.matrix_world @ mathutils.Vector(corner) for corner in target.bound_box]
            else:
                verts_world = []
                for o in bpy.context.visible_objects:
                    if o.type != "MESH":
                        continue
                    verts_world += [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
                if not verts_world:
                    _emit({{"error": "no visible mesh objects to frame"}})
                    raise SystemExit
            xs = [v.x for v in verts_world]
            ys = [v.y for v in verts_world]
            zs = [v.z for v in verts_world]
            bbmin = mathutils.Vector((min(xs), min(ys), min(zs)))
            bbmax = mathutils.Vector((max(xs), max(ys), max(zs)))
            center = (bbmin + bbmax) / 2
            extent = (bbmax - bbmin) * {margin!r}

            # Create / reuse a camera
            cam_data = bpy.data.cameras.get("_EngView_Cam") or bpy.data.cameras.new("_EngView_Cam")
            cam_data.type = "ORTHO"
            cam_obj = bpy.data.objects.get("_EngView_CamObj")
            if cam_obj is None:
                cam_obj = bpy.data.objects.new("_EngView_CamObj", cam_data)
                bpy.context.collection.objects.link(cam_obj)
            else:
                cam_obj.data = cam_data
            scene = bpy.context.scene
            prev_cam = scene.camera
            scene.camera = cam_obj

            # Render settings
            prev = {{
                "engine": scene.render.engine,
                "resx": scene.render.resolution_x,
                "resy": scene.render.resolution_y,
                "film": scene.render.film_transparent,
                "filepath": scene.render.filepath,
            }}
            scene.render.engine = {engine!r}
            scene.render.resolution_x = int({width!r})
            scene.render.resolution_y = int({height!r})
            scene.render.film_transparent = {transparent_bg!r}
            if scene.render.engine == "CYCLES":
                scene.cycles.samples = int({samples!r})
            elif scene.render.engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
                # Some versions use taa_render_samples, some use just samples
                eevee = getattr(scene, "eevee", None)
                if eevee is not None and hasattr(eevee, "taa_render_samples"):
                    eevee.taa_render_samples = int({samples!r})

            # View directions: (name, camera_location_dir, up)
            aspect = {width!r} / max(1, {height!r})
            views_map = {{
                "front":    mathutils.Vector((0, -1, 0)),
                "back":     mathutils.Vector((0,  1, 0)),
                "right":    mathutils.Vector((1,  0, 0)),
                "left":     mathutils.Vector((-1, 0, 0)),
                "top":      mathutils.Vector((0,  0, 1)),
                "bottom":   mathutils.Vector((0,  0, -1)),
                "iso":      mathutils.Vector((1,  1, 1)).normalized(),
                "iso_back": mathutils.Vector((-1,-1, 1)).normalized(),
            }}
            rendered = []
            for vname in views_raw:
                if vname not in views_map:
                    continue
                direction = views_map[vname]
                # Place camera 10× the largest extent away along direction
                dist = max(extent.x, extent.y, extent.z) * 10 + 1
                cam_obj.location = center + direction * dist
                # Point camera at center — use track_to logic manually
                look = (center - cam_obj.location).normalized()
                # Compute rotation: camera's default looks -Z, up +Y
                up = mathutils.Vector((0, 0, 1))
                if abs(look.dot(up)) > 0.999:
                    up = mathutils.Vector((0, 1, 0))
                right = look.cross(up).normalized()
                up_corrected = right.cross(look).normalized()
                mat = mathutils.Matrix((
                    (right.x, up_corrected.x, -look.x, 0),
                    (right.y, up_corrected.y, -look.y, 0),
                    (right.z, up_corrected.z, -look.z, 0),
                    (0, 0, 0, 1),
                )).transposed()
                cam_obj.rotation_euler = mat.to_euler()
                # Fit orthographic scale to bounding extent (max of horizontal extent)
                # For top/bottom: X,Y; for front/back: X,Z; etc. Use max to be safe.
                h_extent = max(extent.x, extent.y, extent.z)
                cam_data.ortho_scale = h_extent * max(1, aspect)
                # Render
                fp = os.path.join({out_dir!r}, f"{filename_prefix!r}_{{vname}}.png")
                scene.render.filepath = fp
                bpy.ops.render.render(write_still=True)
                rendered.append(fp)

            # Restore previous settings
            scene.camera = prev_cam
            scene.render.engine = prev["engine"]
            scene.render.resolution_x = prev["resx"]
            scene.render.resolution_y = prev["resy"]
            scene.render.film_transparent = prev["film"]
            scene.render.filepath = prev["filepath"]

            _emit({{"rendered": rendered, "views": views_raw}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def add_dimension(
        ctx: Context,
        point_a: str = "[0,0,0]",
        point_b: str = "[1,0,0]",
        offset: float = 0.05,
        offset_direction: str = "auto",
        units: str = "mm",
        text_size: float = 0.02,
        name: str = "Dim",
    ) -> str:
        """
        Add a linear dimension annotation between two world-space points.
        Draws a parallel line offset from A-B with a text label showing the
        distance in the chosen units.

        Parameters:
        - point_a, point_b: JSON 3-tuples in scene units (meters).
        - offset: Perpendicular offset of the dimension line, in scene units.
        - offset_direction: "auto" (perpendicular to A-B in XY plane) or a
                            JSON 3-tuple giving the direction.
        - units: "mm" | "cm" | "m" | "in". Display unit for the label.
        - text_size: World-size of the text label (scene units).

        Returns name of the created dimension group.
        """
        body = textwrap.dedent(f'''
            import json as _json, math, mathutils
            A = mathutils.Vector(_json.loads({point_a!r}))
            B = mathutils.Vector(_json.loads({point_b!r}))
            off = {offset!r}
            off_dir_s = {offset_direction!r}
            units = {units!r}
            if off_dir_s == "auto":
                along = (B - A).normalized()
                up = mathutils.Vector((0, 0, 1))
                perp = along.cross(up)
                if perp.length < 1e-6:
                    perp = along.cross(mathutils.Vector((0, 1, 0)))
                perp.normalize()
            else:
                perp = mathutils.Vector(_json.loads(off_dir_s)).normalized()
            A2, B2 = A + perp * off, B + perp * off
            dist_m = (B - A).length
            unit_scale = {{"mm": 1000.0, "cm": 100.0, "m": 1.0, "in": 39.3701}}.get(units, 1000.0)
            label_val = dist_m * unit_scale
            label = f"{{label_val:.2f}} {{units}}"

            # Dimension line (curve)
            cd = bpy.data.curves.new("_dim_line", type="CURVE")
            cd.dimensions = "3D"
            sp = cd.splines.new("POLY"); sp.points.add(3)
            sp.points[0].co = (A.x, A.y, A.z, 1)
            sp.points[1].co = (A2.x, A2.y, A2.z, 1)
            sp.points[2].co = (B2.x, B2.y, B2.z, 1)
            sp.points[3].co = (B.x, B.y, B.z, 1)
            line_obj = bpy.data.objects.new({name!r} + "_line", cd)
            bpy.context.collection.objects.link(line_obj)

            # Text at midpoint
            td = bpy.data.curves.new("_dim_text", type="FONT")
            td.body = label
            td.size = {text_size!r}
            td.align_x = "CENTER"; td.align_y = "CENTER"
            text_obj = bpy.data.objects.new({name!r} + "_text", td)
            midpoint = (A2 + B2) / 2 + perp * ({text_size!r} * 0.8)
            text_obj.location = midpoint
            # Orient text in plane of dim line, facing +perp
            along = (B - A).normalized()
            normal = along.cross(perp)
            if normal.length > 1e-6:
                mat = mathutils.Matrix((
                    (along.x, perp.x, normal.x, 0),
                    (along.y, perp.y, normal.y, 0),
                    (along.z, perp.z, normal.z, 0),
                    (0, 0, 0, 1),
                )).transposed()
                text_obj.rotation_euler = mat.to_euler()
            bpy.context.collection.objects.link(text_obj)

            _emit({{
                "line": line_obj.name,
                "text": text_obj.name,
                "distance_m": dist_m,
                "label": label,
            }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def label_components(
        ctx: Context,
        mapping: str = '{"Cube": "Heat Spreader"}',
        text_size: float = 0.03,
        offset: float = 0.1,
        offset_direction: str = "[0,0,1]",
    ) -> str:
        """
        Add world-space callout labels to a set of objects, with leader lines.

        Parameters:
        - mapping: JSON object {object_name: label_text}.
        - text_size: World-size of each text label.
        - offset: Distance from object center to place the text.
        - offset_direction: JSON 3-tuple direction (world space) for label offset.
        """
        body = textwrap.dedent(f'''
            import json as _json, mathutils
            mapping = _json.loads({mapping!r})
            ts = {text_size!r}
            off = {offset!r}
            direction = mathutils.Vector(_json.loads({offset_direction!r})).normalized()

            created = []
            for obj_name, label_text in mapping.items():
                obj = bpy.data.objects.get(obj_name)
                if obj is None:
                    continue
                # Object center via bound box
                center = sum((obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box),
                             mathutils.Vector()) / 8
                label_pos = center + direction * off

                # Leader line
                cd = bpy.data.curves.new(f"_leader_{{obj_name}}", type="CURVE")
                cd.dimensions = "3D"
                sp = cd.splines.new("POLY"); sp.points.add(1)
                sp.points[0].co = (center.x, center.y, center.z, 1)
                sp.points[1].co = (label_pos.x, label_pos.y, label_pos.z, 1)
                leader = bpy.data.objects.new(f"Label_{{obj_name}}_leader", cd)
                bpy.context.collection.objects.link(leader)

                # Text
                td = bpy.data.curves.new(f"_labeltxt_{{obj_name}}", type="FONT")
                td.body = label_text; td.size = ts
                td.align_x = "CENTER"; td.align_y = "CENTER"
                text_obj = bpy.data.objects.new(f"Label_{{obj_name}}_text", td)
                text_obj.location = label_pos + direction * (ts * 0.8)
                bpy.context.collection.objects.link(text_obj)

                created.append({{"object": obj_name, "leader": leader.name, "text": text_obj.name}})

            _emit({{"created": created, "count": len(created)}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def add_scale_bar(
        ctx: Context,
        length_mm: float = 100.0,
        position: str = "[0,0,0]",
        direction: str = "[1,0,0]",
        tick_count: int = 5,
        text_size: float = 0.02,
        units: str = "mm",
        name: str = "ScaleBar",
    ) -> str:
        """
        World-space scale bar with tick marks and an end label showing length
        in the chosen units.

        Parameters:
        - length_mm: Overall bar length in millimeters.
        - position: JSON 3-tuple for the bar's start point.
        - direction: JSON 3-tuple direction of the bar.
        - tick_count: Number of tick marks (including endpoints).
        - units: "mm" | "cm" | "m" | "in".
        """
        body = textwrap.dedent(f'''
            import json as _json, mathutils
            L = {length_mm!r}/1000
            start = mathutils.Vector(_json.loads({position!r}))
            dirv = mathutils.Vector(_json.loads({direction!r})).normalized()
            up = mathutils.Vector((0, 0, 1))
            perp = dirv.cross(up)
            if perp.length < 1e-6: perp = dirv.cross(mathutils.Vector((0,1,0)))
            perp.normalize()
            tick_size = L * 0.05
            n = max(2, int({tick_count!r}))

            cd = bpy.data.curves.new("_scalebar", type="CURVE")
            cd.dimensions = "3D"
            # Main bar
            sp = cd.splines.new("POLY"); sp.points.add(1)
            sp.points[0].co = (start.x, start.y, start.z, 1)
            end = start + dirv * L
            sp.points[1].co = (end.x, end.y, end.z, 1)
            # Ticks
            for i in range(n):
                t = i / (n - 1)
                p = start + dirv * (L * t)
                t0 = p - perp * tick_size
                t1 = p + perp * tick_size
                tsp = cd.splines.new("POLY"); tsp.points.add(1)
                tsp.points[0].co = (t0.x, t0.y, t0.z, 1)
                tsp.points[1].co = (t1.x, t1.y, t1.z, 1)
            bar_obj = bpy.data.objects.new({name!r} + "_bar", cd)
            bpy.context.collection.objects.link(bar_obj)

            unit_scale = {{"mm": 1000.0, "cm": 100.0, "m": 1.0, "in": 39.3701}}.get({units!r}, 1000.0)
            label = f"{{L * unit_scale:.0f}} {{{units!r}}}"
            td = bpy.data.curves.new("_scalebar_text", type="FONT")
            td.body = label; td.size = {text_size!r}
            td.align_x = "CENTER"; td.align_y = "TOP"
            text_obj = bpy.data.objects.new({name!r} + "_text", td)
            text_obj.location = start + dirv * (L/2) + perp * (tick_size * 2)
            bpy.context.collection.objects.link(text_obj)
            _emit({{"bar": bar_obj.name, "text": text_obj.name, "length_m": L, "label": label}})
        ''').strip()
        return _dispatch(body)
