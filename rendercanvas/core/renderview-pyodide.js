/* global BaseRenderView Element HTMLDivElement HTMLCanvasElement */

/**
 * Adapter between the JS canvas and the Python canvas.
 */
class PyodideRenderView extends BaseRenderView {
  constructor (canvasElement, pycanvas) {
    let canvasId = null
    let viewElement = null
    let wrapperElement = null

    // Turn element id into the element
    if (typeof canvasElement === 'string' || canvasElement instanceof String) {
      canvasId = canvasElement
      canvasElement = document.getElementById(canvasId)
      if (!canvasElement) {
        throw new Error(`Given canvas id '${canvasId}' does not match an element in the DOM.`)
      }
    }

    // Get whether we have a wrapper of an actual canvas
    if (canvasElement instanceof HTMLCanvasElement) {
      viewElement = canvasElement
    } else if (canvasElement instanceof Element && canvasElement.classList.contains('renderview-wrapper')) {
      wrapperElement = canvasElement
      viewElement = document.createElement('canvas')
    } else {
      let repr = `${canvasElement}`
      if (canvasId) {
        repr = `id '${canvasId}' -> ` + repr
      }
      if (canvasElement instanceof HTMLDivElement) {
        repr += ' (Maybe you forgot to add class=\'renderview-wrapper\'?)'
      }
      throw new Error('Given canvas element does not look like a <canvas>: ' + repr)
    }

    super(viewElement, wrapperElement)
    this.pycanvas = pycanvas
    this.setThrottle(0)
  }

  onVisibleChanged (visible) {
    this.pycanvas._onVisibleChanged(visible)
  }

  onResize (physicalWidth, physicalHeight, pixelRatio) {
    // Set canvas physical size
    this.viewElement.width = physicalWidth
    this.viewElement.height = physicalHeight
    // Notify canvas, so the render code knows the size
    this.pycanvas._onResize(physicalWidth, physicalHeight, pixelRatio)
  }

  onEvent (event) {
    this.pycanvas._onEvent(event)
  }
}

window.PyodideRenderView = PyodideRenderView
