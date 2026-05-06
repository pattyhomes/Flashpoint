import { createElement } from 'react'

const stopMapGesture = (event) => {
  event.stopPropagation()
}

export default function MapOverlay({ as: Component = 'div', className, children }) {
  // Do not stop click: button/link clicks must still bubble through React normally.
  return createElement(
    Component,
    {
      className,
      'data-map-overlay': true,
      onPointerDownCapture: stopMapGesture,
      onPointerMoveCapture: stopMapGesture,
      onPointerUpCapture: stopMapGesture,
      onPointerCancelCapture: stopMapGesture,
      onMouseDownCapture: stopMapGesture,
      onMouseMoveCapture: stopMapGesture,
      onMouseUpCapture: stopMapGesture,
      onTouchStartCapture: stopMapGesture,
      onTouchMoveCapture: stopMapGesture,
      onTouchEndCapture: stopMapGesture,
      onWheelCapture: stopMapGesture,
      onDragStartCapture: stopMapGesture,
    },
    children,
  )
}
