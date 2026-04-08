"""Test the jpeg and png encoders for the remote backends."""

from rendercanvas.core import encoders
from rendercanvas.core.encoders import encode_array, encode_jpeg, encode_png
from testutils import run_tests
import pytest
import numpy as np


def get_random_im(*shape):
    """Get a random image."""
    return np.random.randint(0, 100, shape).astype(np.uint8)


def test_encode_array():
    """Test the encode_array function."""

    # This test assumes that simplejpeg is installed

    im = np.random.randint(0, 255, (100, 100, 3)).astype(np.uint8)

    # Basic check
    preamble, bb = encode_array(im)
    assert isinstance(preamble, str)
    assert isinstance(bb, bytes)
    assert "jpeg" in preamble and "png" not in preamble

    # Check compression
    preamble1, bb1 = encode_array(im, 90)
    preamble2, bb2 = encode_array(im, 30)
    assert len(bb2) < len(bb1)

    # Check quality 100
    preamble3, bb3 = encode_array(im, 100)
    assert len(bb3) > len(bb1)

    assert "jpeg" in preamble1 and "png" not in preamble1
    assert "jpeg" in preamble2 and "png" not in preamble1
    assert "png" in preamble3 and "jpeg" not in preamble3

    # Check that RGBA is made RGB
    im4 = np.random.randint(0, 255, (100, 100, 4)).astype(np.uint8)
    im3 = im4[:, :, :3]
    _, bb1 = encode_array(im4, 90)
    _, bb2 = encode_array(im3, 90)
    assert bb1 == bb2

    # Also for PNG mode
    _, bb1 = encode_array(im4, 100)
    _, bb2 = encode_array(im3, 100)
    assert bb1 == bb2

    # Check fallback - disable JPEG encoding, we get PNG
    encoders.CAN_JPEG = False
    try:
        preamble, bb = encode_array(im)
        assert isinstance(preamble, str)
        assert isinstance(bb, bytes)
        assert "png" in preamble and "jpeg" not in preamble

    finally:
        encoders.CAN_JPEG = True

    # Should be back to normal now
    preamble, bb = encode_array(im)
    assert "jpeg" in preamble and "png" not in preamble


def test_encode_jpeg():
    """Tests for encode_jpeg function."""

    _perform_checks(encode_jpeg, 90, 20)
    _perform_error_checks(encode_jpeg)


def test_encode_png():
    """Tests for encode_jpeg function."""

    _perform_checks(encode_png, 3, 9)
    _perform_error_checks(encode_png)


def _perform_checks(encode, c1, c2):

    # Works without compression/level param
    im = get_random_im(100, 100, 3)
    _bb0 = encode(im)

    # RGB
    bb1 = encode(im, c1)
    bb2 = encode(im, c2)
    assert isinstance(bb1, bytes)
    assert len(bb2) < len(bb1)

    # RGB non-contiguous
    im = get_random_im(100, 100, 3)
    bb1 = encode(im[20:-20, 20:-20, :], c1)
    bb2 = encode(im[20:-20, 20:-20, :], c2)
    assert isinstance(bb1, bytes)
    assert len(bb2) < len(bb1)

    # Gray1
    im = get_random_im(100, 100)
    bb1 = encode(im, c1)
    bb2 = encode(im, c2)
    assert isinstance(bb1, bytes)
    assert len(bb2) < len(bb1)

    # Gray2
    im = get_random_im(100, 100, 1)
    bb1 = encode(im, c1)
    bb2 = encode(im, c2)
    assert isinstance(bb1, bytes)
    assert len(bb2) < len(bb1)

    # Gray non-contiguous
    im = get_random_im(200, 200)
    bb1 = encode(im[20:-20, 20:-20], c1)
    bb2 = encode(im[20:-20, 20:-20], c2)
    assert isinstance(bb1, bytes)
    assert len(bb2) < len(bb1)


def _perform_error_checks(encode):
    # Just to verify that this is ok
    encode(get_random_im(10, 10, 3))

    with pytest.raises(TypeError):  # not a numpy array
        encode([1, 2, 3, 4])

    with pytest.raises(TypeError):  # not a numpy array
        encode(b"1234")

    with pytest.raises(ValueError):  # NxMx2?
        encode(get_random_im(10, 10, 2))

    with pytest.raises(TypeError):
        encode(get_random_im(10, 10, 3).astype(np.float32))


if __name__ == "__main__":
    run_tests(globals())
