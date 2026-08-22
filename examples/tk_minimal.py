"""
tk minimal
----------

A minimal example of a Tkinter widget on top of a wgpu scene.
"""

from tkinter import ttk

from rendercanvas.tk import RenderCanvas
from rendercanvas.utils.cube import setup_drawing_sync

# the canvas we draw into
window = RenderCanvas(update_mode="continuous")

# a frame around a button, in the middle of the panel
controls = ttk.Frame(window, padding=8)
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

# ensure the controls (= button) are drawn after the RenderCanvas
# this is not technically needed they were added to the container in the correct draw order
window.update_idletasks()
controls.lift()

draw_frame = setup_drawing_sync(window)
window.request_draw(draw_frame)

window.set_title("TEST")
window.mainloop()
