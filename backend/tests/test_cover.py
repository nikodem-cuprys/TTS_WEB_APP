from PIL import Image

from app.video.cover import _SIZE, generate_cover


def test_generate_cover_produces_a_square_image_of_the_expected_size(tmp_path):
    path = generate_cover(tmp_path / "cover.png", title="My Book", author="An Author")
    assert path.is_file()

    img = Image.open(path)
    assert img.size == (_SIZE, _SIZE)
    assert img.mode == "RGB"


def test_generate_cover_without_author(tmp_path):
    path = generate_cover(tmp_path / "cover.png", title="Solo Title")
    assert path.is_file()
    Image.open(path).load()  # a corrupt/empty write would raise here


def test_generate_cover_handles_a_very_long_title_without_overflowing(tmp_path):
    long_title = " ".join(["Supercalifragilisticexpialidocious"] * 12)
    path = generate_cover(tmp_path / "cover.png", title=long_title, author="Author Name")
    assert path.is_file()
    Image.open(path).load()


def test_generate_cover_handles_empty_title(tmp_path):
    path = generate_cover(tmp_path / "cover.png", title="")
    assert path.is_file()
    Image.open(path).load()


def test_generate_cover_uses_theme_background_color(tmp_path):
    """A quick sanity check that this actually renders the dark/green theme, not
    Pillow's default white canvas — samples a background pixel far from any text."""
    path = generate_cover(tmp_path / "cover.png", title="X")
    img = Image.open(path).convert("RGB")
    corner_pixel = img.getpixel((10, 10))
    assert corner_pixel == (14, 16, 17)
