"""
Little script that:

* Builds the wheel.
* Start a tiny webserver to host html files for a selection of examples.
* Opens a webpage in the default browser.

Files are loaded from disk on each request, so you can leave the server running
and just update examples, update rendercanvas and build the wheel, etc.
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


# Examples to load as PyScript application
py_examples = [
    "drag.html",
    "noise.html",
    "events.html",
    "demo.html",
]

# Examples that are already html
html_examples = ["pyodide.html", "pyscript.html"]


def get_html_index():
    py_examples_list = [f"<li><a href='{name}'>{name}</a></li>" for name in py_examples]
    html_examples_list = [
        f"<li><a href='{name}'>{name}</a></li>" for name in html_examples
    ]

    html = f"""<!doctype html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width,initial-scale=1.0">
        <title>RenderCanvas PyScript examples</title>
        <script type="module" src="https://pyscript.net/releases/2025.10.3/core.js"></script>
    </head>
    <body>

    <a href='/build'>Rebuild the wheel</a><br><br>
    """

    html += "List of .py examples that run in PyScript:\n"
    html += f"<ul>{''.join(py_examples_list)}</ul><br>\n\n"

    html += "List of .html examples:\n"
    html += f"<ul>{''.join(html_examples_list)}</ul><br>\n\n"

    html += "</body>\n</html>\n"
    return html


html_index = get_html_index()


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

    <canvas id='rendercanvas' style="background:#aaa; width: 90%; height: 500px;"></canvas>
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
        elif self.path == "/build":
            try:
                build_wheel()
            except Exception as err:
                self.respond(500, str(err), "text/plain")
            else:
                html = f"Wheel build: {wheel_name}<br><br><a href='/'>Back to list</a>"
                self.respond(200, html, "text/html")
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
            if name in py_examples:
                pyname = name.replace(".html", ".py")
                html = html_template.replace("example.py", pyname)
                html = html.replace('"rendercanvas"', f'"./{wheel_name}"')
                self.respond(200, html, "text/html")
            elif name in html_examples:
                filename = os.path.join(root, "examples", name)
                with open(filename, "rb") as f:
                    html = f.read().decode()
                html = html.replace('"rendercanvas"', f'"./{wheel_name}"')
                self.respond(200, html, "text/html")
            else:
                self.respond(404, "example not found")
        elif self.path.endswith(".py"):
            filename = os.path.join(root, "examples", self.path.strip("/"))
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
