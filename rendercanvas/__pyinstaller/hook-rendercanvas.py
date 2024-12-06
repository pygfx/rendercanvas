# ruff: noqa: N999

from PyInstaller.utils.hooks import collect_dynamic_libs

# Init variables that PyInstaller will pick up.
hiddenimports = []
datas = []
binaries = []

# Add modules that are safe to add, i.e. don't pull in dependencies that we don't want.
hiddenimports += ["asyncio", "rendercanvas.async", "rendercanvas.offscreen"]

# Since glfw does not have a hook like this, it does not include the glfw binary
# when freezing. We can solve this with the code below. Makes the binary a bit
# larger, but only marginally (less than 300kb).
try:
    import glfw  # noqa: F401
except ImportError:
    pass
else:
    hiddenimports += ["rendercanvas.glfw"]
    binaries += collect_dynamic_libs("glfw")
