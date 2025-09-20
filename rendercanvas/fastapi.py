"""
FastAPI canvas implementation. Renders offscreen but handles web events.
"""

__all__ = ["FastAPICanvas", "RenderCanvas", "loop"]

import time
import asyncio
from typing import Optional, Dict, Any

from .base import BaseCanvasGroup, BaseRenderCanvas
from ._events import EventType
from .asyncio import loop
from .offscreen import OffscreenRenderCanvas

import numpy as np


class FastAPICanvasGroup(BaseCanvasGroup):
    pass


class FastAPICanvas(BaseRenderCanvas):
    """A FastAPI-compatible canvas that renders offscreen but handles web events.

    This canvas combines offscreen rendering with event handling, allowing you to:
    - Render frames offscreen and serve them via HTTP
    - Receive click/pointer events from web clients
    - Integrate seamlessly with FastAPI's asyncio event loop

    Usage:
        canvas = FastAPICanvas(size=(800, 600))

        # In your FastAPI app:
        @app.get("/frame")
        async def get_frame():
            return canvas.get_frame_as_bytes()

        @app.post("/event")
        async def handle_event(event_data: dict):
            canvas.handle_web_event(event_data)
    """

    _rc_canvas_group = FastAPICanvasGroup(loop)

    def __init__(self, *args, size=(800, 600), pixel_ratio=1.0, **kwargs):
        super().__init__(*args, **kwargs)

        # Create internal offscreen canvas for rendering
        self._offscreen_canvas = OffscreenRenderCanvas(
            *args, pixel_ratio=pixel_ratio, **kwargs
        )

        # Canvas state
        self._logical_size = size
        self._pixel_ratio = pixel_ratio
        self._closed = False
        self._last_image = None

        # Event handling
        self._pending_events = []
        self._event_lock = asyncio.Lock()

        self._final_canvas_init()

    # %% Methods to implement RenderCanvas

    def _rc_gui_poll(self):
        # Process any pending events
        self._process_pending_events()

    def _rc_get_present_methods(self):
        return {
            "bitmap": {
                "formats": ["rgba-u8"],
            }
        }

    def _rc_request_draw(self):
        # Delegate to offscreen canvas
        self._offscreen_canvas._rc_request_draw()

    def _rc_force_draw(self):
        # Delegate to offscreen canvas
        self._offscreen_canvas._rc_force_draw()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        # Store the rendered frame
        self._last_image = np.frombuffer(data, np.uint8).reshape(data.shape)

    def _rc_get_physical_size(self):
        return int(self._logical_size[0] * self._pixel_ratio), int(
            self._logical_size[1] * self._pixel_ratio
        )

    def _rc_get_logical_size(self):
        return self._logical_size

    def _rc_get_pixel_ratio(self):
        return self._pixel_ratio

    def _rc_set_logical_size(self, width, height):
        self._logical_size = width, height
        self._offscreen_canvas._rc_set_logical_size(width, height)

    def _rc_close(self):
        self._closed = True
        self._offscreen_canvas._rc_close()

    def _rc_get_closed(self):
        return self._closed

    def _rc_set_title(self, title):
        pass  # Not applicable for web canvas

    def _rc_set_cursor(self, cursor):
        pass  # Not applicable for web canvas

    # %% FastAPI-specific methods

    async def handle_web_event(self, event_data: Dict[str, Any]):
        """Handle an event received from a web client.

        Args:
            event_data: Dictionary containing event information from the web client
        """
        async with self._event_lock:
            self._pending_events.append(event_data)

    def _process_pending_events(self):
        """Process any pending events from web clients."""
        while self._pending_events:
            event_data = self._pending_events.pop(0)
            self._translate_and_submit_event(event_data)

    def _translate_and_submit_event(self, event_data: Dict[str, Any]):
        """Translate web event data to canvas event format and submit it."""
        event_type = event_data.get("type")

        if event_type == "click":
            # Convert click to pointer_down + pointer_up sequence
            self.submit_event(
                {
                    "event_type": "pointer_down",
                    "x": event_data.get("x", 0),
                    "y": event_data.get("y", 0),
                    "button": 1,  # Left mouse button
                    "buttons": 1,
                    "modifiers": event_data.get("modifiers", []),
                    "ntouches": 0,
                    "touches": [],
                }
            )
            self.submit_event(
                {
                    "event_type": "pointer_up",
                    "x": event_data.get("x", 0),
                    "y": event_data.get("y", 0),
                    "button": 1,
                    "buttons": 0,
                    "modifiers": event_data.get("modifiers", []),
                    "ntouches": 0,
                    "touches": [],
                }
            )
        elif event_type == "mousemove":
            self.submit_event(
                {
                    "event_type": "pointer_move",
                    "x": event_data.get("x", 0),
                    "y": event_data.get("y", 0),
                    "button": 0,
                    "buttons": 0,
                    "modifiers": event_data.get("modifiers", []),
                    "ntouches": 0,
                    "touches": [],
                }
            )
        elif event_type == "wheel":
            self.submit_event(
                {
                    "event_type": "wheel",
                    "dx": event_data.get("deltaX", 0),
                    "dy": event_data.get("deltaY", 0),
                    "x": event_data.get("x", 0),
                    "y": event_data.get("y", 0),
                    "modifiers": event_data.get("modifiers", []),
                }
            )
        elif event_type == "resize":
            width = event_data.get("width", self._logical_size[0])
            height = event_data.get("height", self._logical_size[1])
            self._rc_set_logical_size(width, height)
            self.submit_event(
                {
                    "event_type": "resize",
                    "width": width,
                    "height": height,
                    "pixel_ratio": self._pixel_ratio,
                }
            )

    def get_frame_as_bytes(self) -> Optional[bytes]:
        """Get the current frame as PNG bytes for serving via HTTP."""
        if self._last_image is None:
            return None

        # Convert to PNG bytes (you might want to use PIL or similar)
        # For now, return the raw RGBA data
        return self._last_image.tobytes()

    def get_frame_as_array(self) -> Optional[np.ndarray]:
        """Get the current frame as a numpy array."""
        return self._last_image

    def draw(self):
        """Perform a draw and get the resulting image.

        This delegates to the internal offscreen canvas.
        """
        # Process any pending events first
        self._process_pending_events()

        # Delegate to offscreen canvas
        result = self._offscreen_canvas.draw()

        # Update our internal state
        if result is not None:
            self._last_image = np.frombuffer(result, np.uint8).reshape(result.shape)

        return result


# Make available under a name that is the same for all backends
RenderCanvas = FastAPICanvas
