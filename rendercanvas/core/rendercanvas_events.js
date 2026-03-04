//
// If you use this code, you want to avoid loading it in the global scope.
// So either put it in a `<script type='module>`, or wrap it in a "(function () {\n{JS}\n})();"

console.log("loading rc_events.js");


// Old code for touches that was in jupyter_rfb for a while:
//
// let touches = {};
// let ntouches = 0;
// for (let pointer_id in pointers) {
//     let pe = pointers[pointer_id]; // pointer event
//     let x = Number(pe.clientX - offset[0]);
//     let y = Number(pe.clientY - offset[1]);
//     let touch = { x: x, y: y, pressure: pe.pressure };
//     touches[pe.pointerId] = touch;
//     ntouches += 1;
// }
//
//
// To allow text-editing functionality *inside* a framebuffer, e.g. via imgui or something similar,
// we need events like arrow keys, backspace, and delete, with modifiers, and with repeat.
// I think it makes sense to send these like the code below, but this needs more thought ...
//
// if (event.key == "Backspace") {
//     let char_event = {
//         event_type: 'char',
//         data: null,
//         is_composing: false,
//         input_type: "deleteBackwards",
//         repeat: e.repeat,
//         time_stamp: get_time_stamp(),
//     };
//     this.send(char_event);
// }


const LOOKS_LIKE_MOBILE =
    /mobi|android|iphone|ipad|ipod|tablet/.test(
        navigator.userAgent.toLowerCase()
    );


const KEY_MAP = {
    'Ctrl': 'Control',
    'Del': 'Delete',
    'Esc': 'Escape',
};

const KEY_MOD_MAP = {
    'altKey': 'Alt',
    'ctrlKey': 'Control',
    'metaKey': 'Meta',
    'shiftKey': 'Shift',
};

const MOUSE_BUTTON_MAP = {
    0: 1,  // left
    1: 3,  //  middle/wheel
    2: 2,  // right
    3: 4,  // backwards
    4: 5,  // forwards
};


function getButtons(ev) {
    let button = MOUSE_BUTTON_MAP[ev.button] || 0;
    let buttons = [];
    for (let b of [0, 1, 2, 3, 4, 5]) { if ((1 << b) & ev.buttons) { buttons.push(b + 1); } }
    // TODO: should buttons not be mapped with MOUSE_BUTTON_MAP too?
    return [button, buttons]
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

class RCModel {

    // this.on('change:cursor', function (cursor) { for (let view of this.views) { view.setCursor(cursor) } }) }, this);
}

class RCEventManager_or_RCView {

    constructor(el, sizeCallback, submitEventCallback, options) {

        console.log(["Creating RCEventManager_or_RCView with", el]);

        const noop = (() => { })

        this.el = el;
        this._submitEventCallback = submitEventCallback || noop;
        this._sizeCallback = sizeCallback || noop;
        this.wheelThrottleTimeout = 20;

        this._focusElement = null;
        this._abortController = null;
        this._resizeObserver = null;

        // Set of throttler functions to send events at a friendly pace
        // TODO; throttle move event

        this._initElements();
        this._registerEvents()
        window.xx = this;
    }

    close() {
        const noop = (() => { })
        this._submitEventCallback = noop;
        this._sizeCallback = noop;

        if (this._focusElement) {
            this._focusElement.remove();
            this._focusElement = null;
        }
        // todo: test this
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }
        if (this._resizeObserver) {
            this._resizeObserver.disconnect()
            this._resizeObserver = null;
        }
        if (this._intersection_observer) {
            this._intersection_observer.disconnect();
            this._intersection_observer = null;
        }
    }

    _initElements() {
        // Prepare the element

        const el = this.el;
        el.tabIndex = -1;

        // Obtain container to put our hidden focus element.
        // Putting the focusElement as a child of the canvas prevents chrome from emitting input events.
        const focusElementContainerId = "rendercanvas-focus-element-container";
        let focusElementContainer = document.getElementById(focusElementContainerId);
        if (!focusElementContainer) {
            focusElementContainer = document.createElement("div");
            focusElementContainer.setAttribute("id", focusElementContainerId);
            focusElementContainer.style.position = "absolute";
            focusElementContainer.style.top = "0";
            focusElementContainer.style.left = "-9999px";
            document.body.appendChild(focusElementContainer);
        }

        // Create an element to which we transfer focus, so we can capture key events and prevent global shortcuts
        let focusElement = document.createElement("input");
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
        el.oncontextmenu = function (e) { if (!e.shiftKey) { e.preventDefault(); e.stopPropagation(); return false; } };

        // TODO: IntersectionObserver?
    }

    _registerEvents() {
        // Register events

        const el = this.el;
        const submitEventCallback = this._submitEventCallback;
        const sizeCallback = this._sizeCallback;
        this._abortController = new AbortController();
        const signal = this._abortController.signal; // to unregister/abort stuff


        // ----- resize ---------------

        this._resizeObserver = new ResizeObserver((entries) => {
            // The physical size is easy. The logical size can be much more tricky
            // to obtain due to all the CSS stuff. But the base class will just calculate that
            // from the physical size and the pixel ratio.

            // Select entry matching our element
            const ourEntries = entries.filter((entry) => entry.target.id === el.id);
            if (!ourEntries.length) { return; }

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
                    lsize = [
                        entry.contentRect.width,
                        entry.contentRect.height,
                    ];
                }
                psize = [
                    Math.floor(lsize[0] * ratio),
                    Math.floor(lsize[1] * ratio),
                ];
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
        let lastButtons = []

        el.addEventListener('pointerdown', (ev) => {
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
            if (!ev.altKey) { ev.preventDefault(); }

            // Collect info
            let [button, buttons] = getButtons(ev);
            let modifiers = getModifiers(ev);

            // Manage
            pointerToButton[ev.pointerId] = button
            lastButtons = buttons

            let event = {
                "event_type": "pointer_down",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": button,
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,  // TODO later: maybe via https://developer.mozilla.org/en-US/docs/Web/API/TouchEvent
                "touches": {},
                "time_stamp": getTimestamp(),
            }
            submitEventCallback(event);
        }, { signal });

        el.addEventListener('pointermove', (ev) => {
            // If this pointer is not down, but other pointers are, don't emit an event.
            if (pointerToButton[ev.pointerId] === undefined) {
                if (Object.keys(pointerToButton).length > 0) { return; }
            }

            // Collect info, use button that started this drag-action
            let [button, buttons] = getButtons(ev);
            let modifiers = getModifiers(ev);
            button = pointerToButton[ev.pointerId] || 0;

            // Manage
            lastButtons = buttons

            let event = {
                "event_type": "pointer_move",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": button,
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": getTimestamp(),
            }
            submitEventCallback(event);
        }, { signal });

        el.addEventListener('lostpointercapture', (ev) => {
            // This happens on pointer-up or pointer-cancel. We threat them the same.
            console.log('release')

            // Get info, use the button stat started the drag-action
            let modifiers = getModifiers(ev);
            let button = pointerToButton[ev.pointerId] || 0;
            let buttons = [];

            // Manage
            delete pointerToButton[ev.pointerId];
            lastButtons = buttons

            let event = {
                "event_type": "pointer_up",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": button,
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": getTimestamp(),
            }
            submitEventCallback(event);
        }, { signal });

        el.addEventListener('pointerenter', (ev) => {
            // If this pointer is not down, but other pointers are, don't emit an event.
            if (pointerToButton[ev.pointerId] === undefined) {
                if (Object.keys(pointerToButton).length > 0) { return; }
            }

            // Collect info, but use button 0. It usually is, and should be.
            let [button, buttons] = getButtons(ev);
            let modifiers = getModifiers(ev);
            button = 0;

            let event = {
                "event_type": "pointer_enter",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": button,
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": getTimestamp(),
            }
            submitEventCallback(event);
        }, { signal });

        el.addEventListener('pointerleave', (ev) => {
            // If this pointer is not down, but other pointers are, don't emit an event.
            if (pointerToButton[ev.pointerId] === undefined) {
                if (Object.keys(pointerToButton).length > 0) { return; }
            }

            // Collect info, but use button 0. It usually is, and should be.
            let [button, buttons] = getButtons(ev);
            let modifiers = getModifiers(ev);
            button = 0;

            let event = {
                "event_type": "pointer_leave",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": button,
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": getTimestamp(),
            }
            submitEventCallback(event);
        }, { signal });


        // ----- click ---------------

        // Click events are not pointer events. In most apps that this targets, click events
        // don't add much over pointer events. But double-click can be useful.
        el.addEventListener('dblclick', (ev) => {
            // Prevent default unless alt is pressed
            if (!ev.altKey) { ev.preventDefault(); }

            // Collect info
            let [button, buttons] = getButtons(ev);
            let modifiers = getModifiers(ev);

            let event = {
                "event_type": "double_click",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": button,
                "buttons": buttons,
                "modifiers": modifiers,
                // no touches here
                "time_stamp": getTimestamp(),
            }
            submitEventCallback(event);
        }, { signal });


        // ----- wheel ---------------

        let pendingWheelEvent = null;

        const sendWheelEvent = () => {
            if (pendingWheelEvent !== null) {
                let event = pendingWheelEvent;
                pendingWheelEvent = null;
                submitEventCallback(event);
            }
        };

        el.addEventListener('wheel', (ev) => {
            // Only scroll if we have focus
            if (window.document.activeElement !== this._focusElement) { return; }
            // Prevent default unless alt is pressed
            if (!ev.altKey) { ev.preventDefault(); }

            // Collect info
            let scales = [1 / window.devicePixelRatio, 16, 600];  // pixel, line, page
            let scale = scales[ev.deltaMode];
            let modifiers = getModifiers(ev);
            let buttons = [...lastButtons];

            // This event is throttled. We either update the pending event or create a new one
            if (pendingWheelEvent !== null &&
                arraysEqual(pendingWheelEvent.buttons, buttons) && arraysEqual(pendingWheelEvent.modifiers, modifiers)
            ) {
                pendingWheelEvent.dx += ev.deltaX * scale;
                pendingWheelEvent.dy += ev.deltaY * scale;
            } else {
                sendWheelEvent();  // Send previous (if any)
                pendingWheelEvent = {
                    "event_type": "wheel",
                    "x": ev.offsetX,
                    "y": ev.offsetY,
                    "dx": ev.deltaX * scale,
                    "dy": ev.deltaY * scale,
                    "buttons": buttons,
                    "modifiers": modifiers,
                    "time_stamp": getTimestamp(),
                }
                window.setTimeout(sendWheelEvent, this.wheelThrottleTimeout);
            }
        }, { signal });


        // ----- key ---------------

        this._focusElement.addEventListener('keydown', (ev) => {
            // Failsafe in case the element is deleted or detached.
            if (this.el.offsetParent === null) { return; }
            // Ignore repeated events (key being held down)
            if (ev.repeat) { return; }
            // No need for stopPropagation or preventDefault because we are in a text-input.

            let modifiers = getModifiers(ev);

            let event = {
                event_type: 'key_down',
                key: KEY_MAP[ev.key] || ev.key,
                modifiers: modifiers,
                time_stamp: getTimestamp(),
            };
            submitEventCallback(event);
        }, { signal });

        this._focusElement.addEventListener('keyup', (ev) => {
            if (this.el.offsetParent === null) { return; }

            let modifiers = getModifiers(ev);

            let event = {
                event_type: 'key_up',
                key: KEY_MAP[ev.key] || ev.key,
                modifiers: modifiers,
                time_stamp: getTimestamp(),
            };
            submitEventCallback(event);
        }, { signal });

        this._focusElement.addEventListener('input', (ev) => {
            // Failsafe in case the element is deleted or detached.
            if (this.el.offsetParent === null) { return; }
            // Prevent the text box from growing
            if (!ev.isComposing) { this.focus_el.value = ""; }

            let event = {
                event_type: 'char',
                data: ev.data,
                is_composing: ev.isComposing,
                input_type: ev.inputType,
                // repeat: ev.repeat,  // n.a.
                time_stamp: getTimestamp(),
            };
            submitEventCallback(event);
        }, { signal });

    }

    render(data) {
        // ...
    }

    setCursor(cursor) {
        this.el.style.cursor = cursor;
    }

}

window.rendercanvas_events = { RCModel, RCEventManager_or_RCView };
// export { RCModel, RCEventManager_or_RCView};
