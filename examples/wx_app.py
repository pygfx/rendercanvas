"""
wx app
------

An example demonstrating a wx app with a wgpu viz inside.
"""

import time

import wx
from rendercanvas.wx import RenderWidget

from rendercanvas.utils.cube import setup_drawing_sync


class Example(wx.Frame):
    def __init__(self):
        super().__init__(None, title="wgpu triangle embedded in a wx app")
        self.SetSize(640, 480)

        # Using present_method 'image' because it reports "The surface texture is suboptimal"
        self.canvas = RenderWidget(
            self, update_mode="continuous", present_method="bitmap"
        )
        self.button = wx.Button(self, -1, "Hello world")
        self.output = wx.StaticText(self)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.button, 0, wx.EXPAND)
        sizer.Add(self.canvas, 1, wx.EXPAND)
        sizer.Add(self.output, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.button.Bind(wx.EVT_BUTTON, self.OnClicked)

        # Force the canvas to be shown, so that it gets a valid handle.
        # Otherwise GetHandle() is initially 0, and getting a surface will fail.
        self.Show()

    def OnClicked(self, event):  # noqa: N802
        t = self.output.GetLabel()
        t += f"\nClicked at {time.time():0.1f}"
        self.output.SetLabel(t)


app = wx.App()
example = Example()

draw_frame = setup_drawing_sync(example.canvas)
example.canvas.request_draw(draw_frame)

app.MainLoop()
