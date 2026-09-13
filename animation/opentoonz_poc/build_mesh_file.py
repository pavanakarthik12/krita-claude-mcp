"""
Builds a minimal OpenToonz .mesh level file (TMeshImage), matching the exact
binary/text container format reverse-engineered from the OpenToonz source at
C:\\Users\\pavan\\OneDrive\\Desktop\\opentoonz:

  toonz/sources/image/mesh/tiio_mesh.cpp   (TImageWriterMesh::save)
  toonz/sources/common/tmeshimage/tmeshimage.cpp  (TTextureMesh::saveData)
  toonz/sources/common/tstream/tstream.cpp (TOStream compressed-file container)

File layout (compressed TOStream, per tstream.cpp lines ~282-309):
    magic       "TABc"            (4 bytes)
    endianness  int32 0x0A0B0C0D
    decomp_len  int32
    comp_len    int32
    payload     LZ4 *frame* (not raw block) compressed XML text, length comp_len

The XML text payload itself (per tiio_mesh.cpp) is:
    <header>
      <version>1 19</version>
      <dpi>DPIX DPIY</dpi>
    </header>
    <mesh>
      <V> vCount  x0 y0  x1 y1 ... </V>
      <E> eCount  v0 v1  v0 v1 ... </E>
      <F> fCount  e0 e1 e2  ... </F>
    </mesh>

(rigidities block omitted - all vertices default to rigidity 1.0, which is
what TTextureMesh::saveData itself does when no vertex has non-1 rigidity)
"""
import struct
import lz4.frame


def build_mesh_xml(vertices, edges, faces, dpi=(72.0, 72.0)):
    lines = []
    lines.append("<header>")
    lines.append("<version>1 19</version>")
    lines.append(f"<dpi>{dpi[0]} {dpi[1]}</dpi>")
    lines.append("</header>")
    lines.append("<mesh>")

    v_parts = [str(len(vertices))]
    for x, y in vertices:
        v_parts.append(f"{x} {y}")
    lines.append("<V>" + " ".join(v_parts) + "</V>")

    e_parts = [str(len(edges))]
    for v0, v1 in edges:
        e_parts.append(f"{v0} {v1}")
    lines.append("<E>" + " ".join(e_parts) + "</E>")

    f_parts = [str(len(faces))]
    for e0, e1, e2 in faces:
        f_parts.append(f"{e0} {e1} {e2}")
    lines.append("<F>" + " ".join(f_parts) + "</F>")

    lines.append("</mesh>")
    return "".join(lines)


def write_compressed_tstream(path, xml_text):
    data = xml_text.encode("ascii")
    compressed = lz4.frame.compress(data)

    with open(path, "wb") as f:
        f.write(b"TABc")
        f.write(struct.pack("<i", 0x0A0B0C0D))
        f.write(struct.pack("<i", len(data)))
        f.write(struct.pack("<i", len(compressed)))
        f.write(compressed)


def build_two_bone_quad_mesh():
    """
    A simple rectangular strip mesh (4 vertices, 2 triangles) spanning the
    rest-pose of a 2-bone skeleton: root at (0,0), child at (0,5).
    Mesh vertices double as the texture-space (UV) coordinates that the
    content column will be projected onto.

    Scale note: OpenToonz stage-object/skeleton coordinates are in the
    scene's field-guide units (this project's default camera is a 16x9
    field, see sandbox_otprj.xml <cleanupCamera><cameraSize>16 9</...).
    A shape spanning 100 units (as an earlier draft used) sits almost
    entirely outside the visible camera frustum, rendering as blank/empty
    frames - confirmed empirically (all-zero RGBA output). Keeping the
    character within a handful of field units keeps it on camera.
    """
    vertices = [
        (-2.5, 0.0),    # 0 bottom-left  (near root)
        (2.5, 0.0),     # 1 bottom-right (near root)
        (2.5, 5.0),     # 2 top-right    (near child)
        (-2.5, 5.0),    # 3 top-left     (near child)
    ]
    # tcg::Mesh edges are directed/shared by faces; the exact edge id list
    # only needs to be topologically consistent, referenced by face triples.
    edges = [
        (0, 1),  # e0 bottom
        (1, 2),  # e1 right
        (2, 0),  # e2 diagonal
        (2, 3),  # e3 top
        (3, 0),  # e4 left
    ]
    faces = [
        (0, 1, 2),  # triangle 0-1-2
        (3, 4, 2),  # triangle 2-3-0 (edges: top, left, diagonal)
    ]
    return vertices, edges, faces


if __name__ == "__main__":
    import sys
    out_path = sys.argv[1] if len(sys.argv) > 1 else "output/character.mesh"
    vertices, edges, faces = build_two_bone_quad_mesh()
    xml_text = build_mesh_xml(vertices, edges, faces)
    write_compressed_tstream(out_path, xml_text)
    print(f"wrote {out_path} ({len(xml_text)} bytes of XML payload)")
