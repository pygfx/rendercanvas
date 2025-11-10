"""
A little script that serves browser-based example, using a wheel from the local rendercanvas.

* Examples that run rendercanvas fully in the browser in Pyodide / PyScript.
* Coming soon: examples that run on the server, with a client in the browser.

What this script does:

* Build the .whl for rendercanvas, so Pyodide can install the dev version.
* Start a tiny webserver to host html files for a selection of examples.
* Opens a webpage in the default browser.

Files are loaded from disk on each request, so you can leave the server running
and just update examples, update rendercanvas and build the wheel, etc.
"""

import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import flit
import rendercanvas


# Examples to load as PyScript application
py_examples = [
    "drag.html",
    "noise.html",
    "snake.html",
    "events.html",
]

# Examples that are already html
html_examples = [
    "pyodide.html",
    "pyscript.html",
]


root = os.path.abspath(os.path.join(__file__, "..", ".."))

short_version = ".".join(str(i) for i in rendercanvas.version_info[:3])
wheel_name = f"rendercanvas-{short_version}-py3-none-any.whl"


def get_html_index():
    """Create a landing page."""

    py_examples_list = [f"<li><a href='{name}'>{name}</a></li>" for name in py_examples]
    html_examples_list = [
        f"<li><a href='{name}'>{name}</a></li>" for name in html_examples
    ]

    html = """<!doctype html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width,initial-scale=1.0">
        <title>RenderCanvas PyScript examples</title>
        <script type="module" src="https://pyscript.net/releases/2025.11.1/core.js"></script>
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


# An html template to show examples using pyscript.
pyscript_template = """
<!doctype html>
<html>
<head>
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>example.py via PyScript</title>
    <script type="module" src="https://pyscript.net/releases/2025.11.1/core.js"></script>
</head>

<body>
    <a href="/">Back to list</a><br><br>

    <p>
    docstring
    </p>
    <dialog id="loading" style='outline: none; border: none; background: transparent;'>
        <h1>Loading...</h1>
    </dialog>
    <script type="module">
        const loading = document.getElementById('loading');
        addEventListener('py:ready', () => loading.close());
        loading.showModal();
    </script>

    <canvas id="canvas" style="background:#aaa; width: 90%; height: 480px;"></canvas>
    <script type="py" src="example.py" ,
        config='{"packages": ["numpy", "sniffio", "rendercanvas"]}'>
    </script>
</body>

</html>
"""


if not (
    os.path.isfile(os.path.join(root, "rendercanvas", "__init__.py"))
    and os.path.isfile(os.path.join(root, "pyproject.toml"))
):
    raise RuntimeError("This script must run in a checkout repo of rendercanvas.")


def build_wheel():
    toml_filename = os.path.join(root, "pyproject.toml")
    flit.main(["-f", toml_filename, "build", "--no-use-vcs", "--format", "wheel"])
    wheel_filename = os.path.join(root, "dist", wheel_name)
    assert os.path.isfile(wheel_filename), f"{wheel_name} does not exist"


def get_docstring_from_py_file(fname):
    filename = os.path.join(root, "examples", fname)
    docstate = 0
    doc = ""
    with open(filename, "rb") as f:
        while True:
            line = f.readline().decode()
            if docstate == 0:
                if line.lstrip().startswith('"""'):
                    docstate = 1
            else:
                if docstate == 1 and line.lstrip().startswith(("---", "===")):
                    docstate = 2
                    doc = ""
                elif '"""' in line:
                    doc += line.partition('"""')[0]
                    break
                else:
                    doc += line

    return doc.replace("\n\n", "<br><br>")


class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
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
                html = pyscript_template.replace("example.py", pyname)
                html = html.replace('"rendercanvas"', f'"./{wheel_name}"')
                html = html.replace("docstring", get_docstring_from_py_file(pyname))
                self.respond(200, html, "text/html")
            elif name in html_examples:
                filename = os.path.join(root, "examples", name)
                with open(filename, "rb") as f:
                    html = f.read().decode()
                html = html.replace('"rendercanvas"', f'"./{wheel_name}"')
                html = html.replace(
                    "<body>", "<body><a href='/'>Back to list</a><br><br>"
                )
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
