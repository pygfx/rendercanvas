"""
RenderCanvas Material with a Pygfx Texture Context?
=============
hacky way to use a rendercanvas like swap chain as a pygfx texture/material
since you can't create a pygfx texture from a wgpu texture without going to the cpu...
we create a pygfx texture and use it like an offscreen render target context with the rendercanvas api - this way you can render other apps into a pygfx scene!
"""

# modified from https://docs.pygfx.org/stable/_gallery/feature_demo/scene_in_a_scene.html#sphx-glr-gallery-feature-demo-scene-in-a-scene-py

# sphinx_gallery_pygfx_docs = 'screenshot'
# sphinx_gallery_pygfx_test = 'run'

import rendercanvas
from rendercanvas.auto import RenderCanvas, loop
from rendercanvas.offscreen import OffscreenRenderCanvas # there is no rendercanvas.offscreen.OffscreenCanvas namespace on it's own!
import pygfx as gfx
import pylinalg as la
import wgpu
from wgpu_shadertoy import Shadertoy
from pygfx.renderers.wgpu.engine.update import ensure_wgpu_object

# my thoughs/discovery process:
# First we create a an offscreen like rendercanvas, but the resources are pygfx textures
# maybe we can do a single resource and deconflict with views?
# maybe we actually want to do a PygfxTextureContext?
# perhaps we want the rendercanvas.WgpuContext as we still render to a wgpu texture like normally...
# maybe we do need GPUCanvasContext????

# name this WgpuContext because the instancing checks for the name... but this is technically the PygfxTextureContext!
class WgpuContext(rendercanvas.contexts.WgpuContext):
    def __new__(cls, present_info: dict, texture: gfx.Texture):
        # avoid the special behaviour?
        return object.__new__(cls)

    def __init__(self, present_info: dict, texture: gfx.Texture):
        # TODO: can you initialize this with a pygfx texture too?
        self.texture = texture
        # TODO: ensure this is a render attachment usage, and then refreush it's wgpu object?
        self._config = None # should already exist tho
        super().__init__(present_info)

    def _get_preferred_format(self, adapter=None) -> str:
        wgpu_format = gfx.renderers.wgpu.to_texture_format(self.texture.format)
        # so any kind of render pipeline setup by canvas like use is compatible with the texture we will provide
        return wgpu_format

    def configure(
        self,
        *,
        device: wgpu.GPUDevice,
        format: str,
        usage: str | int = "RENDER_ATTACHMENT",
        view_formats = (),
        alpha_mode: str = "opaque",) -> None:
        # TODO: make
        inp_config = wgpu.CanvasConfiguration(device=device, format=format, usage=usage, view_formats=view_formats, alpha_mode=alpha_mode) # just to make it type correctly
        assert inp_config.device == gfx.renderers.wgpu.get_shared().device, "you need to use the same device!"
        assert inp_config.format == self._get_preferred_format(), "the target format needs to be that of the existing texture, use the preferred format only!"
        # inp_config.usage |= wgpu.TextureUsage.RENDER_ATTACHMENT #always 0x10 anyway?
        # TODO: can we just ignore the rest?
        self._config = inp_config

    def _unconfigure(self) -> None:
        # don't think I need or want this?
        pass

    def _get_current_texture(self) -> wgpu.GPUTexture:
        if self.texture._wgpu_object is None:
            ensure_wgpu_object(self.texture)
        return self.texture._wgpu_object

    def _rc_present(self) -> None:
        # make ready for sync or something, so the actual pygfx renderer can use it!
        self.texture._gfx_mark_for_sync()
        return {"method": "screen"}

    def _rc_bitmap_present(self) -> None:
        self._rc_present()

    @property
    def physical_size(self) -> tuple[int, int]:
        return self.texture.size[0], self.texture.size[1]

texture1 = gfx.Texture(
    size=(512, 512, 1),
    dim=2,
    format="rgba8unorm",
    usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.TEXTURE_BINDING,
)

# the simplest wrapper, which likely produces a bunch of parts we don't need.
# TODO: actually translate world space events from pygfx into rendercanvas clicks and resizes etc (should be possible?)
class OffscreenPygfxRenderCanvas(OffscreenRenderCanvas):
    def __init__(self, texture: gfx.Texture, *args, **kwargs):
        self._canvas_context = WgpuContext(present_info={"method": "screen"}, texture=texture)
        kwargs["size"] = texture.size[0], texture.size[1]
        super().__init__(*args, **kwargs)

canvas1 = OffscreenPygfxRenderCanvas(texture=texture1) # the "offscreen" canvas that our external app will render to


# this code block is just to make it interesting, and also needs the branch where a custom device and be specified: https://github.com/pygfx/shadertoy/pull/58
# mainly just to show that it's theoretically possible to use an "existing app" by just changing the target canvas.
# picked something small for the example... plus this is also in GLSL
# shadertoy source: https://www.shadertoy.com/view/XtjfDy by FabriceNeyret2 CC-BY-NC-SA-3.0
shader_code = """
void mainImage(out vec4 O, vec2 u) {
    vec2 U = u+u - iResolution.xy;
    float T = 6.2832, l = length(U) / 30., L = ceil(l) * 6.,
          a = atan(U.x,U.y) - iTime * 2.*(fract(1e4*sin(L))-.5);
    O = .6 + .4* cos( floor(fract(a/T)*L) + vec4(0,23,21,0) )
        - max(0., 9.* max( cos(T*l), cos(a*L) ) - 8. ); }
"""
# shadertoy manually clamps alpha, so the transparency is undefined... but fun that it works!

shader = Shadertoy(shader_code, canvas=canvas1, device=gfx.renderers.wgpu.get_shared().device)


# Then create the pygfx actual scene, in the visible canvas

canvas = RenderCanvas(title="using pygfx texture as a rendertarget")  # for gallery scraper, bc we have 2 renderers
renderer2 = gfx.renderers.WgpuRenderer(canvas)
scene2 = gfx.Scene()

geometry2 = gfx.box_geometry(200, 200, 200)
material2 = gfx.MeshPhongMaterial(map=texture1)
cube2 = gfx.Mesh(geometry2, material2)
scene2.add(cube2)

camera2 = gfx.PerspectiveCamera(70, 16 / 9)
camera2.local.z = 400

scene2.add(gfx.AmbientLight(), camera2.add(gfx.DirectionalLight()))


def animate():
    rot = la.quat_from_euler((0.005, 0.01), order="xy")
    cube2.local.rotation = la.quat_mul(rot, cube2.local.rotation)

    shader._draw_frame() # this is a function in the wgpu-shadertoy lib, but if it were bound to the canvas request draw in a differnet way that should probably be called instead

    renderer2.render(scene2, camera2)
    renderer2.request_draw()


if __name__ == "__main__":
    renderer2.request_draw(animate)
    loop.run()
