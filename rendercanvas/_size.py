class SizeInfo(dict):
    """A dict with size information, for internal use.

    Handy to have a separate dict, so that it can be passed to objects that need it.
    Also allows canvases to create size callbacks without holding a ref to the canvas.
    """

    def __init__(self):
        super().__init__()
        self["physical_size"] = 1, 1
        self["native_pixel_ratio"] = 1.0
        self["canvas_pixel_ratio"] = 1.0
        self["total_pixel_ratio"] = 1.0
        self["logical_size"] = 1.0, 1.0
        self["changed"] = False

    def set_physical_size(self, width: int, height: int, pixel_ratio: float):
        """Must be called by subclasses when their size changes.

        The given pixel-ratio represents the 'native' pixel ratio. The canvas'
        zoom factor is multiplied with it to obtain the final pixel-ratio for
        this canvas.
        """
        self["physical_size"] = int(width), int(height)
        self["native_pixel_ratio"] = float(pixel_ratio)
        self._resolve_total_pixel_ratio_and_logical_size()

    def _resolve_total_pixel_ratio_and_logical_size(self):
        physical_size = self["physical_size"]
        native_pixel_ratio = self["native_pixel_ratio"]
        canvas_pixel_ratio = self["canvas_pixel_ratio"]

        total_pixel_ratio = native_pixel_ratio * canvas_pixel_ratio
        logical_size = (
            physical_size[0] / total_pixel_ratio,
            physical_size[1] / total_pixel_ratio,
        )

        self["total_pixel_ratio"] = total_pixel_ratio
        self["logical_size"] = logical_size

        self["changed"] = True

    def set_zoom(self, zoom: float):
        """Set the zoom factor, i.e. the canvas pixel ratio."""
        self["canvas_pixel_ratio"] = float(zoom)
        self._resolve_total_pixel_ratio_and_logical_size()
