"""
tk app
----------

An example demonstrating how to embed wgpu cube in a Tkinter widget / App.
"""

import time
import tkinter as tk
from tkinter import ttk

import numpy as np
import wgpu

from rendercanvas.tk import RenderWidget
from rendercanvas.utils import cube


ROTATION_SPEEDS = {
    "stopped": (0.0, 0.0, 0.0),
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
    "xy": (1.0, 0.7, 0.0),
    "xyz": (1.0, 0.7, 0.4),
}

_ROTATION_PLANES = {
    0: (1, 2),  # X axis
    1: (2, 0),  # Y axis
    2: (0, 1),  # Z axis
}


def rotation_matrix(axis, angle):
    """Return a 4x4 rotation matrix for axis 0, 1, or 2."""
    c, s = np.cos(angle), np.sin(angle)
    i, j = _ROTATION_PLANES[axis]
    matrix = np.eye(4, dtype=np.float32)
    matrix[i, i] = matrix[j, j] = c
    matrix[i, j], matrix[j, i] = -s, s
    return matrix


def setup_cube(canvas, mode, speed):
    """Create the cube renderer and return its draw and reset functions."""
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    device = adapter.request_device_sync()

    pipeline_layout, uniform_buffer, bind_groups = cube.create_pipeline_layout(device)
    pipeline = device.create_render_pipeline(
        **cube.get_render_pipeline_kwargs(canvas, device, pipeline_layout, None)
    )

    vertex_buffer = device.create_buffer_with_data(
        data=cube.vertex_data,
        usage=wgpu.BufferUsage.VERTEX,
    )
    index_buffer = device.create_buffer_with_data(
        data=cube.index_data,
        usage=wgpu.BufferUsage.INDEX,
    )

    context = canvas.get_context("wgpu")
    uniform_data = np.zeros((), dtype=cube.uniform_dtype)
    scale = np.diag([0.6, 0.6, 0.6, 1.0]).astype(np.float32)
    angles = np.array([-0.3, 0.0, 0.0], dtype=np.float32)
    last_time = time.perf_counter()

    def reset():
        nonlocal last_time
        angles[:] = (-0.3, 0.0, 0.0)
        last_time = time.perf_counter()

    def draw():
        nonlocal last_time

        now = time.perf_counter()
        dt = min(now - last_time, 0.1)
        last_time = now
        angles[:] += np.asarray(ROTATION_SPEEDS[mode.get()]) * speed.get() * dt

        transform = scale
        for axis, angle in enumerate(angles):
            transform = rotation_matrix(axis, angle) @ transform
        uniform_data["transform"] = transform
        device.queue.write_buffer(uniform_buffer, 0, uniform_data)

        encoder = device.create_command_encoder()
        render_pass = encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": context.get_current_texture().create_view(),
                    "resolve_target": None,
                    "clear_value": (0.05, 0.05, 0.05, 1.0),
                    "load_op": wgpu.LoadOp.clear,
                    "store_op": wgpu.StoreOp.store,
                }
            ]
        )
        render_pass.set_pipeline(pipeline)
        render_pass.set_vertex_buffer(0, vertex_buffer)
        render_pass.set_index_buffer(index_buffer, wgpu.IndexFormat.uint32)
        for index, bind_group in enumerate(bind_groups):
            render_pass.set_bind_group(index, bind_group)
        render_pass.draw_indexed(cube.index_data.size, 1, 0, 0, 0)
        render_pass.end()
        device.queue.submit([encoder.finish()])

    return draw, reset

dimensions = (1000,650)

root = tk.Tk()
root.title("rendercanvas + Tkinter widgets")
root.geometry("{0}x{1}".format(*dimensions))

mode = tk.StringVar(value="xy")
speed = tk.DoubleVar(value=1.0)

controls = ttk.Frame(root, padding=12)
controls.pack(side="left", fill="y")


ttk.Label(controls, text="Rotation", font=("TkDefaultFont", 10, "bold")).pack(
    anchor="w", pady=(0, 6)
)
for label, value in (
    ("Stopped", "stopped"),
    ("X axis", "x"),
    ("Y axis", "y"),
    ("Z axis", "z"),
    ("X + Y", "xy"),
    ("X + Y + Z", "xyz"),
):
    ttk.Radiobutton(controls, text=label, variable=mode, value=value).pack(
        anchor="w"
    )

ttk.Separator(controls).pack(fill="x", pady=12)
ttk.Label(controls, text="Speed").pack(anchor="w")
ttk.Scale(controls, from_=0.0, to=3.0, variable=speed, orient="horizontal").pack(
    fill="x"
)

canvas = RenderWidget(root, update_mode="continuous", width=800, height=600)
canvas.pack(side="right", fill="both", expand=True)

draw, reset_rotation = setup_cube(canvas, mode, speed)
ttk.Button(controls, text="Reset orientation", command=reset_rotation).pack(
    fill="x", pady=(12, 0)
)

canvas.request_draw(draw)
root.mainloop()