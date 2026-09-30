"""Buat ulang assets/icons/icon_clip.png: ikon clip dengan motif kotak tabel.

Ikon disimpan sebagai L + alpha supaya bisa diwarnai lewat properti ``color``
Kivy, sama seperti ikon-ikon lain di assets/icons. Semua bentuk digambar ulang
dari nol, jadi skrip ini bisa dijalankan berulang kali dengan hasil sama.

Jalankan:
    .venv-audit/bin/python tools/make_clip_icon.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter

SIZE = 96
SCALE = 8
ICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "icons", "icon_clip.png",
)


def canvas():
    return Image.new("L", (SIZE * SCALE, SIZE * SCALE), 0)


def finish(mask, blur=0.0):
    """Turunkan ke 96x96,haluskan tepi, lalu tulis sebagai L + alpha."""
    if blur:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    alpha = mask.resize((SIZE, SIZE), Image.LANCZOS)
    alpha = alpha.point(lambda value: 255 if value > 110 else 0)
    return Image.merge("LA", (Image.new("L", alpha.size, 255), alpha))


def table_mask():
    """Kotak tabel: border, garis judul, dan dua garis kolom."""
    mask = canvas()
    draw = ImageDraw.Draw(mask)
    s = SCALE
    stroke = 7 * s
    draw.rounded_rectangle(
        (5 * s, 24 * s, 91 * s, 80 * s), radius=8 * s, outline=255, width=stroke
    )
    draw.line((5 * s, 45 * s, 91 * s, 45 * s), fill=255, width=stroke)
    for x in (34, 62):
        draw.line((x * s, 54 * s, x * s, 72 * s), fill=255, width=stroke)
    return mask.resize((SIZE, SIZE), Image.LANCZOS)


def paperclip_mask():
    """Gambar clip: dua lingkaran bersarang dengan celah pembuka di kiri bawah."""
    s = SCALE
    mask = canvas()
    draw = ImageDraw.Draw(mask)
    stroke = 7 * s

    # Lingkaran luar.
    draw.rounded_rectangle(
        (24 * s, 6 * s, 72 * s, 90 * s), radius=24 * s, outline=255, width=stroke
    )
    # Lingkaran dalam, berhenti sebelum mencapai lingkaran luar.
    draw.rounded_rectangle(
        (38 * s, 24 * s, 58 * s, 72 * s), radius=12 * s, outline=255, width=stroke
    )
    # Celah pembuka: memotong dinding kiri lingkaran luar.
    draw.rounded_rectangle(
        (18 * s, 66 * s, 34 * s, 76 * s), radius=4 * s, fill=0
    )

    mask = mask.rotate(30, resample=Image.BICUBIC, expand=False, center=(48 * s, 48 * s))
    mask = mask.resize((SIZE, SIZE), Image.LANCZOS)
    # Pangkas sisa kosong di luar kanvas.
    cropped = mask.crop(mask.getbbox())
    width, height = cropped.size
    scale = 74 / max(width, height)
    return cropped.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS
    )


def compose():
    table = table_mask()
    clip = paperclip_mask()

    layer = Image.new("L", (SIZE, SIZE), 0)
    layer.paste(clip, (SIZE - clip.width - 4, 1))

    # Halo kosong di sekitar klip supaya garis tabel terpotong rapi sehingga
    # clip dan tabel tetap terbaca pada ukuran tombol yang kecil.
    halo = layer.filter(ImageFilter.MaxFilter(9))
    table_visible = Image.composite(Image.new("L", (SIZE, SIZE), 0), table, halo)

    combined = table_visible.point(lambda value: 255 if value > 110 else 0)
    combined.paste(layer, (0, 0), layer)
    finish(combined).save(ICON_PATH)
    print(f"icon clip ditulis: {ICON_PATH} ({SIZE}x{SIZE})")


if __name__ == "__main__":
    compose()
