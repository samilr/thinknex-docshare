"""Vista protegida: cada página se renderiza en el servidor a PNG con marca de agua.

Con permiso "Ver" el destinatario nunca recibe el archivo original, solo imágenes marcadas con su
identidad. No evita capturas de pantalla (ningún visor web puede), pero sí la descarga del archivo y
deja trazabilidad visible en cada página.
"""

import hashlib
import io
import math
import threading
from collections import OrderedDict
from functools import cache
from pathlib import Path

import pypdfium2 as pdfium
import reportlab
from PIL import Image, ImageDraw, ImageFont

RENDER_SCALE = 1.6  # ~115 DPI: legible y liviano
_pdfium_lock = threading.Lock()  # pdfium no es thread-safe


class UnsupportedPreview(ValueError):
    pass


def kind(mime_type: str) -> str:
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type in ("image/png", "image/jpeg"):
        return "image"
    if mime_type == "text/plain":
        return "text"
    return "other"


def page_count(content: bytes, mime_type: str) -> int:
    k = kind(mime_type)
    if k == "pdf":
        with _pdfium_lock:
            pdf = pdfium.PdfDocument(content)
            try:
                return len(pdf)
            finally:
                pdf.close()
    return 1 if k in ("image", "text") else 0


# Bitstream Vera (incluida en reportlab): cubre tildes y eñes, a diferencia de la fuente por
# defecto de Pillow, y evita depender de fuentes del sistema en la imagen del contenedor.
_FONT_PATH = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"


@cache
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if _FONT_PATH.exists():
        return ImageFont.truetype(str(_FONT_PATH), size)
    return ImageFont.load_default(size=size)


def _watermark(image: Image.Image, stamp: str) -> Image.Image:
    base = image.convert("RGBA")
    width, height = base.size
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))

    # Texto diagonal repetido en filas y columnas, semitransparente, sobre toda la página.
    size = max(14, width // 38)
    font = _font(size)
    text_w = int(font.getlength(stamp)) + size * 4
    tile = Image.new("RGBA", (text_w, size * 3), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((size, size // 2), stamp, font=font, fill=(190, 30, 30, 70))
    tile = tile.rotate(30, expand=True)
    step_x = max(tile.size[0] * 3 // 4, size * 10)
    step_y = max(tile.size[1] // 2, size * 6)
    for row, y in enumerate(range(-tile.size[1] // 2, height, step_y)):
        shift = (row % 2) * (step_x // 2)
        for x in range(-tile.size[0] // 2 - shift, width, step_x):
            _paste(overlay, tile, x, y)

    # Pie legible con la identidad del acceso.
    footer = _font(max(11, width // 70))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle([(0, height - size * 2), (width, height)], fill=(255, 255, 255, 200))
    draw.text((12, height - math.ceil(size * 1.6)), stamp, font=footer, fill=(120, 20, 20, 255))
    return Image.alpha_composite(base, overlay).convert("RGB")


def _paste(overlay: Image.Image, tile: Image.Image, x: int, y: int) -> None:
    """alpha_composite no admite destinos negativos: se recorta el mosaico."""
    left, top = max(0, -x), max(0, -y)
    if left >= tile.size[0] or top >= tile.size[1]:
        return
    overlay.alpha_composite(tile, (max(0, x), max(0, y)), (left, top))


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_page(content: bytes, mime_type: str, page_index: int, stamp: str | None) -> bytes:
    """Devuelve la página `page_index` (desde 0) como PNG, con marca de agua si hay `stamp`."""
    k = kind(mime_type)
    if k == "pdf":
        image = _render_pdf_page(content, page_index)
    elif k == "image":
        if page_index != 0:
            raise IndexError("La imagen tiene una sola página")
        image = Image.open(io.BytesIO(content))
        image.load()
    else:
        raise UnsupportedPreview("Este tipo de archivo no tiene vista protegida")
    return _png(_watermark(image, stamp) if stamp else image.convert("RGB"))


class _LruCache:
    """Caché pequeño de páginas renderizadas (sin marca) por (sha256, página)."""

    def __init__(self, size: int = 64) -> None:
        self._size = size
        self._items: OrderedDict[tuple[str, int], Image.Image] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, int]) -> Image.Image | None:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key].copy()
        return None

    def put(self, key: tuple[str, int], image: Image.Image) -> None:
        with self._lock:
            self._items[key] = image.copy()
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)


_cache = _LruCache()


def _render_pdf_page(content: bytes, page_index: int) -> Image.Image:
    key = (hashlib.sha256(content).hexdigest(), page_index)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    with _pdfium_lock:
        pdf = pdfium.PdfDocument(content)
        try:
            if not 0 <= page_index < len(pdf):
                raise IndexError("Página fuera de rango")
            page = pdf[page_index]
            image: Image.Image = page.render(scale=RENDER_SCALE).to_pil()
            page.close()
        finally:
            pdf.close()
    _cache.put(key, image)
    return image.copy()
