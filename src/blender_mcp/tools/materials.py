"""
Engineering material library.

Ships a curated JSON database (`data/materials.json`) of common aerospace
materials with thermal, optical, structural, and Blender shader properties.
Exposes three MCP tools:

- list_materials(category=None)
- get_material_properties(material_id)
- apply_material(object_name, material_id, rename_to=None)

When applied, each material's thermal/optical/structural values are stored as
custom properties on the Blender material data-block (e.g. `mat["thermal.k"]`),
so downstream simulation-export tools can read them directly from the .blend.
"""

import importlib.resources as ires
import json
import textwrap
from functools import lru_cache
from typing import Dict, Any

from mcp.server.fastmcp import FastMCP, Context


@lru_cache(maxsize=1)
def _library() -> Dict[str, Any]:
    path = ires.files("blender_mcp") / "data" / "materials.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _flat_custom_props(mat: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten thermal/optical/structural sub-objects to dotted keys."""
    out: Dict[str, Any] = {}
    for section in ("thermal", "optical", "structural"):
        for k, v in (mat.get(section) or {}).items():
            if k == "notes":
                continue
            if isinstance(v, (int, float)):
                out[f"{section}.{k}"] = v
    return out


def register(mcp: FastMCP) -> None:
    """Register material-library tools on the given FastMCP instance."""
    from blender_mcp.server import _run_in_blender, _snippet_header

    @mcp.tool()
    def list_materials(ctx: Context, category: str = "") -> str:
        """
        List available materials from the engineering library.

        Parameters:
        - category: Optional filter — one of "metal", "composite", "polymer",
                    "coating", "insulation". Empty string returns all.

        Returns a JSON list of {id, name, category} entries.
        """
        lib = _library()
        entries = []
        for mid, mat in lib["materials"].items():
            if category and mat.get("category") != category:
                continue
            entries.append({
                "id": mid,
                "name": mat.get("name", mid),
                "category": mat.get("category", "unknown"),
            })
        entries.sort(key=lambda e: (e["category"], e["id"]))
        return json.dumps({"count": len(entries), "materials": entries}, indent=2)

    @mcp.tool()
    def get_material_properties(ctx: Context, material_id: str) -> str:
        """
        Return the full property record (thermal, optical, structural, shader,
        sources, notes) for a material. Use list_materials to discover IDs.

        Parameters:
        - material_id: e.g. "al_6061", "kapton_hn", "z93_white_paint".
        """
        lib = _library()
        mat = lib["materials"].get(material_id)
        if mat is None:
            return json.dumps({
                "error": f"unknown material_id {material_id!r}",
                "available": sorted(lib["materials"].keys()),
            }, indent=2)
        return json.dumps({"id": material_id, **mat, "units": lib.get("units")}, indent=2)

    @mcp.tool()
    def apply_material(
        ctx: Context,
        object_name: str,
        material_id: str,
        rename_to: str = "",
    ) -> str:
        """
        Create (or re-use) a Blender material from the engineering library and
        assign it to an object. Thermal/optical/structural values are stored as
        custom properties on the material data-block so they can be read by
        export scripts (e.g. Elmer, OpenFOAM) via `bpy.data.materials[name][key]`.

        If a material with the target name already exists, it is re-used (the
        shader and custom properties are refreshed to match the library).

        Parameters:
        - object_name: Name of the Blender object to assign to. Must be a mesh.
        - material_id: ID from the library (see list_materials).
        - rename_to: Optional override for the Blender material name. Empty
                     string (default) uses `material_id`.

        Returns the object/material names and the custom properties set.
        """
        lib = _library()
        mat = lib["materials"].get(material_id)
        if mat is None:
            return json.dumps({
                "error": f"unknown material_id {material_id!r}",
                "available": sorted(lib["materials"].keys()),
            }, indent=2)

        mat_name = rename_to or material_id
        blender_shader = mat.get("blender") or {}
        base_color = blender_shader.get("base_color") or [0.8, 0.8, 0.8, 1.0]
        metallic = float(blender_shader.get("metallic", 0.0))
        roughness = float(blender_shader.get("roughness", 0.5))
        custom_props = _flat_custom_props(mat)

        body = textwrap.dedent(f'''
            obj = bpy.data.objects.get({object_name!r})
            if obj is None or obj.type != "MESH":
                _emit({{"error": f"object {object_name!r} not found or not a mesh"}})
            else:
                mat = bpy.data.materials.get({mat_name!r})
                if mat is None:
                    mat = bpy.data.materials.new(name={mat_name!r})
                mat.use_nodes = True
                nt = mat.node_tree
                bsdf = nt.nodes.get("Principled BSDF")
                if bsdf is None:
                    # Recreate a default BSDF if missing
                    for n in list(nt.nodes):
                        nt.nodes.remove(n)
                    out = nt.nodes.new("ShaderNodeOutputMaterial")
                    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
                    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
                bc = {base_color!r}
                bsdf.inputs["Base Color"].default_value = (bc[0], bc[1], bc[2], bc[3] if len(bc) > 3 else 1.0)
                bsdf.inputs["Metallic"].default_value = {metallic!r}
                bsdf.inputs["Roughness"].default_value = {roughness!r}
                if len(bc) > 3 and bc[3] < 1.0:
                    if "Alpha" in bsdf.inputs:
                        bsdf.inputs["Alpha"].default_value = bc[3]
                    # Blender 4.2+ uses 'surface_render_method'; pre-4.2 uses 'blend_method'
                    if hasattr(mat, "surface_render_method"):
                        mat.surface_render_method = "BLENDED"
                    else:
                        mat.blend_method = "BLEND"
                props = {custom_props!r}
                for k, v in props.items():
                    mat[k] = v
                mat["library.id"] = {material_id!r}
                mat["library.name"] = {mat.get("name", material_id)!r}
                if obj.data.materials:
                    obj.data.materials[0] = mat
                else:
                    obj.data.materials.append(mat)
                _emit({{
                    "object": obj.name,
                    "material": mat.name,
                    "material_id": {material_id!r},
                    "custom_properties_set": len(props) + 2,
                    "properties": {{k: v for k, v in mat.items()}},
                }})
        ''').strip()
        return json.dumps(_run_in_blender(_snippet_header() + body), indent=2)
