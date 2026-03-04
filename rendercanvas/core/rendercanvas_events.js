/*************************************************************************************************
    rendercanvas_events.js

    This module implements the rendercanvas event spec for canvases in a
    browser. It implements observers and event listeners and converts these into
    rendercanvas-specific event dicts. The code is written with little
    assumptions about the applications, so that it can be applied in different
    backends, e.g. pyodide, anywidget, remote-browser.

    Code that loads the script should avoid loading it in the global scope.
    Either by putting it in a ``<script type='module>``, or wrapping it in a
    ``(() => {\n{JS}\n})();``

    This code adheres to common JS practices and formatting, but it probably
    shows that rendercanvas is a Python project. For instance, the code uses
    camelCase, but Python's underscore prefix for private-by-convention
    attributes.

 *************************************************************************************************

    Old code for touches that was in jupyter_rfb for a while:

    let touches = {};
    let ntouches = 0;
    for (let pointer_id in pointers) {
        let pe = pointers[pointer_id]; * pointer event
        let x = Number(pe.clientX - offset[0]);
        let y = Number(pe.clientY - offset[1]);
        let touch = { x: x, y: y, pressure: pe.pressure };
        touches[pe.pointerId] = touch;
        ntouches += 1;
    }

    To allow text-editing functionality *inside* a framebuffer, e.g. via imgui or something similar,
    we need events like arrow keys, backspace, and delete, with modifiers, and with repeat.
    I think it makes sense to send these like the code below, but this needs more thought ...

    if (event.key == "Backspace") {
        let char_event = {
            event_type: 'char',
            data: null,
            is_composing: false,
            input_type: "deleteBackwards",
            repeat: e.repeat,
            time_stamp: get_time_stamp(),
        };
        this.send(char_event);

 *************************************************************************************************/

console.log("loading rendercanvas_events.js");

const LOOKS_LIKE_MOBILE = /mobi|android|iphone|ipad|ipod|tablet/.test(
    navigator.userAgent.toLowerCase(),
);

const KEY_MAP = {
    Ctrl: "Control",
    Del: "Delete",
    Esc: "Escape",
};

const KEY_MOD_MAP = {
    altKey: "Alt",
    ctrlKey: "Control",
    metaKey: "Meta",
    shiftKey: "Shift",
};

const MOUSE_BUTTON_MAP = {
    0: 1, // left
    1: 3, // middle/wheel
    2: 2, // right
    3: 4, // backwards
    4: 5, // forwards
};

function getButtons(ev) {
    // Note that ev.button has a historic awkward mapping, but ev.buttons is in the order that we want
    const button = MOUSE_BUTTON_MAP[ev.button] || 0;
    const buttons = [];
    for (const b of [0, 1, 2, 3, 4, 5]) {
        if ((1 << b) & ev.buttons) {
            buttons.push(b + 1);
        }
    }
    return [button, buttons];
}

function getModifiers(ev) {
    return Object.entries(KEY_MOD_MAP)
        .filter(([k]) => ev[k])
        .map(([, v]) => v);
}

function getTimestamp() {
    return Date.now() / 1000;
}

function arraysEqual(a, b) {
    return a.length === b.length && a.every((val, i) => val === b[i]);
}

function noop() { }

class RCModel {
    // this.on('change:cursor', function (cursor) { for (let view of this.views) { view.setCursor(cursor) } }) }, this);
}

class RCEventManager_or_RCView {
    constructor({
        el,
        sizeCallback,
        eventCallback,
        wheelThrottle = 20,
        moveThrottle = 20,
    }) {
        if (el === undefined || !(el instanceof Element)) {
            throw new Error("el must be given an an Element");
        }
        this.el = el;

        this._sizeCallback = sizeCallback || noop;
        this._eventCallback = eventCallback || noop;
        this.wheelThrottle = wheelThrottle || 0;
        this.moveThrottle = moveThrottle || 0;

        this._focusElement = null;
        this._abortController = null;
        this._resizeObserver = null;
        this._intersectionObserver = null;

        this._initElements();
        this._registerEvents();
    }

    close() {
        this._eventCallback = noop;
        this._sizeCallback = noop;

        if (this._focusElement) {
            this._focusElement.remove();
            this._focusElement = null;
        }
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        if (this._intersectionObserver) {
            this._intersectionObserver.disconnect();
            this._intersectionObserver = null;
        }
    }

    _initElements() {
        // Prepare the element

        const el = this.el;
        el.tabIndex = -1;

        // Obtain container to put our hidden focus element.
        // Putting the focusElement as a child of the canvas prevents chrome from emitting input events.
        const focusElementContainerId = "rendercanvas-focus-element-container";
        let focusElementContainer = document.getElementById(
            focusElementContainerId,
        );
        if (!focusElementContainer) {
            focusElementContainer = document.createElement("div");
            focusElementContainer.setAttribute("id", focusElementContainerId);
            focusElementContainer.style.position = "absolute";
            focusElementContainer.style.top = "0";
            focusElementContainer.style.left = "-9999px";
            document.body.appendChild(focusElementContainer);
        }

        // Create an element to which we transfer focus, so we can capture key events and prevent global shortcuts
        const focusElement = document.createElement("input");
        this._focusElement = focusElement;
        focusElement.type = "text";
        focusElement.tabIndex = -1;
        focusElement.autocomplete = "off";
        focusElement.autocorrect = "off";
        focusElement.autocapitalize = "off";
        focusElement.spellcheck = false;
        focusElement.style.width = "1px";
        focusElement.style.height = "1px";
        focusElement.style.padding = "0";
        focusElement.style.opacity = 0;
        focusElement.style.pointerEvents = "none";
        focusElementContainer.appendChild(focusElement);

        // Prevent context menu on RMB. Firefox still shows it when shift is pressed. It seems
        // impossible to override this (tips welcome!), so let's make this the actual behavior.
        el.oncontextmenu = function (e) {
            if (!e.shiftKey) {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }
        };
    }

    _registerEvents() {
        // Register events

        const el = this.el;
        const eventCallback = this._eventCallback;
        const sizeCallback = this._sizeCallback;
        this._abortController = new AbortController();
        const signal = this._abortController.signal; // to unregister/abort stuff

        // ----- visibility ---------------

        this._intersectionObserver = new IntersectionObserver(
            (entries, observer) => {
                // This gets called when one of the observed elements becomes visible/invisible.
                // Note that entries only contains the *changed* elements, so we keep track ourselves.
                for (const entry of entries) {
                    entry.target._rc_is_visible = entry.isIntersecting;
                    // TODO: actually use this, but need some multi-view logic. The observer is best combined between all views, I suppose?
                }
            },
        );
        this._intersectionObserver.observe(el);

        // ----- resize ---------------

        this._resizeObserver = new ResizeObserver((entries) => {
            // The physical size is easy. The logical size can be much more tricky
            // to obtain due to all the CSS stuff. But the base class will just calculate that
            // from the physical size and the pixel ratio.

            // Select entry matching our element
            const ourEntries = entries.filter((entry) => entry.target.id === el.id);
            if (!ourEntries.length) {
                return;
            }

            const entry = ourEntries[0];
            const ratio = window.devicePixelRatio;
            let psize;

            if (entry.devicePixelContentBoxSize) {
                psize = [
                    entry.devicePixelContentBoxSize[0].inlineSize,
                    entry.devicePixelContentBoxSize[0].blockSize,
                ];
            } else {
                // Some browsers don't support devicePixelContentBoxSize
                let lsize;
                if (entry.contentBoxSize) {
                    lsize = [
                        entry.contentBoxSize[0].inlineSize,
                        entry.contentBoxSize[0].blockSize,
                    ];
                } else {
                    lsize = [entry.contentRect.width, entry.contentRect.height];
                }
                psize = [Math.floor(lsize[0] * ratio), Math.floor(lsize[1] * ratio)];
            }

            // If the element does not set the size with its style, the canvas' width and height are used.
            // On hidpi screens this'd cause the canvas size to quickly increase with factors of 2 :)
            // Therefore we want to make sure that the style.width and style.height are set.
            const lsize = [psize[0] / ratio, psize[1] / ratio];
            if (!el.style.width) {
                el.style.width = `${lsize[0]}px`;
            }
            if (!el.style.height) {
                el.style.height = `${lsize[1]}px`;
            }

            // Set canvas physical size
            el.width = psize[0];
            el.height = psize[1];

            sizeCallback(psize[0], psize[1], ratio);
        });

        this._resizeObserver.observe(this.el);

        // ----- pointer ---------------

        // Current pointer ids, mapping to initial button
        const pointerToButton = {};

        // The last used buttons, so we can pass to wheel event
        let lastButtons = [];

        el.addEventListener(
            "pointerdown",
            (ev) => {
                // When pointer is down, set focus to the focus-element.
                if (!LOOKS_LIKE_MOBILE) {
                    this._focusElement.focus({ preventScroll: true, focusVisble: false });
                }
                // capture the pointing device.
                // Because we capture the event, there will be no other events when buttons are pressed down,
                // although they will end up in the 'buttons'. The lost/release will only get fired when all buttons
                // are released/lost. Which is why we look up the original button in our `pointers` list.
                el.setPointerCapture(ev.pointerId);
                // Prevent default unless alt is pressed
                if (!ev.altKey) {
                    ev.preventDefault();
                }

                // Collect info
                const [button, buttons] = getButtons(ev);
                const modifiers = getModifiers(ev);

                // Manage
                pointerToButton[ev.pointerId] = button;
                lastButtons = buttons;

                const event = {
                    event_type: "pointer_down",
                    x: ev.offsetX,
                    y: ev.offsetY,
                    button,
                    buttons,
                    modifiers,
                    ntouches: 0, // TODO later: maybe via https://developer.mozilla.org/en-US/docs/Web/API/TouchEvent
                    touches: {},
                    time_stamp: getTimestamp(),
                };
                eventCallback(event);
            },
            { signal },
        );

        let pendingMoveEvent = null;

        const sendMoveEvent = () => {
            if (pendingMoveEvent !== null) {
                const event = pendingMoveEvent;
                pendingMoveEvent = null;
                eventCallback(event);
            }
        };

        el.addEventListener(
            "pointermove",
            (ev) => {
                // If this pointer is not down, but other pointers are, don't emit an event.
                if (pointerToButton[ev.pointerId] === undefined) {
                    if (Object.keys(pointerToButton).length > 0) {
                        return;
                    }
                }

                // Collect info, use button that started this drag-action
                let [button, buttons] = getButtons(ev);
                const modifiers = getModifiers(ev);
                button = pointerToButton[ev.pointerId] || 0;

                // Manage
                lastButtons = buttons;

                // This event is throttled. We either update the pending event or create a new one
                if (
                    pendingMoveEvent !== null &&
                    arraysEqual(pendingMoveEvent.buttons, buttons) &&
                    arraysEqual(pendingMoveEvent.modifiers, modifiers)
                ) {
                    pendingMoveEvent.x = ev.offsetX;
                    pendingMoveEvent.y = ev.offsetY;
                } else {
                    const event = {
                        event_type: "pointer_move",
                        x: ev.offsetX,
                        y: ev.offsetY,
                        button,
                        buttons,
                        modifiers,
                        ntouches: 0,
                        touches: {},
                        time_stamp: getTimestamp(),
                    };
                    if (this.moveThrottle > 0) {
                        sendMoveEvent(); // Send previous (if any)
                        pendingMoveEvent = event;
                        window.setTimeout(sendMoveEvent, this.moveThrottle);
                    } else {
                        eventCallback(event);
                    }
                }
            },
            { signal },
        );

        el.addEventListener(
            "lostpointercapture",
            (ev) => {
                // This happens on pointer-up or pointer-cancel. We threat them the same.

                // Get info, use the button stat started the drag-action
                const modifiers = getModifiers(ev);
                const button = pointerToButton[ev.pointerId] || 0;
                const buttons = [];

                // Manage
                delete pointerToButton[ev.pointerId];
                lastButtons = buttons;

                const event = {
                    event_type: "pointer_up",
                    x: ev.offsetX,
                    y: ev.offsetY,
                    button,
                    buttons,
                    modifiers,
                    ntouches: 0,
                    touches: {},
                    time_stamp: getTimestamp(),
                };
                eventCallback(event);
            },
            { signal },
        );

        el.addEventListener(
            "pointerenter",
            (ev) => {
                // If this pointer is not down, but other pointers are, don't emit an event.
                if (pointerToButton[ev.pointerId] === undefined) {
                    if (Object.keys(pointerToButton).length > 0) {
                        return;
                    }
                }

                // Collect info, but use button 0. It usually is, and should be.
                let [button, buttons] = getButtons(ev);
                const modifiers = getModifiers(ev);
                button = 0;

                const event = {
                    event_type: "pointer_enter",
                    x: ev.offsetX,
                    y: ev.offsetY,
                    button,
                    buttons,
                    modifiers,
                    ntouches: 0,
                    touches: {},
                    time_stamp: getTimestamp(),
                };
                eventCallback(event);
            },
            { signal },
        );

        el.addEventListener(
            "pointerleave",
            (ev) => {
                // If this pointer is not down, but other pointers are, don't emit an event.
                if (pointerToButton[ev.pointerId] === undefined) {
                    if (Object.keys(pointerToButton).length > 0) {
                        return;
                    }
                }

                // Collect info, but use button 0. It usually is, and should be.
                let [button, buttons] = getButtons(ev);
                const modifiers = getModifiers(ev);
                button = 0;

                const event = {
                    event_type: "pointer_leave",
                    x: ev.offsetX,
                    y: ev.offsetY,
                    button,
                    buttons,
                    modifiers,
                    ntouches: 0,
                    touches: {},
                    time_stamp: getTimestamp(),
                };
                eventCallback(event);
            },
            { signal },
        );

        // ----- click ---------------

        // Click events are not pointer events. In most apps that this targets, click events
        // don't add much over pointer events. But double-click can be useful.
        el.addEventListener(
            "dblclick",
            (ev) => {
                // Prevent default unless alt is pressed
                if (!ev.altKey) {
                    ev.preventDefault();
                }

                // Collect info
                const [button, buttons] = getButtons(ev);
                const modifiers = getModifiers(ev);

                const event = {
                    event_type: "double_click",
                    x: ev.offsetX,
                    y: ev.offsetY,
                    button,
                    buttons,
                    modifiers,
                    // no touches here
                    time_stamp: getTimestamp(),
                };
                eventCallback(event);
            },
            { signal },
        );

        // ----- wheel ---------------

        let pendingWheelEvent = null;

        const sendWheelEvent = () => {
            if (pendingWheelEvent !== null) {
                const event = pendingWheelEvent;
                pendingWheelEvent = null;
                eventCallback(event);
            }
        };

        el.addEventListener(
            "wheel",
            (ev) => {
                // Only scroll if we have focus
                if (window.document.activeElement !== this._focusElement) {
                    return;
                }
                // Prevent default unless alt is pressed
                if (!ev.altKey) {
                    ev.preventDefault();
                }

                // Collect info
                const scales = [1 / window.devicePixelRatio, 16, 600]; // pixel, line, page
                const scale = scales[ev.deltaMode];
                const modifiers = getModifiers(ev);
                const buttons = [...lastButtons];

                // This event is throttled. We either update the pending event or create a new one
                if (
                    pendingWheelEvent !== null &&
                    arraysEqual(pendingWheelEvent.buttons, buttons) &&
                    arraysEqual(pendingWheelEvent.modifiers, modifiers)
                ) {
                    pendingWheelEvent.x = ev.offsetX;
                    pendingWheelEvent.y = ev.offsetY;
                    pendingWheelEvent.dx += ev.deltaX * scale;
                    pendingWheelEvent.dy += ev.deltaY * scale;
                } else {
                    const event = {
                        event_type: "wheel",
                        x: ev.offsetX,
                        y: ev.offsetY,
                        dx: ev.deltaX * scale,
                        dy: ev.deltaY * scale,
                        buttons,
                        modifiers,
                        time_stamp: getTimestamp(),
                    };
                    if (this.wheelThrottle > 0) {
                        sendWheelEvent(); // Send previous (if any)
                        pendingWheelEvent = event;
                        window.setTimeout(sendWheelEvent, this.wheelThrottle);
                    } else {
                        eventCallback(event);
                    }
                }
            },
            { signal },
        );

        // ----- key ---------------

        this._focusElement.addEventListener(
            "keydown",
            (ev) => {
                // Failsafe in case the element is deleted or detached.
                if (this.el.offsetParent === null) {
                    return;
                }
                // Ignore repeated events (key being held down)
                if (ev.repeat) {
                    return;
                }
                // No need for stopPropagation or preventDefault because we are in a text-input.

                const modifiers = getModifiers(ev);

                const event = {
                    event_type: "key_down",
                    key: KEY_MAP[ev.key] || ev.key,
                    modifiers,
                    time_stamp: getTimestamp(),
                };
                eventCallback(event);
            },
            { signal },
        );

        this._focusElement.addEventListener(
            "keyup",
            (ev) => {
                if (this.el.offsetParent === null) {
                    return;
                }

                const modifiers = getModifiers(ev);

                const event = {
                    event_type: "key_up",
                    key: KEY_MAP[ev.key] || ev.key,
                    modifiers,
                    time_stamp: getTimestamp(),
                };
                eventCallback(event);
            },
            { signal },
        );

        this._focusElement.addEventListener(
            "input",
            (ev) => {
                // Failsafe in case the element is deleted or detached.
                if (this.el.offsetParent === null) {
                    return;
                }
                // Prevent the text box from growing
                if (!ev.isComposing) {
                    this.focus_el.value = "";
                }

                const event = {
                    event_type: "char",
                    data: ev.data,
                    is_composing: ev.isComposing,
                    input_type: ev.inputType,
                    // repeat: ev.repeat,  // n.a.
                    time_stamp: getTimestamp(),
                };
                eventCallback(event);
            },
            { signal },
        );
    }

    render(data) {
        // ...
    }

    setCursor(cursor) {
        this.el.style.cursor = cursor;
    }
}

// Old-school export
window.rendercanvas_events = { RCModel, RCEventManager_or_RCView };
