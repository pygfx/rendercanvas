"""
Running a simulation, part 1
----------------------------

In this example, we run a simulation (Conway's Game of Life),
where each rendered frame is one step in the simulation.
This is convenient when you want to see every step of an animation.

We could simply call this simulation_step() inside the animate function
to get one step on each frame. But in this example we wrapped
the simulation in a generator function.

Note that this example uses the bitmap context, but this can be used
with wgpu in the same way.
"""

import numpy as np

from rendercanvas.auto import RenderCanvas, loop
from scipy.signal import convolve2d


canvas = RenderCanvas()
canvas.set_update_mode("continuous", max_fps=10)


context = canvas.get_context("bitmap")


def simulation_step(grid: np.ndarray) -> np.ndarray:
    # Define the 3x3 convolution kernel for neighbor count
    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
    # Count live neighbors
    neighbors = convolve2d(grid, kernel, mode="same", boundary="wrap")
    # Apply the rules of Game of Life
    next_grid = ((grid == 1) & ((neighbors == 2) | (neighbors == 3))) | (
        (grid == 0) & (neighbors == 3)
    )
    return next_grid.astype(np.uint8)


def simulation():
    # Initialize a grid with a glider
    grid = np.zeros((30, 30), dtype=np.uint8)
    grid[1, 2] = grid[2, 3] = grid[3, 1] = grid[3, 2] = grid[3, 3] = 1

    # Keep stepping
    while True:
        grid = simulation_step(grid)
        yield grid


grid_generator = simulation()


@canvas.request_draw
def animate():
    grid = next(grid_generator)
    context.set_bitmap(grid * 255)


loop.run()
