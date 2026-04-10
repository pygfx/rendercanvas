/*************************************************************************************************
  renderview-client.js

  Code to use renderview in a remote browser (rendercanvas http backend).
  There are basically two approaches to take. Either use renderview-afm.js and re-use the render logic,
  but implement an AFM host. Or directly attach a RenderView to a websocket. I went for the latter. Even
  though that means duplicating some code, it looks like this leads to simpler and shorter code.

  *************************************************************************************************/

/* global BaseRenderView WebSocket */


const wrapperElement = document.getElementById('canvas')
const statusElement = document.getElementById('status')
let view = null
let websocket = null
let isActive = null

updateStatus()
openWebsocketConnection()
window.openWebsocketConnection = openWebsocketConnection


class ClientRenderView extends BaseRenderView {
    constructor(wrapperElement) {
        wrapperElement.classList.add('renderview-wrapper')

        // Create view element
        const viewElement = document.createElement('img')
        viewElement.decoding = 'sync'
        viewElement.loading = 'eager'
        viewElement.style.touchAction = 'none' // prevent default pan/zoom behavior
        viewElement.ondragstart = () => false // prevent browser's built-in image drag

        // Instantiate
        super(viewElement, wrapperElement)
        this.setThrottle(20) // 20ms -> max 50 move/wheel events per second

        this.frames = []
        this.imgUpdatePending = false
        this.lastSrc = null
    }

    onEvent(event) {
        if (websocket !== null) {
            websocket.send(JSON.stringify(event))
        }
    }

    requestAnimationFrame() {
        // Request an animation frame.
        // Before the anywidget refactor, we did this via a tiny delay, which supposedly made things more smooth,
        // but it also increases the delay for a frame to hit the screen, and limits the max fps, so let's not do that.
        if (!this.imgUpdatePending) {
            this.imgUpdatePending = true
            window.requestAnimationFrame(this.animate.bind(this))
        }
    }

    animate() {
        this.imgUpdatePending = false
        if (this.frames.length === 0) { return };

        // Pick the oldest frame from the stack, and get its source
        const frame = this.frames.shift()
        let newSrc
        if (frame.buffers && frame.buffers.length > 0) {
            const blob = new Blob([frame.buffers[0]], { type: frame.mimetype })
            newSrc = URL.createObjectURL(blob)
        } else {
            newSrc = frame.data_b64
        }

        // Revoke last objectURL
        URL.revokeObjectURL(this.lastSrc)
        this.lastSrc = newSrc

        // Update the image sources
        view.viewElement.src = newSrc
        view.viewElement.onload = this.requestAnimationFrame.bind(this)

        // Let the server know we processed the image (even if it's not shown yet)
        this.sendResponse(frame)
    }

    sendResponse(frame) {
        // Let Python know what we have at the frame.
        const event = { type: '_framefeedback', index: frame.index, timestamp: frame.timestamp, localtime: Date.now() / 1000 }
        this.onEvent(event)
    }
}

function updateStatus() {
    if (statusElement === null) { return }

    let activeText = ''
    if (isActive !== null) {
        activeText = isActive ? ' (active)' : '(passive)'
    }

    if (websocket === null) {
        statusElement.innerHTML = "<span style='color:#900'>?</span> Disconnected <button onclick='openWebsocketConnection()'>reconnect</button>"
    } else {
        statusElement.innerHTML = `<span style='color:#090'>+</span> Connected ${activeText}`
    }
}

function openWebsocketConnection() {
    const ws = new WebSocket('ws://' + window.location.host + window.location.pathname)

    ws.onopen = (e) => {
        console.log('websocket opened')
        websocket = ws
        window.websocket = ws // allow manual closing to mimic lost connection
        if (view === null) {
            view = new ClientRenderView(wrapperElement)
            console.log('created ClientRenderView')
        }
        updateStatus()
    }
    ws.onerror = (e) => {
        console.log(`websocket error: ${e}`)
        websocket = null
        updateStatus()
    }

    let pendingMsg
    ws.onmessage = (e) => {
        let msg = null

        // First some handling to support a message with buffers
        if (typeof e.data === 'string' || e.data instanceof String) {
            msg = JSON.parse(e.data)
            if (msg.nbuffers && msg.nbuffers > 0) {
                pendingMsg = msg
                pendingMsg.buffers = []
                msg = null
            } else {
                pendingMsg = null // discard unfinished pending message (if any)
            }
        } else { // Blob
            if (pendingMsg !== null) {
                pendingMsg.buffers.push(e.data)
                if (pendingMsg.buffers.length >= pendingMsg.nbuffers) {
                    msg = pendingMsg
                    pendingMsg = null
                }
            }
        }

        if (msg === null) { return }

        // Process message
        // console.log(msg)
        if (msg.type === 'framebufferdata') {
            view.frames.push(msg)
            view.requestAnimationFrame()
        } else if (msg.type === 'active') {
            isActive = msg.value
            updateStatus()
        } else if (msg.type === 'cursor') {
            view.setCursor(msg.value)
        }
    }

    ws.onclose = (e) => {
        console.log(`websocket closed: ${e.reason} (${e.code})`)
        websocket = null
        updateStatus()
    }
}
