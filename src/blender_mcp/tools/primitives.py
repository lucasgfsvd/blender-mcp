"""
Parametric engineering primitives.

Two groups:

- Mechanical: slotted/perforated plates, brackets, channels, rounded boxes,
  bolt-hole patterns, swept tubes, truss nodes.
- Aerospace: cylindrical/spherical tanks, cones (frustums), tori, satellite
  buses, cubesats, rover chassis, lander legs, planetary terrain patches.

All dimensions are in scene units (meters by default, matching Blender's
defaults). Where engineers typically think in millimeters, params are named
with the unit in the argument name (e.g. `length_mm`) and converted
internally.
"""

import json
import textwrap

from mcp.server.fastmcp import FastMCP, Context


def register(mcp: FastMCP) -> None:
    """Register all parametric primitive tools on the given FastMCP instance."""
    from blender_mcp.server import _run_in_blender, _snippet_header

    def _dispatch(body: str) -> str:
        return json.dumps(_run_in_blender(_snippet_header() + body), indent=2)

    # ─────────────────────────────────────────────────────────────────────
    # MECHANICAL
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def slotted_plate(
        ctx: Context,
        length_mm: float = 100.0,
        width_mm: float = 60.0,
        thickness_mm: float = 3.0,
        slot_length_mm: float = 20.0,
        slot_width_mm: float = 5.0,
        slot_count: int = 3,
        slot_pitch_mm: float = 0.0,
        name: str = "SlottedPlate",
    ) -> str:
        """
        Create a rectangular plate with a linear array of oblong slots through
        its thickness. Slots run along the length direction.

        Parameters:
        - length_mm, width_mm, thickness_mm: plate dimensions.
        - slot_length_mm, slot_width_mm: individual slot footprint.
        - slot_count: number of slots (≥1).
        - slot_pitch_mm: center-to-center spacing. 0 (default) auto-spaces
                         uniformly across length.
        """
        body = textwrap.dedent(f'''
            import bmesh
            L, W, T = {length_mm!r}/1000, {width_mm!r}/1000, {thickness_mm!r}/1000
            sL, sW = {slot_length_mm!r}/1000, {slot_width_mm!r}/1000
            n = max(1, int({slot_count!r}))
            pitch = {slot_pitch_mm!r}/1000
            if pitch <= 0:
                pitch = L / (n + 1)

            # Base plate
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,0))
            plate = bpy.context.active_object
            plate.name = {name!r}
            plate.scale = (L, W, T)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            # Slot cutters
            cutters = []
            x0 = -(n - 1) * pitch / 2
            for i in range(n):
                x = x0 + i * pitch
                bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0, 0))
                c = bpy.context.active_object
                c.name = f"_slot_{{i}}"
                c.scale = (sL, sW, T * 2)
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                cutters.append(c)

            # Boolean subtract each cutter
            bpy.context.view_layer.objects.active = plate
            for c in cutters:
                mod = plate.modifiers.new(name="bool", type="BOOLEAN")
                mod.operation = "DIFFERENCE"
                mod.object = c
                bpy.ops.object.modifier_apply(modifier=mod.name)
                bpy.data.objects.remove(c, do_unlink=True)

            _emit({{"object": plate.name, "length_m": L, "width_m": W, "thickness_m": T, "slots": n}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def perforated_plate(
        ctx: Context,
        length_mm: float = 100.0,
        width_mm: float = 100.0,
        thickness_mm: float = 2.0,
        hole_diameter_mm: float = 5.0,
        pitch_x_mm: float = 10.0,
        pitch_y_mm: float = 10.0,
        pattern: str = "square",
        name: str = "PerfPlate",
    ) -> str:
        """
        Rectangular plate with a grid of circular holes through thickness.

        Parameters:
        - pattern: "square" (grid) or "staggered" (offset every other row).
        """
        body = textwrap.dedent(f'''
            import math
            L, W, T = {length_mm!r}/1000, {width_mm!r}/1000, {thickness_mm!r}/1000
            d = {hole_diameter_mm!r}/1000
            px, py = {pitch_x_mm!r}/1000, {pitch_y_mm!r}/1000
            pattern = {pattern!r}

            bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,0))
            plate = bpy.context.active_object
            plate.name = {name!r}
            plate.scale = (L, W, T)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            nx = max(1, int((L - d) / px))
            ny = max(1, int((W - d) / py))
            x0 = -(nx - 1) * px / 2
            y0 = -(ny - 1) * py / 2

            cutters = []
            for iy in range(ny):
                offset = (px / 2) if (pattern == "staggered" and iy % 2 == 1) else 0.0
                for ix in range(nx):
                    x = x0 + ix * px + offset
                    y = y0 + iy * py
                    if abs(x) + d/2 > L/2 or abs(y) + d/2 > W/2:
                        continue
                    bpy.ops.mesh.primitive_cylinder_add(radius=d/2, depth=T*2, location=(x, y, 0))
                    cutters.append(bpy.context.active_object)

            bpy.context.view_layer.objects.active = plate
            for c in cutters:
                mod = plate.modifiers.new(name="bool", type="BOOLEAN")
                mod.operation = "DIFFERENCE"
                mod.object = c
                bpy.ops.object.modifier_apply(modifier=mod.name)
            for c in cutters:
                bpy.data.objects.remove(c, do_unlink=True)
            _emit({{"object": plate.name, "holes": len(cutters), "pattern": pattern}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def l_bracket(
        ctx: Context,
        leg_a_mm: float = 50.0,
        leg_b_mm: float = 50.0,
        width_mm: float = 40.0,
        thickness_mm: float = 3.0,
        fillet_mm: float = 0.0,
        name: str = "LBracket",
    ) -> str:
        """
        L-shaped bracket. Leg A runs along +X, leg B along +Z.
        Both legs share the same thickness and width (along Y).
        Optional inner-corner fillet.
        """
        body = textwrap.dedent(f'''
            a, b, w, t = ({leg_a_mm!r}/1000, {leg_b_mm!r}/1000,
                          {width_mm!r}/1000, {thickness_mm!r}/1000)
            f = {fillet_mm!r}/1000

            # Horizontal leg
            bpy.ops.mesh.primitive_cube_add(size=1, location=(a/2, 0, t/2))
            legA = bpy.context.active_object
            legA.scale = (a, w, t)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            # Vertical leg
            bpy.ops.mesh.primitive_cube_add(size=1, location=(t/2, 0, b/2))
            legB = bpy.context.active_object
            legB.scale = (t, w, b)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

            # Join
            bpy.ops.object.select_all(action="DESELECT")
            legA.select_set(True); legB.select_set(True)
            bpy.context.view_layer.objects.active = legA
            bpy.ops.object.join()
            obj = bpy.context.active_object
            obj.name = {name!r}

            # Weld coincident verts at the corner
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.remove_doubles(threshold=1e-6)
            bpy.ops.object.mode_set(mode="OBJECT")

            if f > 0:
                mod = obj.modifiers.new(name="Bevel", type="BEVEL")
                mod.width = f
                mod.segments = 6
                bpy.ops.object.modifier_apply(modifier=mod.name)

            _emit({{"object": obj.name, "leg_a_m": a, "leg_b_m": b, "width_m": w, "thickness_m": t, "fillet_m": f}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def t_bracket(
        ctx: Context,
        crossbar_mm: float = 80.0,
        stem_mm: float = 50.0,
        width_mm: float = 40.0,
        thickness_mm: float = 3.0,
        name: str = "TBracket",
    ) -> str:
        """T-shaped bracket: crossbar along X, stem along +Z."""
        body = textwrap.dedent(f'''
            cb, st, w, t = ({crossbar_mm!r}/1000, {stem_mm!r}/1000,
                            {width_mm!r}/1000, {thickness_mm!r}/1000)

            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, t/2))
            bar = bpy.context.active_object
            bar.scale = (cb, w, t); bpy.ops.object.transform_apply(scale=True)

            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, t + st/2))
            stem = bpy.context.active_object
            stem.scale = (t, w, st); bpy.ops.object.transform_apply(scale=True)

            bpy.ops.object.select_all(action="DESELECT")
            bar.select_set(True); stem.select_set(True)
            bpy.context.view_layer.objects.active = bar
            bpy.ops.object.join()
            obj = bpy.context.active_object
            obj.name = {name!r}
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.remove_doubles(threshold=1e-6)
            bpy.ops.object.mode_set(mode="OBJECT")
            _emit({{"object": obj.name, "crossbar_m": cb, "stem_m": st}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def u_channel(
        ctx: Context,
        length_mm: float = 200.0,
        height_mm: float = 40.0,
        width_mm: float = 40.0,
        thickness_mm: float = 2.0,
        name: str = "UChannel",
    ) -> str:
        """
        U-shaped channel (three-sided cross-section) extruded along X.
        Width runs along Y, height along Z, opening at +Z.
        """
        body = textwrap.dedent(f'''
            L, H, W, t = ({length_mm!r}/1000, {height_mm!r}/1000,
                          {width_mm!r}/1000, {thickness_mm!r}/1000)

            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, t/2))
            bot = bpy.context.active_object
            bot.scale = (L, W, t); bpy.ops.object.transform_apply(scale=True)

            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -(W-t)/2, H/2))
            wL = bpy.context.active_object
            wL.scale = (L, t, H); bpy.ops.object.transform_apply(scale=True)

            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, (W-t)/2, H/2))
            wR = bpy.context.active_object
            wR.scale = (L, t, H); bpy.ops.object.transform_apply(scale=True)

            bpy.ops.object.select_all(action="DESELECT")
            for o in (bot, wL, wR): o.select_set(True)
            bpy.context.view_layer.objects.active = bot
            bpy.ops.object.join()
            obj = bpy.context.active_object
            obj.name = {name!r}
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.remove_doubles(threshold=1e-6)
            bpy.ops.object.mode_set(mode="OBJECT")
            _emit({{"object": obj.name, "length_m": L, "height_m": H, "width_m": W, "thickness_m": t}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def rounded_box(
        ctx: Context,
        length_mm: float = 100.0,
        width_mm: float = 60.0,
        height_mm: float = 40.0,
        fillet_mm: float = 5.0,
        segments: int = 6,
        name: str = "RoundedBox",
    ) -> str:
        """Box with filleted (beveled) edges — common enclosure shape."""
        body = textwrap.dedent(f'''
            L, W, H = {length_mm!r}/1000, {width_mm!r}/1000, {height_mm!r}/1000
            f = {fillet_mm!r}/1000
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
            obj = bpy.context.active_object
            obj.name = {name!r}
            obj.scale = (L, W, H); bpy.ops.object.transform_apply(scale=True)
            mod = obj.modifiers.new(name="Bevel", type="BEVEL")
            mod.width = f; mod.segments = int({segments!r})
            bpy.ops.object.modifier_apply(modifier=mod.name)
            _emit({{"object": obj.name, "L_m": L, "W_m": W, "H_m": H, "fillet_m": f}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def bolt_hole_pattern(
        ctx: Context,
        object_name: str,
        pattern: str = "pcd",
        pcd_diameter_mm: float = 80.0,
        hole_count: int = 4,
        hole_diameter_mm: float = 4.2,
        grid_rows: int = 2,
        grid_cols: int = 2,
        grid_pitch_x_mm: float = 50.0,
        grid_pitch_y_mm: float = 50.0,
        axis: str = "Z",
    ) -> str:
        """
        Boolean-subtract a bolt-hole pattern through an existing object.
        Drills along the chosen axis.

        Parameters:
        - pattern: "pcd" (pitch-circle diameter) or "grid".
        - axis: "X", "Y", or "Z" — the axis the holes run along.
        """
        body = textwrap.dedent(f'''
            import math
            obj = bpy.data.objects.get({object_name!r})
            if obj is None:
                _emit({{"error": f"object {object_name!r} not found"}}); raise SystemExit
            pattern = {pattern!r}
            axis = {axis!r}
            d = {hole_diameter_mm!r}/1000
            # Long enough cylinder to punch through any reasonable part
            depth = max(obj.dimensions) * 4 + 0.1

            def _cyl(x, y, z):
                bpy.ops.mesh.primitive_cylinder_add(radius=d/2, depth=depth, location=(x, y, z))
                c = bpy.context.active_object
                if axis == "X":
                    c.rotation_euler = (0, math.radians(90), 0)
                elif axis == "Y":
                    c.rotation_euler = (math.radians(90), 0, 0)
                bpy.ops.object.transform_apply(rotation=True)
                return c

            cutters = []
            if pattern == "pcd":
                r = {pcd_diameter_mm!r}/1000 / 2
                n = max(1, int({hole_count!r}))
                for i in range(n):
                    ang = 2 * math.pi * i / n
                    if axis == "Z":
                        cutters.append(_cyl(r*math.cos(ang), r*math.sin(ang), 0))
                    elif axis == "Y":
                        cutters.append(_cyl(r*math.cos(ang), 0, r*math.sin(ang)))
                    else:
                        cutters.append(_cyl(0, r*math.cos(ang), r*math.sin(ang)))
            elif pattern == "grid":
                nx, ny = int({grid_cols!r}), int({grid_rows!r})
                px, py = {grid_pitch_x_mm!r}/1000, {grid_pitch_y_mm!r}/1000
                x0, y0 = -(nx-1)*px/2, -(ny-1)*py/2
                for iy in range(ny):
                    for ix in range(nx):
                        x, y = x0 + ix*px, y0 + iy*py
                        if axis == "Z":
                            cutters.append(_cyl(x, y, 0))
                        elif axis == "Y":
                            cutters.append(_cyl(x, 0, y))
                        else:
                            cutters.append(_cyl(0, x, y))
            else:
                _emit({{"error": f"unknown pattern {{pattern!r}}"}}); raise SystemExit

            bpy.context.view_layer.objects.active = obj
            for c in cutters:
                mod = obj.modifiers.new(name="bool", type="BOOLEAN")
                mod.operation = "DIFFERENCE"; mod.object = c
                bpy.ops.object.modifier_apply(modifier=mod.name)
            for c in cutters:
                bpy.data.objects.remove(c, do_unlink=True)
            _emit({{"object": obj.name, "holes_drilled": len(cutters), "pattern": pattern, "axis": axis}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def swept_tube(
        ctx: Context,
        points: str = "[[0,0,0],[0.1,0,0],[0.1,0.1,0],[0.1,0.1,0.1]]",
        outer_diameter_mm: float = 10.0,
        wall_thickness_mm: float = 1.0,
        bevel_resolution: int = 12,
        name: str = "Tube",
    ) -> str:
        """
        Swept tube along a polyline path (list of [x,y,z] points in meters).
        Hollow if wall_thickness_mm < half the outer diameter.

        Parameters:
        - points: JSON list of 3-tuples in meters, e.g. "[[0,0,0],[1,0,0],[1,1,0]]".
        """
        body = textwrap.dedent(f'''
            import json as _json
            pts = _json.loads({points!r})
            od, wt = {outer_diameter_mm!r}/1000, {wall_thickness_mm!r}/1000
            # Build a curve
            cd = bpy.data.curves.new("_tube_path", type="CURVE")
            cd.dimensions = "3D"
            sp = cd.splines.new("POLY")
            sp.points.add(len(pts) - 1)
            for i, p in enumerate(pts):
                sp.points[i].co = (p[0], p[1], p[2], 1.0)
            obj = bpy.data.objects.new({name!r}, cd)
            bpy.context.collection.objects.link(obj)
            cd.bevel_depth = od / 2
            cd.bevel_resolution = int({bevel_resolution!r})
            # Convert curve to mesh so we can optionally hollow it
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.convert(target="MESH")
            obj = bpy.context.active_object
            if wt > 0 and wt < od/2:
                mod = obj.modifiers.new(name="Solidify", type="SOLIDIFY")
                mod.thickness = -wt  # inward
                mod.offset = 1
                bpy.ops.object.modifier_apply(modifier=mod.name)
            _emit({{"object": obj.name, "points": len(pts), "outer_d_m": od, "wall_m": wt}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def truss_node(
        ctx: Context,
        directions: str = "[[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]]",
        strut_length_mm: float = 100.0,
        strut_diameter_mm: float = 8.0,
        hub_diameter_mm: float = 15.0,
        name: str = "TrussNode",
    ) -> str:
        """
        Spherical hub with cylindrical struts radiating along given direction
        vectors. Useful for space-frame / spherical-truss assemblies.

        Parameters:
        - directions: JSON list of 3-vectors (need not be unit). Each becomes one strut.
        """
        body = textwrap.dedent(f'''
            import math, json as _json, mathutils
            dirs = _json.loads({directions!r})
            L = {strut_length_mm!r}/1000
            d = {strut_diameter_mm!r}/1000
            hd = {hub_diameter_mm!r}/1000
            bpy.ops.mesh.primitive_uv_sphere_add(radius=hd/2, location=(0,0,0))
            hub = bpy.context.active_object
            hub.name = {name!r}
            parts = [hub]
            for v in dirs:
                vec = mathutils.Vector(v)
                if vec.length == 0:
                    continue
                vec.normalize()
                bpy.ops.mesh.primitive_cylinder_add(radius=d/2, depth=L, location=(0,0,0))
                st = bpy.context.active_object
                # Align cylinder (default along +Z) with vec
                up = mathutils.Vector((0, 0, 1))
                rot = up.rotation_difference(vec).to_euler()
                st.rotation_euler = rot
                st.location = vec * (L/2)
                bpy.ops.object.transform_apply(location=True, rotation=True)
                parts.append(st)
            bpy.ops.object.select_all(action="DESELECT")
            for p in parts: p.select_set(True)
            bpy.context.view_layer.objects.active = hub
            bpy.ops.object.join()
            obj = bpy.context.active_object
            obj.name = {name!r}
            _emit({{"object": obj.name, "struts": len(dirs)}})
        ''').strip()
        return _dispatch(body)

    # ─────────────────────────────────────────────────────────────────────
    # AEROSPACE
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def cylindrical_tank(
        ctx: Context,
        diameter_mm: float = 500.0,
        barrel_length_mm: float = 800.0,
        dome_type: str = "ellipsoidal",
        dome_aspect: float = 0.5,
        wall_thickness_mm: float = 3.0,
        segments: int = 64,
        name: str = "Tank",
    ) -> str:
        """
        Cylindrical pressure tank with domed caps.

        Parameters:
        - dome_type: "ellipsoidal" (k=dome_aspect, 0.5 = 2:1 ellipsoidal),
                     "hemispherical" (dome_aspect ignored),
                     "flat" (closed disk).
        - dome_aspect: dome height / tank radius for ellipsoidal. 0.5 = 2:1.
        - wall_thickness_mm: 0 = solid; >0 = hollow shell via Solidify.
        """
        body = textwrap.dedent(f'''
            import math
            r = {diameter_mm!r}/2000
            Lc = {barrel_length_mm!r}/1000
            dtype = {dome_type!r}
            k = {dome_aspect!r}
            wt = {wall_thickness_mm!r}/1000
            segs = int({segments!r})

            # Barrel
            bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=Lc, vertices=segs, location=(0,0,0), end_fill_type="NOTHING")
            barrel = bpy.context.active_object
            barrel.name = {name!r}

            def _dome(z_center, flip):
                if dtype == "flat":
                    bpy.ops.mesh.primitive_circle_add(radius=r, vertices=segs, fill_type="NGON", location=(0,0,z_center))
                    return bpy.context.active_object
                bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=segs, ring_count=max(8, segs//4), location=(0,0,z_center))
                d = bpy.context.active_object
                if dtype == "ellipsoidal":
                    d.scale = (1, 1, k * (-1 if flip else 1))
                else:  # hemispherical
                    d.scale = (1, 1, (-1 if flip else 1))
                bpy.ops.object.transform_apply(scale=True)
                # Keep only the hemisphere on the correct side
                bpy.ops.object.mode_set(mode="EDIT")
                import bmesh
                bm = bmesh.from_edit_mesh(d.data)
                for v in list(bm.verts):
                    if (not flip and v.co.z < z_center - 1e-9) or (flip and v.co.z > z_center + 1e-9):
                        bm.verts.remove(v)
                bmesh.update_edit_mesh(d.data)
                bpy.ops.object.mode_set(mode="OBJECT")
                return d

            top = _dome(Lc/2, flip=False)
            bot = _dome(-Lc/2, flip=True)

            bpy.ops.object.select_all(action="DESELECT")
            barrel.select_set(True); top.select_set(True); bot.select_set(True)
            bpy.context.view_layer.objects.active = barrel
            bpy.ops.object.join()
            obj = bpy.context.active_object
            obj.name = {name!r}

            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.remove_doubles(threshold=1e-5)
            bpy.ops.mesh.normals_make_consistent(inside=False)
            bpy.ops.object.mode_set(mode="OBJECT")

            if wt > 0:
                mod = obj.modifiers.new(name="Solidify", type="SOLIDIFY")
                mod.thickness = -wt; mod.offset = 1
                bpy.ops.object.modifier_apply(modifier=mod.name)

            _emit({{"object": obj.name, "radius_m": r, "barrel_length_m": Lc, "dome_type": dtype, "wall_m": wt}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def spherical_tank(
        ctx: Context,
        diameter_mm: float = 500.0,
        wall_thickness_mm: float = 3.0,
        segments: int = 64,
        name: str = "SphereTank",
    ) -> str:
        """Spherical pressure vessel. wall_thickness=0 → solid sphere."""
        body = textwrap.dedent(f'''
            r = {diameter_mm!r}/2000
            wt = {wall_thickness_mm!r}/1000
            bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=int({segments!r}), ring_count=int({segments!r})//2)
            obj = bpy.context.active_object
            obj.name = {name!r}
            if wt > 0:
                mod = obj.modifiers.new(name="Solidify", type="SOLIDIFY")
                mod.thickness = -wt; mod.offset = 1
                bpy.ops.object.modifier_apply(modifier=mod.name)
            _emit({{"object": obj.name, "radius_m": r, "wall_m": wt}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def cone_frustum(
        ctx: Context,
        radius_bottom_mm: float = 100.0,
        radius_top_mm: float = 50.0,
        height_mm: float = 200.0,
        segments: int = 64,
        cap: bool = True,
        wall_thickness_mm: float = 0.0,
        name: str = "Cone",
    ) -> str:
        """
        Cone frustum. radius_top=0 → full cone. wall_thickness>0 → hollow shell.
        """
        body = textwrap.dedent(f'''
            r1 = {radius_bottom_mm!r}/1000
            r2 = {radius_top_mm!r}/1000
            h = {height_mm!r}/1000
            wt = {wall_thickness_mm!r}/1000
            fill = "NGON" if {cap!r} else "NOTHING"
            bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=h,
                                            vertices=int({segments!r}), end_fill_type=fill)
            obj = bpy.context.active_object
            obj.name = {name!r}
            if wt > 0:
                mod = obj.modifiers.new(name="Solidify", type="SOLIDIFY")
                mod.thickness = -wt; mod.offset = 1
                bpy.ops.object.modifier_apply(modifier=mod.name)
            _emit({{"object": obj.name, "r_bot_m": r1, "r_top_m": r2, "height_m": h, "wall_m": wt}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def torus(
        ctx: Context,
        major_radius_mm: float = 200.0,
        minor_radius_mm: float = 30.0,
        major_segments: int = 64,
        minor_segments: int = 16,
        name: str = "Torus",
    ) -> str:
        """Torus. For square cross-sections, apply a Remesh afterwards."""
        body = textwrap.dedent(f'''
            R = {major_radius_mm!r}/1000
            r = {minor_radius_mm!r}/1000
            bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r,
                                             major_segments=int({major_segments!r}),
                                             minor_segments=int({minor_segments!r}))
            obj = bpy.context.active_object
            obj.name = {name!r}
            _emit({{"object": obj.name, "R_m": R, "r_m": r}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def satellite_bus(
        ctx: Context,
        length_mm: float = 1000.0,
        width_mm: float = 800.0,
        height_mm: float = 1200.0,
        wall_thickness_mm: float = 3.0,
        panel_thickness_mm: float = 25.0,
        include_solar_panels: bool = False,
        solar_panel_span_mm: float = 2000.0,
        solar_panel_width_mm: float = 800.0,
        name: str = "SatBus",
    ) -> str:
        """
        Rectangular satellite bus (six panel faces) with optional deployed
        solar wings along the +Y / -Y axes.

        Each face is a separate mesh panel with `panel_thickness_mm`; they are
        joined into one object so you can apply a material to the whole bus or
        use select_by_normal downstream to target individual panels.
        """
        body = textwrap.dedent(f'''
            L, W, H = {length_mm!r}/1000, {width_mm!r}/1000, {height_mm!r}/1000
            pt = {panel_thickness_mm!r}/1000

            panels = []
            # ±X faces
            for sx in (-1, 1):
                bpy.ops.mesh.primitive_cube_add(size=1, location=(sx*(L-pt)/2, 0, 0))
                p = bpy.context.active_object; p.scale=(pt, W, H); bpy.ops.object.transform_apply(scale=True)
                panels.append(p)
            # ±Y faces
            for sy in (-1, 1):
                bpy.ops.mesh.primitive_cube_add(size=1, location=(0, sy*(W-pt)/2, 0))
                p = bpy.context.active_object; p.scale=(L, pt, H); bpy.ops.object.transform_apply(scale=True)
                panels.append(p)
            # ±Z faces
            for sz in (-1, 1):
                bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, sz*(H-pt)/2))
                p = bpy.context.active_object; p.scale=(L, W, pt); bpy.ops.object.transform_apply(scale=True)
                panels.append(p)

            if {include_solar_panels!r}:
                sp_L, sp_W = {solar_panel_span_mm!r}/1000, {solar_panel_width_mm!r}/1000
                for sy in (-1, 1):
                    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, sy*(W/2 + sp_L/2), 0))
                    p = bpy.context.active_object; p.scale=(sp_W, sp_L, 0.01); bpy.ops.object.transform_apply(scale=True)
                    p.name = f"SolarPanel_{{'P' if sy>0 else 'N'}}Y"
                    panels.append(p)

            bpy.ops.object.select_all(action="DESELECT")
            for p in panels: p.select_set(True)
            bpy.context.view_layer.objects.active = panels[0]
            bpy.ops.object.join()
            obj = bpy.context.active_object
            obj.name = {name!r}
            _emit({{"object": obj.name, "L_m": L, "W_m": W, "H_m": H, "panels": len(panels), "solar_panels": {include_solar_panels!r}}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def cubesat(
        ctx: Context,
        size_u: int = 3,
        u_length_mm: float = 100.0,
        u_cross_mm: float = 100.0,
        wall_thickness_mm: float = 2.0,
        name: str = "CubeSat",
    ) -> str:
        """
        CubeSat hollow frame. `size_u` ∈ {{1, 1.5, 2, 3, 6, 12}} — longest
        dimension is `size_u * u_length_mm`.
        """
        body = textwrap.dedent(f'''
            u = float({size_u!r})
            uL = {u_length_mm!r}/1000
            uX = {u_cross_mm!r}/1000
            wt = {wall_thickness_mm!r}/1000
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,0))
            obj = bpy.context.active_object
            obj.name = {name!r}
            obj.scale = (uX, uX, u * uL)
            bpy.ops.object.transform_apply(scale=True)
            mod = obj.modifiers.new(name="Solidify", type="SOLIDIFY")
            mod.thickness = -wt; mod.offset = 1
            bpy.ops.object.modifier_apply(modifier=mod.name)
            _emit({{"object": obj.name, "size_u": u, "length_m": u*uL, "cross_m": uX, "wall_m": wt}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def rover_chassis(
        ctx: Context,
        wheelbase_mm: float = 1200.0,
        track_mm: float = 900.0,
        body_height_mm: float = 300.0,
        wheel_diameter_mm: float = 200.0,
        wheel_width_mm: float = 80.0,
        ground_clearance_mm: float = 250.0,
        name: str = "Rover",
    ) -> str:
        """
        Simple 4-wheel rover chassis: rectangular body on four cylindrical wheels.
        Returns a joined mesh. For articulated suspensions, script on top with
        execute_blender_code.
        """
        body = textwrap.dedent(f'''
            import math
            wb, tr = {wheelbase_mm!r}/1000, {track_mm!r}/1000
            bh = {body_height_mm!r}/1000
            wd, ww = {wheel_diameter_mm!r}/1000, {wheel_width_mm!r}/1000
            gc = {ground_clearance_mm!r}/1000

            # Body
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, gc + bh/2))
            body = bpy.context.active_object
            body.scale = (wb, tr * 0.8, bh); bpy.ops.object.transform_apply(scale=True)
            parts = [body]

            # Wheels — axis along Y
            for sx in (-1, 1):
                for sy in (-1, 1):
                    bpy.ops.mesh.primitive_cylinder_add(radius=wd/2, depth=ww,
                        location=(sx*wb/2, sy*tr/2, wd/2), rotation=(math.radians(90), 0, 0))
                    w = bpy.context.active_object
                    w.name = f"Wheel_{{'F' if sx>0 else 'R'}}{{'L' if sy>0 else 'R'}}"
                    parts.append(w)

            bpy.ops.object.select_all(action="DESELECT")
            for p in parts: p.select_set(True)
            bpy.context.view_layer.objects.active = body
            bpy.ops.object.join()
            obj = bpy.context.active_object
            obj.name = {name!r}
            _emit({{"object": obj.name, "wheelbase_m": wb, "track_m": tr, "wheels": 4}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def lander_leg(
        ctx: Context,
        strut_length_mm: float = 1500.0,
        strut_diameter_mm: float = 40.0,
        footpad_diameter_mm: float = 300.0,
        footpad_thickness_mm: float = 30.0,
        splay_angle_deg: float = 25.0,
        name: str = "LanderLeg",
    ) -> str:
        """
        Single lander leg: cylindrical strut with a disk footpad, splayed
        outward from vertical by `splay_angle_deg`. Anchor point is at origin;
        strut tilts along +X.
        """
        body = textwrap.dedent(f'''
            import math
            L = {strut_length_mm!r}/1000
            d = {strut_diameter_mm!r}/1000
            pd = {footpad_diameter_mm!r}/1000
            pt = {footpad_thickness_mm!r}/1000
            ang = math.radians({splay_angle_deg!r})
            # Strut
            bpy.ops.mesh.primitive_cylinder_add(radius=d/2, depth=L, location=(0,0,0))
            s = bpy.context.active_object; s.name = "_strut"
            # Rotate so -Z end is at origin pointing +X-out
            s.rotation_euler = (0, math.pi/2 - ang, 0)
            s.location = (math.sin(ang)*L/2, 0, -math.cos(ang)*L/2)
            bpy.ops.object.transform_apply(location=True, rotation=True)
            # Footpad at the strut's far end
            fx = math.sin(ang) * L
            fz = -math.cos(ang) * L
            bpy.ops.mesh.primitive_cylinder_add(radius=pd/2, depth=pt, location=(fx, 0, fz - pt/2))
            p = bpy.context.active_object; p.name = "_foot"
            bpy.ops.object.select_all(action="DESELECT")
            s.select_set(True); p.select_set(True)
            bpy.context.view_layer.objects.active = s
            bpy.ops.object.join()
            obj = bpy.context.active_object
            obj.name = {name!r}
            _emit({{"object": obj.name, "strut_m": L, "footpad_m": pd, "splay_deg": {splay_angle_deg!r}}})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def planetary_terrain_patch(
        ctx: Context,
        size_m: float = 100.0,
        subdivisions: int = 128,
        noise_scale: float = 0.05,
        noise_strength: float = 5.0,
        seed: int = 0,
        name: str = "Terrain",
    ) -> str:
        """
        Square terrain patch with procedural heightfield (Perlin-like noise).
        Useful backdrop for rover/lander renders.

        Parameters:
        - size_m: edge length.
        - subdivisions: grid resolution (e.g. 128 → 128×128 quads).
        - noise_scale: spatial frequency of features.
        - noise_strength: vertical displacement amplitude in meters.
        """
        body = textwrap.dedent(f'''
            import mathutils
            n = int({subdivisions!r})
            s = {size_m!r}
            scale = {noise_scale!r}
            strength = {noise_strength!r}
            seed = int({seed!r})
            bpy.ops.mesh.primitive_grid_add(x_subdivisions=n, y_subdivisions=n, size=s)
            obj = bpy.context.active_object
            obj.name = {name!r}
            noise_v = mathutils.Vector((seed * 13.17, seed * 7.91, seed * 3.33))
            for v in obj.data.vertices:
                p = (v.co + noise_v) * scale
                v.co.z = mathutils.noise.noise(p, noise_basis="PERLIN_ORIGINAL") * strength
            obj.data.update()
            _emit({{"object": obj.name, "size_m": s, "resolution": n, "strength_m": strength}})
        ''').strip()
        return _dispatch(body)
