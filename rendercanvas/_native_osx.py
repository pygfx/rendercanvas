"""

This uses rubicon to load objc classes, mainly for Cocoa (MacOS's
windowing API). For rendering to bitmap we follow the super-fast
approach of creating an IOSurface that is wrapped in a Metal texture.
On Apple silicon, the memory for that texture is in RAM, so we can write
directly to the texture, no copies. This approach is used by e.g. video
viewers.

However, because Python (via Rubicon) cannot pass or create pure C-level
IOSurfaceRef pointers, which are required by Metal’s
newTextureWithDescriptor:iosurface:plane; Rubicon can only work with
actual Objective-C objects.

Therefore this code relies on a mirco objc libary that is shipped along
in rendercanvas. This dylib handles the C-level IOSurface creation and
wraps it in a proper MTLTexture that Python can safely use.
"""

# ruff: noqa - for now

import os
import time
import ctypes

import numpy as np  # TODO: no numpy
from rubicon.objc import ObjCClass, objc_method, ObjCInstance

from .base import BaseCanvasGroup, BaseRenderCanvas
from .asyncio import loop


__all__ = ["RenderCanvas", "CocoaRenderCanvas", "loop"]


NSApplication = ObjCClass("NSApplication")
NSWindow = ObjCClass("NSWindow")
NSObject = ObjCClass("NSObject")


# Application and window
app = NSApplication.sharedApplication


SHADER = """
#include <metal_stdlib>
using namespace metal;

struct VertexOut {
    float4 position [[position]];
    float2 texcoord;
};

vertex VertexOut vertex_main(uint vertexID [[vertex_id]]) {
    float2 pos[3] = {
        float2(-1.0, -1.0),
        float2( 3.0, -1.0),
        float2(-1.0,  3.0)
    };
    VertexOut out;
    out.position = float4(pos[vertexID], 0.0, 1.0);
    out.texcoord = (pos[vertexID] * float2(1.0, -1.0) + 1.0) * 0.5;
    return out;
}

fragment float4 fragment_main(VertexOut in [[stage_in]],
                            texture2d<float> tex [[texture(0)]],
                            sampler samp [[sampler(0)]]) {
    constexpr sampler linearSampler(address::clamp_to_edge, filter::linear);
    float4 color = tex.sample(linearSampler, in.texcoord);
    return color;
}
"""


class MetalRenderer(NSObject):
    @objc_method
    def initWithDevice_(self, device):  # -> ctypes.c_void_p:
        self.init()
        # self = ObjCInstance(send_message(self, "init"))
        if self is None:
            return None
        self.device = device
        self.queue = device.newCommandQueue()

        self.texture = None

        # --- Metal shader code ---

        options = {}
        error_placeholder = None  # ctypes.c_void_p()
        library = device.newLibraryWithSource_options_error_(
            SHADER, None, error_placeholder
        )
        if not library:
            print("Shader compile failed:", error_placeholder)
            return self

        vertex_func = library.newFunctionWithName_("vertex_main")
        frag_func = library.newFunctionWithName_("fragment_main")

        desc = ObjCClass("MTLRenderPipelineDescriptor").alloc().init()
        desc.vertexFunction = vertex_func
        desc.fragmentFunction = frag_func
        desc.colorAttachments.objectAtIndexedSubscript_(
            0
        ).pixelFormat = 80  # BGRA8Unorm

        self.pipeline = device.newRenderPipelineStateWithDescriptor_error_(
            desc, error_placeholder
        )
        if not self.pipeline:
            print("Pipeline creation failed:", error_placeholder)
        return self

    @objc_method
    def setTexture_(self, texture):
        self.texture = texture

    @objc_method
    def drawInMTKView_(self, view):
        drawable = view.currentDrawable
        if drawable is None:
            return

        passdesc = ObjCClass("MTLRenderPassDescriptor").renderPassDescriptor()
        passdesc.colorAttachments.objectAtIndexedSubscript_(
            0
        ).texture = drawable.texture
        passdesc.colorAttachments.objectAtIndexedSubscript_(0).loadAction = 2  # Clear
        passdesc.colorAttachments.objectAtIndexedSubscript_(0).storeAction = 1  # Store
        passdesc.colorAttachments.objectAtIndexedSubscript_(
            0
        ).clearColor = view.clearColor

        cmd_buf = self.queue.commandBuffer()
        enc = cmd_buf.renderCommandEncoderWithDescriptor_(passdesc)

        enc.setRenderPipelineState_(self.pipeline)
        enc.setFragmentTexture_atIndex_(self.texture, 0)

        enc.setRenderPipelineState_(self.pipeline)
        enc.drawPrimitives_vertexStart_vertexCount_(3, 0, 3)
        enc.endEncoding()
        cmd_buf.presentDrawable_(drawable)
        cmd_buf.commit()
        # cmd_buf.waitUntilCompleted()

    @objc_method
    def mtkView_drawableSizeWillChange_(self, view, newSize):
        # Update if needed
        # print("resize", newSize)
        pass


class CocoaCanvasGroup(BaseCanvasGroup):
    pass


class CocoaRenderCanvas(BaseRenderCanvas):
    """A native canvas for OSX using Cocoa."""

    _rc_canvas_group = CocoaCanvasGroup(loop)

    _helper_dylib = None

    def __init__(self, *args, present_method=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_minimized = False
        self._present_method = present_method

        # Define window style
        NSWindowStyleMaskTitled = 1 << 0
        NSBackingStoreBuffered = 2
        NSTitledWindowMask = 1 << 0
        NSClosableWindowMask = 1 << 1
        NSMiniaturizableWindowMask = 1 << 2
        NSResizableWindowMask = 1 << 3
        style_mask = (
            NSTitledWindowMask
            | NSClosableWindowMask
            | NSMiniaturizableWindowMask
            | NSResizableWindowMask
        )

        rect = (100, 100), (100, 100)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style_mask, NSBackingStoreBuffered, False
        )
        self._window.makeKeyAndOrderFront_(None)  # focus
        self._keep_notified_of_resizes()

        # Start out with no bitmap present enabled. Will do that jit when needed.
        self._texture = None
        self._renderer = None

        self._final_canvas_init()

    def _keep_notified_of_resizes(self):
        def update_size():
            pixel_ratio = self._window.screen.backingScaleFactor
            size = self._window.frame.size
            pwidth = int(size.width * pixel_ratio)
            pheight = int(size.height * pixel_ratio)
            print("new size", pwidth, pheight)
            self._set_size_info(pwidth, pheight, pixel_ratio)

        class WindowDelegate(NSObject):
            @objc_method
            def windowDidResize_(self, notification):
                update_size()

            @objc_method
            def windowDidChangeBackingProperties_(self, notification):
                update_size()

        delegate = WindowDelegate.alloc().init()
        self._window.setDelegate_(delegate)
        update_size()

    def _setup_for_bitmap_present(self):
        # Create the helper first, because it also creates the device
        self._create_surface_texture_array(1, 1)

        # # Create more components
        self._create_renderer()
        self._create_mtk_view()

        # TODO: move the _create_renderer, _create_mtk_view, and maybe _create_surface_texture_array to functions or a helper class
        # -> keep bitmap/metal logic more separate

    def _create_renderer(self):
        # Instantiate the renderer and set as delegate
        # renderer = MetalRenderer.alloc().init()
        self._renderer = MetalRenderer.alloc().initWithDevice_(self._device)

    def _create_mtk_view(self):
        # Create MTKView
        MTKView = ObjCClass("MTKView")
        mtk_view = MTKView.alloc().initWithFrame_device_(
            self._window.contentView.bounds, self._device
        )
        # Ensure we can write into the view's texture (not framebuffer-only) if we want to upload into it
        try:
            mtk_view.setFramebufferOnly_(False)
        except Exception:
            pass  # Not all setups require this call; ignore if not present

        # TODO: use RGBA
        # TODO: support yuv420p or something
        # Choose pixel format. We'll assume BGRA8Unorm for Metal.
        mtk_view.setColorPixelFormat_(80)  # MTLPixelFormatBGRA8Unorm

        self._window.setContentView_(mtk_view)
        mtk_view.setDelegate_(self._renderer)

        # ?? vsync?
        # mtk_view.enableSetNeedsDisplay = False
        # mtk_view.preferredFramesPerSecond = 60

        self._mtkView = mtk_view

    def _create_surface_texture_array(self, width, height):
        print("creating new texture")
        if CocoaRenderCanvas._helper_dylib is None:
            # Load our helper dylib to make its objc class available to rubicon.
            CocoaRenderCanvas._helper_dylib = ctypes.CDLL(
                os.path.abspath(
                    os.path.join(__file__, "..", "libMetalIOSurfaceHelper.dylib")
                )
            )

        # Init our little helper helper
        MetalIOSurfaceHelper = ObjCClass("MetalIOSurfaceHelper")
        self._helper = MetalIOSurfaceHelper.alloc().initWithWidth_height_(width, height)
        self._texture = self._helper.texture
        self._device = self._helper.device

        # Access CPU memory
        base_addr = self._helper.baseAddress()
        bytes_per_row = self._helper.bytesPerRow()

        # Map array onto the shared memory
        total_bytes = bytes_per_row * height
        array_type = ctypes.c_uint8 * total_bytes
        pixel_buf = array_type.from_address(base_addr.value)
        self._texture_array = np.frombuffer(
            pixel_buf, dtype=np.uint8, count=total_bytes
        )
        self._texture_array.shape = height, -1
        self._texture_array = self._texture_array[:, : width * 4]
        self._texture_array.shape = height, width, 4

        if self._renderer is not None:
            self._renderer.setTexture(self._texture)

    def _rc_gui_poll(self):
        for mode in ("kCFRunLoopDefaultMode", "NSEventTrackingRunLoopMode"):
            # Drain events (non-blocking). If we don't drain events, the animation becomes jaggy when e.g. the mouse moves.
            # TODO: this seems to work, but lets check what happens here
            while True:
                event = app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                    0xFFFFFFFFFFFFFFFF,  # all events
                    None,  # don't wait
                    mode,
                    True,
                )
                if event:
                    app.sendEvent_(event)
                else:
                    break

    def _paint(self):
        self._draw_frame_and_present()
        # app.updateWindows()  # I also want to update one

    def _rc_get_present_methods(self):
        methods = {
            "bitmap": {"formats": ["rgba-u8"]},
            "screen": {"platform": "cocoa", "window": self._window.ptr.value},
        }
        if self._present_method:
            methods = {
                key: val for key, val in methods.items() if key == self._present_method
            }
        return methods

    def _rc_request_draw(self):
        if not self._is_minimized:
            loop = self._rc_canvas_group.get_loop()
            loop.call_soon(self._paint)

    def _rc_force_draw(self):
        self._paint()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        if not self._texture:
            self._setup_for_bitmap_present()
        if data.shape[:2] != self._texture_array.shape[:2]:
            self._create_surface_texture_array(data.shape[1], data.shape[0])

        self._texture_array[:] = data
        # print("present bitmap", data.shape)
        # self._window.contentView.setNeedsDisplay_(True)
        # self._mtkView.setNeedsDisplay_(True)

    def _rc_set_logical_size(self, width, height):
        frame = self._window.frame
        frame.size.width = width
        frame.size.height = height
        self._window.setFrame_display_animate_(frame, True, False)

    def _rc_close(self):
        pass

    def _rc_get_closed(self):
        return False

    def _rc_set_title(self, title):
        self._window.setTitle_(title)

    def _rc_set_cursor(self, cursor):
        pass


# Make available under a common name
RenderCanvas = CocoaRenderCanvas


if __name__ == "__main__":
    win = Window()

    frame_index = 0
    while True:
        frame_index += 1
        # Drain events (non-blocking)
        event = app.nextEventMatchingMask_untilDate_inMode_dequeue_(
            0xFFFFFFFFFFFFFFFF,  # all events
            None,  # don't wait
            "kCFRunLoopDefaultMode",
            True,
        )
        if event:
            app.sendEvent_(event)

        update_texture(frame_index)

        app.updateWindows()

        # your own update / render logic here
        # (Metal drawInMTKView_ will get called by MTKView’s internal timer)
        time.sleep(1 / 120)  # e.g. 120 Hz pacing
