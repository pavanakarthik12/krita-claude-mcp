"""
Builds the "simple drawable character" - a plain PNG raster image sized to
match the rest-pose bounding box of the Plastic mesh (-50..50 x, 0..100 y in
scene units, rendered at 72 dpi => 1 unit = 1 px here for simplicity).

This is deliberately NOT an OpenToonz-proprietary vector (.pli) level - PNG
is a standard, well-understood raster format that OpenToonz's TXshSimpleLevel
loads directly (see toonz/sources/image/tiio.cpp: TFileType::declare("png",
TFileType::RASTER_IMAGE)), so no proprietary format reverse-engineering is
needed for the artwork itself - only for the mesh/skeleton/deformation data,
which is the actual point of this POC.
"""
from PIL import Image, ImageDraw


def build_character_png(path, size=(100, 100)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # simple "body" silhouette: a rounded rectangle + a circular "head" bump
    # near the child-bone end (top of the image, y=0 in image space = y=100
    # in scene space since raster Y grows downward)
    draw.rounded_rectangle([10, 30, 90, 100], radius=15, fill=(220, 120, 40, 255))
    draw.ellipse([25, 0, 75, 50], fill=(220, 160, 90, 255))

    img.save(path)


if __name__ == "__main__":
    import sys
    out_path = sys.argv[1] if len(sys.argv) > 1 else "output/character_art.png"
    build_character_png(out_path)
    print(f"wrote {out_path}")
