"""
Little script to make it serve a selection of examples as PyScript applications.
"""

import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import rendercanvas

try:
    from build.__main__ import main as build_main
except ImportError:
    msg = "This script needs the 'build' package. Get it with `pip install build` or similar."
    raise ImportError(msg) from None


available_examples = [
    "drag.html",
    "noise.html",
    "events.html",
    "demo.html",
]


example_list_items = [f"<li><a href='{name}'>{name}</a></li>" for name in available_examples]
html_index = f"""
<!doctype html>
<html>
<head>
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>RenderCanvas PyScript examples</title>
    <script type="module" src="https://pyscript.net/releases/2025.10.3/core.js"></script>
</head>
<body>
List of examples that run in PyScript:
<ul>{''.join(example_list_items)}</ul>
</body>
</html>
"""

html_template = """
<!doctype html>
<html>
<head>
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>example.py via PyScript</title>
    <script type="module" src="https://pyscript.net/releases/2025.10.3/core.js"></script>
</head>

<body>
    <a href="/">Back to list</a><br><br>

    <dialog id="loading" style='outline: none; border: none; background: transparent;'>
        <h1>Loading...</h1>
    </dialog>
    <script type="module">
        const loading = document.getElementById('loading');
        addEventListener('py:ready', () => loading.close());
        loading.showModal();
    </script>

    <canvas id="canvas" style="background:#aaa; width: 90%; height: 500px;"></canvas>
    <script type="py" src="example.py" ,
        config='{"packages": ["numpy", "sniffio", "rendercanvas"]}'>
    </script>
</body>

</html>
"""

root = os.path.abspath(os.path.join(__file__, "..", ".."))

short_version = ".".join(str(i) for i in rendercanvas.version_info[:3])
wheel_name = f"rendercanvas-{short_version}-py3-none-any.whl"
# todo: dont hardcode version in html example

if not (
    os.path.isfile(os.path.join(root, "rendercanvas", "__init__.py"))
    and os.path.isfile(os.path.join(root, "pyproject.toml"))
):
    raise RuntimeError("This script must run in a checkout repo of rendercanvas.")


def build_wheel():
    # pip.main(["wheel", "-w", os.path.join(root, "dist"), root])
    build_main(["-n", "-w", root])
    wheel_filename = os.path.join(root, "dist", wheel_name)
    assert os.path.isfile(wheel_filename), f"{wheel_name} does not exist"


class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa
        if self.path == "/":
            self.respond(200, html_index, "text/html")
        elif self.path.endswith(".whl"):
            filename = os.path.join(root, "dist", self.path.strip("/"))
            if os.path.isfile(filename):
                with open(filename, "rb") as f:
                    data = f.read()
                self.respond(200, data, "application/octet-stream")
            else:
                self.respond(404, "wheel not found")
        elif self.path.endswith(".html"):
            name = self.path.strip("/")
            if name in available_examples:
                pyname = name.replace(".html", ".py")
                html = html_template.replace("example.py", pyname)
                html = html.replace('"rendercanvas"', f'"./{wheel_name}"')
                self.respond(200, html, "text/html")
            else:
                self.respond(404, "example not found")
        elif self.path.endswith(".py"):
            name = self.path.strip("/")
            filename = os.path.join(root, "examples", name)
            if os.path.isfile(filename):
                with open(filename, "rb") as f:
                    data = f.read()
                self.respond(200, data, "text/plain")
            else:
                self.respond(404, "py file not found")
        else:
            self.respond(404, "not found")

    def respond(self, code, body, content_type="text/plain"):
        self.send_response(code)
        self.send_header("Content-type", content_type)
        self.end_headers()
        if isinstance(body, str):
            body = body.encode()
        self.wfile.write(body)


if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[-1])
        except ValueError:
            pass

    build_wheel()
    print("Opening page in web browser ...")
    webbrowser.open(f"http://localhost:{port}/")
    HTTPServer(("", port), MyHandler).serve_forever()
