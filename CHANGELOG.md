# Changelog / release notes

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Possible sections in each release:

* Added: for new features.
* Changed: for changes in existing functionality.
* Deprecated: for soon-to-be removed features.
* Removed: for now removed features.
* Fixed: for any bug fixes.
* Security: in case of vulnerabilities.


## [v3.0.0](https://github.com/pygfx/rendercanvas/releases/tag/v3.0.0) - 06-11-2026

### Notable API changes

* The `canvas.is_closed()` method, which was already deprecated, is removed, use `get_closed()` instead.
* Running a task with `loop.add_task()` now always runs on rendercanvas' own micro-framework, never on a native framework like asyncio, so you can only use `sleep` and `Event` from `rendercanvas.utils.asyncs`. Likewise, the `sleep` and `Event` from `rendercanvas.utils.asyncs` can no longer be used in e.g. asyncio.
* `loop.call_soon()` and `loop.call_later()` now return an object that allows canceling the callback.

### Merged PR's

* Fix two scheduling bugs by @almarklein in https://github.com/pygfx/rendercanvas/pull/246
* Refactor canvas and loop closing logic by @almarklein in https://github.com/pygfx/rendercanvas/pull/227
* Add comment for post-close polling by @almarklein in https://github.com/pygfx/rendercanvas/pull/248
* Support presenting to a native Wayland surface on Qt by @hmaarrfk in https://github.com/pygfx/rendercanvas/pull/233
* Tweak events example by @almarklein in https://github.com/pygfx/rendercanvas/pull/245
* Add text example by @almarklein in https://github.com/pygfx/rendercanvas/pull/251
* Feature request: Add callback submethod for data handling by @hmaarrfk in https://github.com/pygfx/rendercanvas/pull/252
* Ensure utf-8 encoding for anywidget by @Vipitis in https://github.com/pygfx/rendercanvas/pull/253
* enable stack switching with present method screen in pyodide by @Vipitis in https://github.com/pygfx/rendercanvas/pull/258
* Refactor async mechanics by @almarklein in https://github.com/pygfx/rendercanvas/pull/260
* Better readable stub.py by copying in the docstrings as comments by @almarklein in https://github.com/pygfx/rendercanvas/pull/261
* fix EventEmitter.remove_handler by @lkeegan in https://github.com/pygfx/rendercanvas/pull/264
* A variety of fixes by @almarklein in https://github.com/pygfx/rendercanvas/pull/262
* Fix flaky CI test (and allow overriding call_later impl for qt and wx) by @almarklein in https://github.com/pygfx/rendercanvas/pull/266
* Better performance for call_later_from_thread by @almarklein in https://github.com/pygfx/rendercanvas/pull/265
* Version 3.0 by @almarklein in https://github.com/pygfx/rendercanvas/pull/247

### New Contributors
* @lkeegan made their first contribution in https://github.com/pygfx/rendercanvas/pull/264

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.7.2...v3.0.0


## [v2.7.1](https://github.com/pygfx/rendercanvas/releases/tag/v2.7.1) - 21-07-2026

### What's Changed
* Two fixes for VSCode by @almarklein in https://github.com/pygfx/rendercanvas/pull/235


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.7.0...v2.7.1


## [v2.7.0](https://github.com/pygfx/rendercanvas/releases/tag/v2.7.0) - 17-07-2026

This release adds multiple new backends, and has many fixes and small improvements.

### New backends

* Add anywidget backend by @almarklein in https://github.com/pygfx/rendercanvas/pull/200
* Add http backend by @almarklein in https://github.com/pygfx/rendercanvas/pull/202
* Add terminal backend by @almarklein in https://github.com/pygfx/rendercanvas/pull/216

### Backend-specific fixes and improvements

* Update renderview by @almarklein in https://github.com/pygfx/rendercanvas/pull/205
* Update jupyter backend and support Marimo by @almarklein in https://github.com/pygfx/rendercanvas/pull/198
* Update renderview.js by @almarklein in https://github.com/pygfx/rendercanvas/pull/199
* Improve marimo detection by @almarklein in https://github.com/pygfx/rendercanvas/pull/201
* Resize and title support for Pyodide canvases by @almarklein in https://github.com/pygfx/rendercanvas/pull/196
* Performance boost for terminal backend by @almarklein in https://github.com/pygfx/rendercanvas/pull/222
* Fix that Qt update() and wx Refresh did not cause a new draw by @almarklein in https://github.com/pygfx/rendercanvas/pull/203
* Backends that use renderview.js now check valid event types by @almarklein in https://github.com/pygfx/rendercanvas/pull/208
* Consistent GLFW backend detection on hybrid Wayland/X11 systems by @mortacious in https://github.com/pygfx/rendercanvas/pull/210
* Fix that wx canvases dont get gc'd by @almarklein in https://github.com/pygfx/rendercanvas/pull/225
* Terminal: Mimick key release on non-kitty-keyboard terminals by @almarklein in https://github.com/pygfx/rendercanvas/pull/231

### Other changes

* Small improvement to error messages in asyncadapter by @almarklein in https://github.com/pygfx/rendercanvas/pull/212
* Fix HDR support by @almarklein in https://github.com/pygfx/rendercanvas/pull/213
* Tweak auto backend selection by @almarklein in https://github.com/pygfx/rendercanvas/pull/217
* Deal with cancelled draws from wgpu by @almarklein in https://github.com/pygfx/rendercanvas/pull/221
* Present can also be cancelled by @almarklein in https://github.com/pygfx/rendercanvas/pull/226
* List backends in readme by @almarklein in https://github.com/pygfx/rendercanvas/pull/223
* More backend tests by @almarklein in https://github.com/pygfx/rendercanvas/pull/219
* Fix bullet list in readme by @almarklein in https://github.com/pygfx/rendercanvas/pull/228
* Tweak contribution section in readme by @almarklein in https://github.com/pygfx/rendercanvas/pull/229
* Specify that bitmap does not have to match physical size by @almarklein in https://github.com/pygfx/rendercanvas/pull/224
* All backends use nearest interpolation when bitmap is smaller than physical size by @almarklein in https://github.com/pygfx/rendercanvas/pull/230

### New Contributors
* @mortacious made their first contribution in https://github.com/pygfx/rendercanvas/pull/210

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.6.3...v2.7.0


## [v2.6.3](https://github.com/pygfx/rendercanvas/releases/tag/v2.6.3) - 12-03-2026

### What's Changed
* Add more leeway on CI for macos runner by @almarklein in https://github.com/pygfx/rendercanvas/pull/191
* Add zenodo link by @almarklein in https://github.com/pygfx/rendercanvas/pull/192
* Fix drag example by @almarklein in https://github.com/pygfx/rendercanvas/pull/194
* Fix wx scrolling by @tlambert03 in https://github.com/pygfx/rendercanvas/pull/190


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.6.2...v2.6.3


## [v2.6.2](https://github.com/pygfx/rendercanvas/releases/tag/v2.6.2) - 09-03-2026

### What's Changed

* Prevent exceptions when closing wx canvas by @almarklein in https://github.com/pygfx/rendercanvas/pull/182
* Refactor to put core modules in subpackage by @almarklein in https://github.com/pygfx/rendercanvas/pull/184
* Add contribution guide by @almarklein in https://github.com/pygfx/rendercanvas/pull/187
* Always request a draw on a resize & bump patch version by @almarklein in https://github.com/pygfx/rendercanvas/pull/188


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.6.1...v2.6.2


## [v2.6.1](https://github.com/pygfx/rendercanvas/releases/tag/v2.6.1) - 18-02-2026

### What's Changed
* Detect Pyodide to avoid get_asyncgen_hooks by @almarklein in https://github.com/pygfx/rendercanvas/pull/179
* Update _version.py by @almarklein in https://github.com/pygfx/rendercanvas/pull/180


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.6.0...v2.6.1


## [v2.6.0](https://github.com/pygfx/rendercanvas/releases/tag/v2.6.0) - 05-02-2026

This release focuses on present methods (bitmap vs screen). The bitmap present method is now async, making it much more performant. And  there are changes in how the method is selected. One of these changes is that on Qt 'bitmap' is the default, which avoids many qt-specific issues.

### What's Changed

* Refactor how the present_method is selected by @almarklein in https://github.com/pygfx/rendercanvas/pull/169
* Better error message for typos in kwargs to RenderCanvas by @almarklein in https://github.com/pygfx/rendercanvas/pull/167
* Update copyright year by @almarklein in https://github.com/pygfx/rendercanvas/pull/170
* Also weigh preference of context in present-method selection by @almarklein in https://github.com/pygfx/rendercanvas/pull/171
* Async bitmap present by @almarklein in https://github.com/pygfx/rendercanvas/pull/138
* Qt and wx default to bitmap present by @almarklein in https://github.com/pygfx/rendercanvas/pull/175
* Add docs on P3 behaviour of qt by @almarklein in https://github.com/pygfx/rendercanvas/pull/177


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.5.2...v2.6.0


## [v2.5.2](https://github.com/pygfx/rendercanvas/releases/tag/v2.5.2) - 23-12-2025

### What's Changed
* Softer limits on ci to avoid spurious failures by @almarklein in https://github.com/pygfx/rendercanvas/pull/163
* Streamline internal sleep and call_later by @almarklein in https://github.com/pygfx/rendercanvas/pull/162
* Add more gui-specific tests and run on ci by @almarklein in https://github.com/pygfx/rendercanvas/pull/164
* Fix several warnings in tests by @almarklein in https://github.com/pygfx/rendercanvas/pull/165


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.5.1...v2.5.2


## [v2.5.1](https://github.com/pygfx/rendercanvas/releases/tag/v2.5.1) - 18-12-2025

### What's Changed
* Fix asyncadapter.Event by @almarklein in https://github.com/pygfx/rendercanvas/pull/160
* fix: Override Wx.RenderCanvas.set_logical_size by @gselzer in https://github.com/pygfx/rendercanvas/pull/159

### New Contributors
* @gselzer made their first contribution in https://github.com/pygfx/rendercanvas/pull/159

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.5.0...v2.5.1


## [v2.5.0](https://github.com/pygfx/rendercanvas/releases/tag/v2.5.0) - 17-12-2025

### What's Changed
* Add `loop.call_soon_threadsafe()` and re-implement precise sleep by @almarklein in https://github.com/pygfx/rendercanvas/pull/146
* Improvements to loop lifecycle by @almarklein in https://github.com/pygfx/rendercanvas/pull/152
* Run loop tests with more loop classes by @almarklein in https://github.com/pygfx/rendercanvas/pull/156
* Drop sniffio and improved limetime by @almarklein in https://github.com/pygfx/rendercanvas/pull/157


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.4.2...v2.5.0


## [v2.4.2](https://github.com/pygfx/rendercanvas/releases/tag/v2.4.2) - 19-11-2025

### What's Changed
* Update to readme by @almarklein in https://github.com/pygfx/rendercanvas/pull/147
* More fixes to the docs. by @almarklein in https://github.com/pygfx/rendercanvas/pull/149
* Make canvas.set_logical_size lazy again by @almarklein in https://github.com/pygfx/rendercanvas/pull/148

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.4.1...v2.4.2


## [v2.4.1](https://github.com/pygfx/rendercanvas/releases/tag/v2.4.1) - 14-11-2025

### Summary

This minor release fixes some regressions related to sizes that were introduced in earlier refactorings. It also brings back support for custom contexts (but not via the hook we had earlier).

### What's Changed

Fixes:

* Size inits as (1,1) and logical size is applied early by @almarklein in https://github.com/pygfx/rendercanvas/pull/141
* Better support for custom contexts by @almarklein in https://github.com/pygfx/rendercanvas/pull/142
* Resolve incompatible char events by @almarklein in https://github.com/pygfx/rendercanvas/pull/143
* Bump pyscript in docs and examples by @Vipitis in https://github.com/pygfx/rendercanvas/pull/136

Additions:

* Add notes on performance for Qt bitmap present by @almarklein in https://github.com/pygfx/rendercanvas/pull/139
* Allow displaying frame-time in ms in title ($ms instead of $fps) by @almarklein in https://github.com/pygfx/rendercanvas/pull/140


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.4.0...v2.4.1


## [v2.4.0](https://github.com/pygfx/rendercanvas/releases/tag/v2.4.0) - 10-11-2025


### Summary

Support for Pyodide!! 🚀 And laying foundation for improved remote contexts, by implementing the contexts here instead of in wgpu-py.

### What's Changed
* Also run unit tests without wgpu by @almarklein in https://github.com/pygfx/rendercanvas/pull/131
* Support for Pyodide and PyScript by @Vipitis in https://github.com/pygfx/rendercanvas/pull/115
* Implement own context classes by @almarklein in https://github.com/pygfx/rendercanvas/pull/127
* Refactor internal _set_size_info() by @almarklein in https://github.com/pygfx/rendercanvas/pull/132
* Small type tweaks by @almarklein in https://github.com/pygfx/rendercanvas/pull/133


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.3.0...v2.4.0


## [v2.3.0](https://github.com/pygfx/rendercanvas/releases/tag/v2.3.0) - 05-11-2025

### Summary

This release drops support for async event handlers, makes sure that the user-code is up-to-date with the canvas size before a draw, has better support for static typing, and much more ...

### What's Changed
* Drop support for py39 by @almarklein in https://github.com/pygfx/rendercanvas/pull/108
* Typed enums by @almarklein in https://github.com/pygfx/rendercanvas/pull/112
* Improve typing by @almarklein in https://github.com/pygfx/rendercanvas/pull/113
* Adjust high DPI scaling handling for Qt 6 to avoid deprecation warning by @hmaarrfk in https://github.com/pygfx/rendercanvas/pull/116
* Add logo to readme by @almarklein in https://github.com/pygfx/rendercanvas/pull/118
* Async event handlers are no longer allowed by @almarklein in https://github.com/pygfx/rendercanvas/pull/119
* Add example that shows dragging by @almarklein in https://github.com/pygfx/rendercanvas/pull/121
* Refactor resizing logic and avoid mismatch between last resize event and draw by @almarklein in https://github.com/pygfx/rendercanvas/pull/120
* Added support for set_pixel_ratio to offscreen canvas by @almarklein in https://github.com/pygfx/rendercanvas/pull/122
* Tweak internal resize logic by @almarklein in https://github.com/pygfx/rendercanvas/pull/128
* log_exception context manager avoids spamming by not logging every exception by @almarklein in https://github.com/pygfx/rendercanvas/pull/126
* Add docs on physical-size, logical-size and pixel-ratio to guide by @almarklein in https://github.com/pygfx/rendercanvas/pull/129

### New Contributors
* @hmaarrfk made their first contribution in https://github.com/pygfx/rendercanvas/pull/116

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.2.1...v2.3.0


## [v2.2.1](https://github.com/pygfx/rendercanvas/releases/tag/v2.2.1) - 15-09-2025

### What's Changed
* Fix for Wayland set_logical_size by @almarklein in https://github.com/pygfx/rendercanvas/pull/103
* Add some docs on pixel ratio by @almarklein in https://github.com/pygfx/rendercanvas/pull/104
* Update _version.py by @almarklein in https://github.com/pygfx/rendercanvas/pull/106
* Switch to trusted publishing for PyPI publish in CI by @EpicWink in https://github.com/pygfx/rendercanvas/pull/110
* Reach FPS closer to max_fps on Windows by @almarklein in https://github.com/pygfx/rendercanvas/pull/109

### New Contributors
* @EpicWink made their first contribution in https://github.com/pygfx/rendercanvas/pull/110

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.2.0...v2.2.1


## [v2.2.0](https://github.com/pygfx/rendercanvas/releases/tag/v2.2.0) - 30-06-2025

### What's Changed
* Do not emit repeated `key_down` and `key_up` events by @SpicyRicecaker in https://github.com/pygfx/rendercanvas/pull/94
* fix PageUp key event by @Vipitis in https://github.com/pygfx/rendercanvas/pull/96
* Allow unparented WxRenderWidget by @almarklein in https://github.com/pygfx/rendercanvas/pull/92
* Allow user to select preferred format for offscreen canvas by @almarklein in https://github.com/pygfx/rendercanvas/pull/97
* Disallow max_fps=-1 by @almarklein in https://github.com/pygfx/rendercanvas/pull/99

### New Contributors
* @SpicyRicecaker made their first contribution in https://github.com/pygfx/rendercanvas/pull/94
* @Vipitis made their first contribution in https://github.com/pygfx/rendercanvas/pull/96

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.1.2...v2.2.0


## [v2.1.2](https://github.com/pygfx/rendercanvas/releases/tag/v2.1.2) - 14-05-2025

### What's Changed
* Fix pointer up outside glfw window by @almarklein in https://github.com/pygfx/rendercanvas/pull/90


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.1.1...v2.1.2


## [v2.1.1](https://github.com/pygfx/rendercanvas/releases/tag/v2.1.1) - 13-05-2025

### What's Changed
* Fix that set_update_mode does not work for wrapper canvases by @almarklein in https://github.com/pygfx/rendercanvas/pull/87


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.1.0...v2.1.1


## [v2.1.0](https://github.com/pygfx/rendercanvas/releases/tag/v2.1.0) - 13-05-2025

### What's Changed
* Prevent jupyter backend from submitting events that rendercanvas does not (yet) know by @almarklein in https://github.com/pygfx/rendercanvas/pull/82
* Add pointer_enter and pointer_leave events by @almarklein in https://github.com/pygfx/rendercanvas/pull/80
* Small optimization in checking event type by @almarklein in https://github.com/pygfx/rendercanvas/pull/84
* Add canvas.set_cursor() by @almarklein in https://github.com/pygfx/rendercanvas/pull/81
* Add canvas.set_update_mode() by @almarklein in https://github.com/pygfx/rendercanvas/pull/83
* Add type hints for the public API by @almarklein in https://github.com/pygfx/rendercanvas/pull/85


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.0.4...v2.1.0


## [v2.0.4](https://github.com/pygfx/rendercanvas/releases/tag/v2.0.4) - 15-04-2025

### What's Changed
* Better canvas cleanup, avoids segfaults on some systems with glfw+wgpu by @almarklein in https://github.com/pygfx/rendercanvas/pull/73
* Improve HDR support by @almarklein in https://github.com/pygfx/rendercanvas/pull/75

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.0.3...v2.0.4


## [v2.0.3](https://github.com/pygfx/rendercanvas/releases/tag/v2.0.3) - 26-03-2025

### What's Changed
* Hide bitmap warning when explicitly picked by @tlambert03 in https://github.com/pygfx/rendercanvas/pull/67
* Fix AttributeError on present() "fail" case by @rafaelbeckel in https://github.com/pygfx/rendercanvas/pull/68
* GLFW window start at correct size and draw during resize by @almarklein in https://github.com/pygfx/rendercanvas/pull/70
* Fix that WinIdChange event is in a different place on pyqt by @almarklein in https://github.com/pygfx/rendercanvas/pull/71

### New Contributors
* @tlambert03 made their first contribution in https://github.com/pygfx/rendercanvas/pull/67
* @rafaelbeckel made their first contribution in https://github.com/pygfx/rendercanvas/pull/68

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.0.2...v2.0.3


## [v2.0.2](https://github.com/pygfx/rendercanvas/releases/tag/v2.0.2) - 13-03-2025

### What's Changed
* Add a fully functioning pure-Python event loop by @almarklein in https://github.com/pygfx/rendercanvas/pull/53
* Fix bitmap adapter test by @almarklein in https://github.com/pygfx/rendercanvas/pull/59
* Dont get winId in qt and wx with bitmap present-method by @almarklein in https://github.com/pygfx/rendercanvas/pull/60
* Detect qt winid changes by @almarklein in https://github.com/pygfx/rendercanvas/pull/61


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.0.1...v2.0.2


## [v2.0.1](https://github.com/pygfx/rendercanvas/releases/tag/v2.0.1) - 05-01-2025

### What's Changed
* Add doc for migrating from wgpu.gui by @almarklein in https://github.com/pygfx/rendercanvas/pull/47
* fix set logical size in `JupyterRenderCanvas` by @kushalkolar in https://github.com/pygfx/rendercanvas/pull/50

### New Contributors
* @kushalkolar made their first contribution in https://github.com/pygfx/rendercanvas/pull/50

**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v2.0.0...v2.0.1


## [v2.0.0](https://github.com/pygfx/rendercanvas/releases/tag/v2.0.0) - 10-12-2024

This release marks a big step with regards to support for async:

* Refactor to go async by @almarklein in https://github.com/pygfx/rendercanvas/pull/41
* A bit more docs on async by @almarklein in https://github.com/pygfx/rendercanvas/pull/44

Further improvements:

* Handle ctrl-c by @almarklein in https://github.com/pygfx/rendercanvas/pull/25
* Add backend overview to docs by @almarklein in https://github.com/pygfx/rendercanvas/pull/43
* Fix rendering via bitmap adapter by @almarklein in https://github.com/pygfx/rendercanvas/pull/45
* Run examples on ci by @almarklein in https://github.com/pygfx/rendercanvas/pull/23

Changes to the API:

* Rename `is_closed()` to `get_closed()` by @almarklein in https://github.com/pygfx/rendercanvas/pull/26
* Remove `run` function by @almarklein in https://github.com/pygfx/rendercanvas/pull/42


**Full Changelog**: https://github.com/pygfx/rendercanvas/compare/v1.0.0...v2.0.0


## [v1.0.0](https://github.com/pygfx/rendercanvas/releases/tag/v1.0.0) - 18-11-2024

This marks the first release since this repo was rolled out of [wgpu-py](https://github.com/pygfx/wgpu-py). Compared to the version in wgpu-py, this code underwent the following changes:

* Obvious renaming, e.g. `WgpuCanvas` -> `RenderCanvas`.
* The `canvas.get_context()` must be called with `canvas.get_context("wgpu")`.
* The above means that the canvas can also be used by other rendering systems.
* We provide a bitmap-based context `canvas.get_context("bitmap")` out of the box.
* Add backends for qt libs, e.g. `from rendercanvas.pyside6 import RenderCanvas`.
* New scheduling system that is implemented generally instead of separate for each backend, and is generally better in several ways.
* Multiple different update modes are supported.
* The backend system is much better defined, and a few bugs were fixed in this process.
* Don't call `asyncio.get_event_loop()`, because its deprecated now.
