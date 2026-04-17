"""
Mesh simplification and defeaturing tools.

Wraps Blender's bpy.ops mesh and modifier operators behind named MCP tools so
the model gets a discoverable surface for common simplification operations
instead of having to recompose execute_blender_code calls each time.

All tools dispatch via execute_blender_code — no addon.py changes required.

Typical CAE defeaturing flow on an imported STL or OBJ:
    1. separate_loose_parts(obj)            # split disconnected components
    2. delete_small_objects(threshold_mm=5) # drop bolts, washers, fasteners
    3. keep_outer_shell(obj)                # remove interior faces
    4. fill_holes(obj, max_sides=8)         # close small openings
    5. merge_duplicates(obj, threshold=1e-4)# weld coincident verts
    6. decimate(obj, ratio=0.3)             # reduce poly count for meshing
"""

import json
import textwrap

from mcp.server.fastmcp import FastMCP, Context


def register(mcp: FastMCP) -> None:
    """Register all simplification tools on the given FastMCP instance."""
    from blender_mcp.server import _run_in_blender, _snippet_header

    def _dispatch(body: str) -> str:
        return json.dumps(_run_in_blender(_snippet_header() + body), indent=2)

    @mcp.tool()
    def decimate(
        ctx: Context,
        object_name: str,
        ratio: float = 0.5,
        apply: bool = True,
    ) -> str:
        """
        Add a Decimate (Collapse) modifier to reduce a mesh's polygon count.

        Parameters:
        - object_name: Name of the mesh object.
        - ratio: Collapse ratio in (0, 1]. 0.5 keeps roughly half the polygons.
        - apply: If True (default) the modifier is applied immediately.
                 If False it is left on the modifier stack for tweaking.

        Returns vertex/face counts before and after.
        """
        body = textwrap.dedent(f'''
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                vb, fb = len(obj.data.vertices), len(obj.data.polygons)
                bpy.context.view_layer.objects.active = obj
                if bpy.context.object.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
                mod = obj.modifiers.new(name="Decimate_collapse", type="DECIMATE")
                mod.decimate_type = "COLLAPSE"
                mod.ratio = {ratio!r}
                if {apply!r}:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                va, fa = len(obj.data.vertices), len(obj.data.polygons)
                _emit({{
                    "object": obj.name,
                    "ratio": {ratio!r},
                    "applied": {apply!r},
                    "modifier": None if {apply!r} else mod.name,
                    "vertices_before": vb, "vertices_after": va,
                    "faces_before": fb, "faces_after": fa,
                }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def decimate_planar(
        ctx: Context,
        object_name: str,
        angle_deg: float = 5.0,
        apply: bool = True,
    ) -> str:
        """
        Decimate a mesh by dissolving faces whose adjacent normals differ by less
        than `angle_deg`. Best for collapsing flat regions (CAD plates, walls)
        without affecting curved areas.

        Parameters:
        - object_name: Name of the mesh object.
        - angle_deg: Maximum angle between coplanar faces (degrees). Default 5.
        - apply: Apply the modifier immediately.
        """
        body = textwrap.dedent(f'''
            import math
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                vb, fb = len(obj.data.vertices), len(obj.data.polygons)
                bpy.context.view_layer.objects.active = obj
                if bpy.context.object.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
                mod = obj.modifiers.new(name="Decimate_planar", type="DECIMATE")
                mod.decimate_type = "DISSOLVE"
                mod.angle_limit = math.radians({angle_deg!r})
                if {apply!r}:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                va, fa = len(obj.data.vertices), len(obj.data.polygons)
                _emit({{
                    "object": obj.name,
                    "angle_deg": {angle_deg!r},
                    "applied": {apply!r},
                    "modifier": None if {apply!r} else mod.name,
                    "vertices_before": vb, "vertices_after": va,
                    "faces_before": fb, "faces_after": fa,
                }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def keep_outer_shell(ctx: Context, object_name: str) -> str:
        """
        Delete interior faces of a mesh, keeping only the outer visible shell.
        Standard step when preparing CAD imports for thermal radiation/view-factor
        analysis where only external surfaces matter.

        Uses bpy.ops.mesh.select_interior_faces() — selects faces fully enclosed
        by other faces, then deletes them.

        Parameters:
        - object_name: Name of the mesh object.

        Returns face counts before and after.
        """
        body = textwrap.dedent(f'''
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                fb = len(obj.data.polygons)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="DESELECT")
                bpy.ops.mesh.select_interior_faces()
                # Count selected before deletion
                bpy.ops.object.mode_set(mode="OBJECT")
                selected = sum(1 for f in obj.data.polygons if f.select)
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.delete(type="FACE")
                bpy.ops.object.mode_set(mode="OBJECT")
                fa = len(obj.data.polygons)
                _emit({{
                    "object": obj.name,
                    "interior_faces_removed": selected,
                    "faces_before": fb, "faces_after": fa,
                }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def delete_small_objects(
        ctx: Context,
        threshold_mm: float = 5.0,
        name_filter: str = "",
        dry_run: bool = True,
    ) -> str:
        """
        Delete mesh objects whose bounding-box diagonal is smaller than
        `threshold_mm`. Used to strip fasteners (bolts, screws, washers) and
        small details from imported CAD assemblies for CAE prep.

        Parameters:
        - threshold_mm: Bounding-box diagonal threshold in millimeters.
                        Assumes scene units are meters (Blender default).
                        Default 5 mm.
        - name_filter: Optional substring; only objects whose name contains it
                       are considered. Empty (default) = all mesh objects.
        - dry_run: If True (default) only lists candidates without deleting.
                   Set False to actually delete. Always start with dry_run.

        Returns the list of matching objects with their diagonals (mm).
        """
        body = textwrap.dedent(f'''
            import math
            threshold_m = {threshold_mm!r} / 1000.0
            name_filter = {name_filter!r}
            dry_run = {dry_run!r}
            candidates = []
            for o in list(bpy.data.objects):
                if o.type != "MESH":
                    continue
                if name_filter and name_filter not in o.name:
                    continue
                dx, dy, dz = o.dimensions
                diag = math.sqrt(dx*dx + dy*dy + dz*dz)
                if diag < threshold_m:
                    candidates.append({{"name": o.name, "diagonal_mm": round(diag * 1000, 4)}})
            if not dry_run:
                for c in candidates:
                    o = bpy.data.objects.get(c["name"])
                    if o is not None:
                        bpy.data.objects.remove(o, do_unlink=True)
            _emit({{
                "threshold_mm": {threshold_mm!r},
                "name_filter": name_filter or None,
                "dry_run": dry_run,
                "matched": len(candidates),
                "objects": candidates,
            }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def separate_loose_parts(ctx: Context, object_name: str) -> str:
        """
        Split a mesh into one object per disconnected component (loose part).
        Use this before delete_small_objects on an imported STL where the
        whole assembly came in as a single mesh.

        Parameters:
        - object_name: Name of the mesh to split.

        Returns the list of resulting object names.
        """
        body = textwrap.dedent(f'''
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                before = set(bpy.data.objects.keys())
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.separate(type="LOOSE")
                bpy.ops.object.mode_set(mode="OBJECT")
                after = set(bpy.data.objects.keys())
                created = sorted(after - before)
                _emit({{
                    "source": obj.name,
                    "parts_created": len(created) + 1,
                    "new_objects": created,
                }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def fill_holes(ctx: Context, object_name: str, max_sides: int = 4) -> str:
        """
        Fill closed boundary loops in a mesh with up to `max_sides` edges.
        Useful for closing small openings left by defeaturing or by sloppy CAD
        export.

        Parameters:
        - object_name: Name of the mesh.
        - max_sides: Maximum edges per hole to fill. 0 = no limit. Default 4.

        Returns face counts before and after.
        """
        body = textwrap.dedent(f'''
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                fb = len(obj.data.polygons)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.mesh.fill_holes(sides={max_sides!r})
                bpy.ops.object.mode_set(mode="OBJECT")
                fa = len(obj.data.polygons)
                _emit({{
                    "object": obj.name,
                    "max_sides": {max_sides!r},
                    "faces_before": fb, "faces_after": fa,
                    "faces_added": fa - fb,
                }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def merge_duplicates(
        ctx: Context,
        object_name: str,
        threshold: float = 0.0001,
    ) -> str:
        """
        Merge vertices that lie within `threshold` of each other (Blender's
        Merge by Distance). Eliminates seams from boolean operations or
        duplicated geometry from STL stitching.

        Parameters:
        - object_name: Name of the mesh.
        - threshold: Distance threshold in scene units (meters by default).
                     Default 1e-4 (0.1 mm).

        Returns vertex counts before and after.
        """
        body = textwrap.dedent(f'''
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                vb = len(obj.data.vertices)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.mesh.remove_doubles(threshold={threshold!r})
                bpy.ops.object.mode_set(mode="OBJECT")
                va = len(obj.data.vertices)
                _emit({{
                    "object": obj.name,
                    "threshold": {threshold!r},
                    "vertices_before": vb, "vertices_after": va,
                    "vertices_merged": vb - va,
                }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def triangulate(
        ctx: Context,
        object_name: str,
        quad_method: str = "BEAUTY",
        ngon_method: str = "BEAUTY",
    ) -> str:
        """
        Convert all quads and n-gons in a mesh to triangles. Required by most
        FE/FV solvers and STL exporters.

        Parameters:
        - object_name: Name of the mesh.
        - quad_method: BEAUTY | FIXED | FIXED_ALTERNATE | SHORTEST_DIAGONAL
        - ngon_method: BEAUTY | CLIP

        Returns face counts and triangle count after.
        """
        body = textwrap.dedent(f'''
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                fb = len(obj.data.polygons)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.mesh.quads_convert_to_tris(
                    quad_method={quad_method!r},
                    ngon_method={ngon_method!r},
                )
                bpy.ops.object.mode_set(mode="OBJECT")
                fa = len(obj.data.polygons)
                tri_count = sum(1 for p in obj.data.polygons if len(p.vertices) == 3)
                _emit({{
                    "object": obj.name,
                    "faces_before": fb, "faces_after": fa,
                    "triangles": tri_count,
                }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def remesh_voxel(
        ctx: Context,
        object_name: str,
        voxel_size: float = 0.01,
        adaptivity: float = 0.0,
        apply: bool = True,
    ) -> str:
        """
        Voxel remesh: rebuild a mesh from a uniform voxel grid. Produces a
        watertight, manifold mesh with consistent triangle size — ideal as a
        precursor to FEM/CFD meshing.

        Parameters:
        - object_name: Name of the mesh.
        - voxel_size: Edge length of one voxel in scene units (meters).
                      Smaller = more detail, more memory. Default 0.01 (10 mm).
        - adaptivity: 0..1, allows larger triangles in flat regions. Default 0.
        - apply: Apply the modifier immediately. Default True.

        Returns vertex/face counts before and after.
        """
        body = textwrap.dedent(f'''
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                vb, fb = len(obj.data.vertices), len(obj.data.polygons)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="OBJECT")
                mod = obj.modifiers.new(name="Remesh_voxel", type="REMESH")
                mod.mode = "VOXEL"
                mod.voxel_size = {voxel_size!r}
                mod.adaptivity = {adaptivity!r}
                if {apply!r}:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                va, fa = len(obj.data.vertices), len(obj.data.polygons)
                _emit({{
                    "object": obj.name,
                    "voxel_size": {voxel_size!r},
                    "adaptivity": {adaptivity!r},
                    "applied": {apply!r},
                    "modifier": None if {apply!r} else mod.name,
                    "vertices_before": vb, "vertices_after": va,
                    "faces_before": fb, "faces_after": fa,
                }})
        ''').strip()
        return _dispatch(body)

    @mcp.tool()
    def remesh_quad(
        ctx: Context,
        object_name: str,
        octree_depth: int = 6,
        scale: float = 0.9,
        apply: bool = True,
    ) -> str:
        """
        Quad-based remesh (octree). Produces a quad-dominant retopology.
        Faster than voxel for organic shapes; use voxel for hard-surface CAD.

        Parameters:
        - object_name: Name of the mesh.
        - octree_depth: Subdivision depth, 4..10 typical. Higher = more detail.
                        Default 6.
        - scale: 0..1, controls how tightly the remesh hugs the original.
                 Default 0.9.
        - apply: Apply the modifier immediately. Default True.
        """
        body = textwrap.dedent(f'''
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                vb, fb = len(obj.data.vertices), len(obj.data.polygons)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="OBJECT")
                mod = obj.modifiers.new(name="Remesh_quad", type="REMESH")
                mod.mode = "SHARP"
                mod.octree_depth = {octree_depth!r}
                mod.scale = {scale!r}
                if {apply!r}:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                va, fa = len(obj.data.vertices), len(obj.data.polygons)
                _emit({{
                    "object": obj.name,
                    "octree_depth": {octree_depth!r},
                    "scale": {scale!r},
                    "applied": {apply!r},
                    "modifier": None if {apply!r} else mod.name,
                    "vertices_before": vb, "vertices_after": va,
                    "faces_before": fb, "faces_after": fa,
                }})
        ''').strip()
        return _dispatch(body)
