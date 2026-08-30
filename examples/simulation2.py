"""
Running a simulation, part 2
----------------------------

In this example, we run a simulation (Conway's Game of Life),
where the simulation and rendering both run at their own pace.
This is convenient when you want to run a simulation as fast as possible,
and just have the animation to 'keep an eye' on it.

To allow the simulation to run concurrently, we implememt it as an async
function that is added as a task. The animation simply renders the current
grid.

Note that this example uses the bitmap context, but this can be used
with wgpu in the same way.

Note that this works for any backend, and does not require the asyncio event loop.
"""

import numpy as np
from rendercanvas.pyside6 import RenderCanvas, loop
from scipy.signal import convolve2d
from rendercanvas.utils.asyncs import sleep as async_sleep


canvas = RenderCanvas()
canvas.set_update_mode("continuous", max_fps=20)


context = canvas.get_context("bitmap")


the_grid = np.zeros((10, 10), np.uint8)


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


async def simulation():
    global the_grid

    # Initialize a grid with a glider
    grid = np.zeros((30, 30), dtype=np.uint8)
    grid[1, 2] = grid[2, 3] = grid[3, 1] = grid[3, 2] = grid[3, 3] = 1

    # Keep stepping
    while True:
        grid = simulation_step(grid)

        # Sleep to allow other tasks to run (and keep the window alive)
        # This sleep time can be very small. We made it higher than necessary
        # to deliberately slow the animation down a bit.
        # If one simulation step takes a long time, you can add some sleep-calls
        # inside the simulation step as well (note that the simulation_step() must
        # then be made async).
        await async_sleep(0.01)

        # Set the grid so the animation can draw it. If the simulation
        # is fast, some steps can be skipped. ìf the simulation is slow,
        # the same grid may be rendered multiple times.
        the_grid = grid

        # You can also force a draw here, but if you want to see each frame you
        # should probably use the approach shown in the simulation1.py example.
        # canvas.force_draw()


@canvas.request_draw
def animate():
    context.set_bitmap(the_grid * 255)


loop.add_task(simulation)
loop.run()
