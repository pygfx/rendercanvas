"""
FastAPI
-------

Rendercanvas can do remote rendering as part of a web application.
It implements its own little ASGI application, that can be mounted
as part of a larger web application. This example demonstrates this
with the FastAPI web framework.

You can now run this like any AGI app, e.g. with uvicorn:

    uvicorn web_fastapi:app

"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from rendercanvas.http import RenderCanvas, asgi
from rendercanvas.utils.cube import setup_drawing_sync


# FastAPI code

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Test</title>
        </head>
        <body>
            <h1>Hello world</h1>
            <p>Head over to the <a href='rc/'>rendercanvas client<a></p>
        </body>
    </html>
    """


# Prepare a canvas to render something

canvas = RenderCanvas(
    title="The wgpu cube example on $backend", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


# Mount rendercanvas in the app
app.mount("/rc", asgi)
