"""
A tool so contexts that produce a bitmap can still render to screen.
"""

import sys
import wgpu


class BitmapPresentAdapter:
    """An adapter to present a bitmap to a canvas using wgpu.

    This adapter can be used by context objects that want to present a bitmap, when the
    canvas only supports presenting to screen.
    """

    def __init__(self, canvas, present_methods):
        # Init wgpu
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        device = self._device = adapter.request_device_sync(required_limits={})

        self._texture_helper = FullscreenTexture(device)

        # Create context
        backend_module = wgpu.gpu.__module__
        CanvasContext = sys.modules[backend_module].GPUCanvasContext  # noqa: N806
        self._context = CanvasContext(canvas, present_methods)
        self._context_is_configured = False

    def present_bitmap(self, bitmap):
        """Present the given bitmap to screen.

        Supported formats are "rgba-u8" and "i-u8" (grayscale).
        Returns the present-result dict produced by ``GPUCanvasContext.present()``.
        """

        self._texture_helper.set_texture_data(bitmap)

        if not self._context_is_configured:
            format = self._context.get_preferred_format(self._device.adapter)
            # We don't want an srgb texture, because we assume the input bitmap is already srgb.
            # AFAIK contexts always support both the regular and the srgb texture format variants
            if format.endswith("-srgb"):
                format = format[:-5]
            self._context.configure(device=self._device, format=format)

        target = self._context.get_current_texture().create_view()
        command_encoder = self._device.create_command_encoder()
        self._texture_helper.draw(command_encoder, target)
        self._device.queue.submit([command_encoder.finish()])

        return self._context.present()


class FullscreenTexture:
    """An object that helps rendering a texture to the full viewport."""

    def __init__(self, device):
        self._device = device
        self._pipeline_layout = None
        self._pipeline = None
        self._texture = None
        self._uniform_data = memoryview(bytearray(1 * 4)).cast("f")

    def set_texture_data(self, data):
        """Upload new data to the texture. Creates a new internal texture object if needed."""
        m = memoryview(data)

        texture_format = self._get_format_from_memoryview(m)
        texture_size = m.shape[1], m.shape[0], 1

        # Lazy init for the static stuff
        if self._pipeline_layout is None:
            self._create_uniform_buffer()
            self._create_pipeline_layout()

        # Need new texture?
        if (
            self._texture is None
            or self._texture.size != texture_size
            or texture_format != self._texture.format
        ):
            self._create_texture(texture_size, texture_format)
            self._create_bind_groups()

        # Update buffer data
        self._uniform_data[0] = 1 if texture_format.startswith("r8") else 4

        # Upload data
        self._update_texture(m)
        self._update_uniform_buffer()

    def _get_format_from_memoryview(self, m):
        # Check dtype
        if m.format == "B":
            dtype = "u8"
        else:
            raise ValueError(
                "Unsupported bitmap dtype/format '{m.format}', expecting unsigned bytes ('B')."
            )

        # Get color format
        color_format = None
        if len(m.shape) == 2:
            color_format = "i"
        elif len(m.shape) == 3:
            if m.shape[2] == 1:
                color_format = "i"
            elif m.shape[2] == 4:
                color_format = "rgba"
        if not color_format:
            raise ValueError(
                f"Unsupported bitmap shape {m.shape}, expecting a 2D grayscale or rgba image."
            )

        # Deduce wgpu texture format
        format_map = {
            "i-u8": wgpu.TextureFormat.r8unorm,
            "rgba-u8": wgpu.TextureFormat.rgba8unorm,
        }
        format = f"{color_format}-{dtype}"
        return format_map[format]

    def _create_uniform_buffer(self):
        device = self._device
        self._uniform_buffer = device.create_buffer(
            size=self._uniform_data.nbytes,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )

    def _update_uniform_buffer(self):
        device = self._device
        device.queue.write_buffer(self._uniform_buffer, 0, self._uniform_data)

    def _create_texture(self, size, format):
        device = self._device
        self._texture = device.create_texture(
            size=size,
            usage=wgpu.TextureUsage.COPY_DST | wgpu.TextureUsage.TEXTURE_BINDING,
            dimension=wgpu.TextureDimension.d2,
            format=format,
            mip_level_count=1,
            sample_count=1,
        )
        self._texture_view = self._texture.create_view()
        self._sampler = device.create_sampler()

    def _update_texture(self, texture_data):
        device = self._device
        size = texture_data.shape[1], texture_data.shape[0], 1
        device.queue.write_texture(
            {
                "texture": self._texture,
                "mip_level": 0,
                "origin": (0, 0, 0),
            },
            texture_data,
            {
                "offset": 0,
                "bytes_per_row": texture_data.strides[0],
            },
            size,
        )

    def _create_pipeline_layout(self):
        device = self._device
        bind_groups_layout_entries = [[]]

        bind_groups_layout_entries[0].append(
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.VERTEX | wgpu.ShaderStage.FRAGMENT,
                "buffer": {},
            }
        )
        bind_groups_layout_entries[0].append(
            {
                "binding": 1,
                "visibility": wgpu.ShaderStage.FRAGMENT,
                "texture": {},
            }
        )
        bind_groups_layout_entries[0].append(
            {
                "binding": 2,
                "visibility": wgpu.ShaderStage.FRAGMENT,
                "sampler": {},
            }
        )

        # Create the wgpu binding objects
        bind_group_layouts = []
        for layout_entries in bind_groups_layout_entries:
            bind_group_layout = device.create_bind_group_layout(entries=layout_entries)
            bind_group_layouts.append(bind_group_layout)

        self._bind_group_layouts = bind_group_layouts
        self._pipeline_layout = device.create_pipeline_layout(
            bind_group_layouts=bind_group_layouts
        )

    def _create_pipeline(self, target_texture_view):
        device = self._device
        texture_format = target_texture_view.texture.format
        shader = device.create_shader_module(code=shader_source)

        pipeline_kwargs = dict(
            layout=self._pipeline_layout,
            vertex={
                "module": shader,
                "entry_point": "vs_main",
            },
            primitive={
                "topology": wgpu.PrimitiveTopology.triangle_strip,
                "front_face": wgpu.FrontFace.ccw,
                "cull_mode": wgpu.CullMode.back,
            },
            depth_stencil=None,
            multisample=None,
            fragment={
                "module": shader,
                "entry_point": "fs_main",
                "targets": [
                    {
                        "format": texture_format,
                        "blend": {
                            "alpha": {},
                            "color": {},
                        },
                    }
                ],
            },
        )

        self._pipeline = device.create_render_pipeline(**pipeline_kwargs)

    def _create_bind_groups(self):
        device = self._device
        bind_groups_entries = [[]]
        bind_groups_entries[0].append(
            {
                "binding": 0,
                "resource": {
                    "buffer": self._uniform_buffer,
                    "offset": 0,
                    "size": self._uniform_buffer.size,
                },
            }
        )
        bind_groups_entries[0].append({"binding": 1, "resource": self._texture_view})
        bind_groups_entries[0].append({"binding": 2, "resource": self._sampler})

        bind_groups = []
        for entries, bind_group_layout in zip(
            bind_groups_entries, self._bind_group_layouts
        ):
            bind_groups.append(
                device.create_bind_group(layout=bind_group_layout, entries=entries)
            )
        self._bind_groups = bind_groups

    def draw(self, command_encoder, target_texture_view):
        """Draw the bitmap to given target texture view."""

        if self._pipeline is None:
            self._create_pipeline(target_texture_view)

        render_pass = command_encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": target_texture_view,
                    "resolve_target": None,
                    "clear_value": (0, 0, 0, 1),
                    "load_op": wgpu.LoadOp.clear,
                    "store_op": wgpu.StoreOp.store,
                }
            ],
        )

        render_pass.set_pipeline(self._pipeline)
        for bind_group_id, bind_group in enumerate(self._bind_groups):
            render_pass.set_bind_group(bind_group_id, bind_group)
        render_pass.draw(4, 1, 0, 0)
        render_pass.end()


shader_source = """
struct Uniforms {
    format: f32,
};
@group(0) @binding(0)
var<uniform> uniforms: Uniforms;

struct VertexInput {
    @builtin(vertex_index) vertex_index : u32,
};
struct VertexOutput {
    @location(0) texcoord: vec2<f32>,
    @builtin(position) pos: vec4<f32>,
};
struct FragmentOutput {
    @location(0) color : vec4<f32>,
};


@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var positions = array<vec2<f32>, 4>(
        vec2<f32>(-1.0,  1.0),
        vec2<f32>(-1.0, -1.0),
        vec2<f32>( 1.0,  1.0),
        vec2<f32>( 1.0, -1.0),
    );
    var texcoords = array<vec2<f32>, 4>(
        vec2<f32>(0.0, 0.0),
        vec2<f32>(0.0, 1.0),
        vec2<f32>(1.0, 0.0),
        vec2<f32>(1.0, 1.0),
    );
    let index = i32(in.vertex_index);
    var out: VertexOutput;
    out.pos = vec4<f32>(positions[index], 0.0, 1.0);
    out.texcoord = vec2<f32>(texcoords[index]);
    return out;
}

@group(0) @binding(1)
var r_tex: texture_2d<f32>;

@group(0) @binding(2)
var r_sampler: sampler;

@fragment
fn fs_main(in: VertexOutput) -> FragmentOutput {
    let value = textureSample(r_tex, r_sampler, in.texcoord);
    var color = vec4<f32>(value);
    if (uniforms.format == 1) {
        color = vec4<f32>(value.r, value.r, value.r, 1.0);
    } else if (uniforms.format == 2) {
        color = vec4<f32>(value.r, value.r, value.r, value.g);
    }
    // We assume that the input color is sRGB. We don't need to go to physical/linear
    // colorspace, because we don't need light calculations or anything. The
    // output texture format is a regular rgba8unorm (not srgb), so that no transform
    // happens as we write to the texture; the pixel values are already srgb.
    var out: FragmentOutput;
    out.color = color;
    return out;
}
"""
