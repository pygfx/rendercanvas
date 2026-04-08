import io
import struct
import zlib

import numpy as np

try:
    import simplejpeg
except ImportError:
    simplejpeg = None


CAN_JPEG = simplejpeg is not None


def encode_array(array, quality: int = 75):
    """Encode an image array to a compressed format.

    If the quality is 100, a PNG is returned. Otherwise, JPEG is
    preferred and PNG is used as a fallback. Returns (mimetype, bytes).
    """

    if quality >= 100 or not CAN_JPEG:
        # Drop alpha channel if it has one
        if array.ndim == 3 and array.shape[2] == 4:
            array = array[:, :, :3]
        mimetype = "image/png"
        data = encode_png(array)
    else:
        mimetype = "image/jpeg"
        data = encode_jpeg(array, quality)

    return mimetype, data


def encode_jpeg(array, quality: int = 75):
    """Encode an image array to bytes to the jpeg format.

    The image shape must be NxM, NxMx3, or NxMx4.
    """

    if simplejpeg is None:
        raise RuntimeError("encode_jpeg() needs simplejpeg but it is not installed.")
    if not (isinstance(array, np.ndarray) and array.dtype == "uint8"):
        raise TypeError("encode_jpeg() requires an uint8 numpy array")

    # Fix and check shape and contiguity
    if array.ndim == 2:
        array = array.reshape(*array.shape, 1)
    if array.ndim == 3 and array.shape[2] == 1:
        colorspace = "GRAY"
        colorsubsampling = "Gray"
    elif array.ndim == 3 and array.shape[2] in (3, 4):
        colorspace = "RGBA"[: array.shape[2]]
        colorsubsampling = "444"  # 420 does not seem to help the compression much
    else:
        raise ValueError(
            f"encode_jpeg() expects an NxM, NxMx3, or NxMx4 array, but got {array.shape}"
        )

    # Make sure it is contiguous
    array = np.ascontiguousarray(array)

    # Encode!
    return simplejpeg.encode_jpeg(
        array,
        quality=quality,
        colorspace=colorspace,
        colorsubsampling=colorsubsampling,
        fastdct=True,
    )


def encode_png(array, level: int = 6):
    """Encode an image array to bytes to the png format.

    The image shape must be NxM, NxMx3, or NxMx4.
    The written image is in RGB or RGBA format, with 8 bit precision,
    zlib-compressed, without interlacing.
    """

    if not (isinstance(array, np.ndarray) and array.dtype == "uint8"):
        raise TypeError("encode_png() requires an uint8 numpy array")

    # Fix and check shape and contiguity
    if array.ndim == 3 and array.shape[2] == 1:
        array = array.reshape(*array.shape[:2])
    if array.ndim == 2:
        array3 = np.empty((*array.shape[:2], 3), np.uint8)
        array3[..., 0] = array
        array3[..., 1] = array
        array3[..., 2] = array
        array = array3
    elif array.ndim == 3 and array.shape[2] in (3, 4):
        pass
    else:
        raise ValueError(
            f"encode_png() expects an NxM, NxMx3, or NxMx4 array, but got {array.shape}"
        )

    # Get file object
    f = io.BytesIO()

    def add_chunk(data, name):
        name = name.encode("ASCII")
        crc = zlib.crc32(data, zlib.crc32(name))
        f.write(struct.pack(">I", len(data)))
        f.write(name)
        f.write(data)
        f.write(struct.pack(">I", crc & 0xFFFFFFFF))

    # Write ...

    # Header
    f.write(b"\x89PNG\x0d\x0a\x1a\x0a")

    # First chunk
    h, w, c = array.shape
    depth = 8
    ctyp = 0b0110 if c == 4 else 0b0010
    ihdr = struct.pack(">IIBBBBB", w, h, depth, ctyp, 0, 0, 0)
    add_chunk(ihdr, "IHDR")

    # Chunk with pixels. Just one chunk, no fancy filters.
    compressor = zlib.compressobj(level=level)
    compressed_data = []
    for row_index in range(array.shape[0]):
        row = np.ascontiguousarray(array[row_index])
        compressed_data.append(compressor.compress(b"\x00"))  # prepend filter bytes
        compressed_data.append(compressor.compress(row))
    compressed_data.append(compressor.flush())
    add_chunk(b"".join(compressed_data), "IDAT")

    # Closing chunk
    add_chunk(b"", "IEND")

    f.flush()
    return f.getvalue()
