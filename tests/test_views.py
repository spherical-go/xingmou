"""Board-view tiling must work without a hard-coded Linux font path."""

import io

from PIL import Image

import xingmou.player as player


def _png(width: int = 40, height: int = 30, color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "PNG")
    return buf.getvalue()


def test_tile_2x2_keeps_layout():
    images = [_png() for _ in range(4)]
    result = player._tile_2x2(
        images, ["Dark North", "Fertile South", "East Wilds", "West Gorge"]
    )
    grid = Image.open(io.BytesIO(result))
    assert grid.format == "PNG"
    assert grid.size == (80, 2 * (player.LABEL_H + 30))


def test_labels_are_actually_drawn():
    images = [_png() for _ in range(4)]
    result = player._tile_2x2(images, ["A", "B", "C", "D"])
    grid = Image.open(io.BytesIO(result)).convert("RGB")
    # The label bar is pure black except for the white label text.
    label_bar = grid.crop((0, 0, grid.width, player.LABEL_H))
    assert label_bar.getextrema()[0][1] > 0


def test_load_font_returns_a_measurable_font():
    # Pillow's FreeTypeFont is not an ImageFont subclass, so assert behaviour.
    font = player._load_font(20)
    assert font.getbbox("Dark North")[2] > 0


def test_bogus_font_override_does_not_crash(monkeypatch):
    monkeypatch.setenv("XINGMOU_FONT", "/nonexistent/xingmou-font.ttf")
    font = player._load_font(20)
    assert font.getbbox("Dark North")[2] > 0


def test_shrink_downscales_large_views():
    big = _png(2400, 1324)
    shrunk = player._shrink(big, max_side=900)
    assert max(Image.open(io.BytesIO(shrunk)).size) == 900


def test_shrink_leaves_small_views_untouched():
    small = _png(120, 60)
    assert player._shrink(small, max_side=900) is small
