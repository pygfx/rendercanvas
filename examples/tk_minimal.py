"""
tk minimal
----------

A minimal example of a Tkinter widget on top of a wgpu scene.
"""

import tkinter as tk
from tkinter import ttk

from rendercanvas.tk import RenderWidget
from rendercanvas.utils.cube import setup_drawing_sync


root = tk.Tk()
root.geometry("640x480")

container = ttk.Frame(root)
container.pack(fill="both", expand=True)

# the canvas we draw into
canvas = RenderWidget(container, update_mode="continuous")
canvas.place(x=0, y=0, relwidth=1, relheight=1)

# a frame around a button, in the middle of the panel
controls = ttk.Frame(container, padding=8)
controls.place(relx=0.5, rely=0.5, anchor="center")
label = ttk.Label(controls, text="I feel empty...")
label.pack()

clicks = 0
def on_click():
	global clicks
	clicks += 1
	label.configure(text=f"Clicked {clicks} times")

button = ttk.Button(controls, text="Click me", command=on_click)
button.pack(pady=5)

# ensure the controls (= button) are drawn after the RenderWidget
# this is not technically needed they were added to the container in the correct draw order
root.update_idletasks()
controls.lift()

draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)

root.mainloop()