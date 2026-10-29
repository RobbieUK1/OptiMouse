import QtQuick
import QtQuick.Shapes

// A vector pointer arrow with its hotspot at the item's top-left corner, so
// the enlarged cursor stays sharp at any size. `size` matches cursor-theme
// sizes: the arrow fills roughly the same height as a theme cursor of that size.
Item {
  id: root

  property real size: 24
  property color fillColor: "#000000"
  property color strokeColor: "#ffffff"

  // The path is drawn in a 13 × 20 unit box and scaled as a whole, outline
  // included.
  readonly property real unit: root.size * 0.85 / 20

  width: Math.ceil(13 * root.unit)
  height: Math.ceil(20 * root.unit)

  Shape {
    width: 13
    height: 20
    antialiasing: true
    preferredRendererType: Shape.CurveRenderer
    transform: Scale { xScale: root.unit; yScale: root.unit }

    ShapePath {
      fillColor: root.fillColor
      strokeColor: root.strokeColor
      strokeWidth: 1.4
      joinStyle: ShapePath.RoundJoin

      PathSvg {
        path: "M 0.7 0.7 L 0.7 17.2 L 4.6 13.3 L 7.3 19.3 L 10 18.1 L 7.4 12.2 L 12.6 12.2 Z"
      }
    }
  }
}
