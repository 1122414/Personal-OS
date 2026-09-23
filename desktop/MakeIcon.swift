import AppKit
import Foundation

@main
struct MakeIcon {
    static func main() throws {
        guard CommandLine.arguments.count == 2 else { throw IconError.missingDirectory }
        let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        for (name, size) in [
            ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
            ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
            ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
            ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
            ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
        ] {
            try draw(size: size).write(to: directory.appendingPathComponent(name))
        }
    }

    static func draw(size: Int) throws -> Data {
        guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
                                            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                            isPlanar: false, colorSpaceName: .deviceRGB,
                                            bytesPerRow: 0, bitsPerPixel: 0),
              let graphics = NSGraphicsContext(bitmapImageRep: bitmap) else {
            throw IconError.cannotDraw
        }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = graphics
        let side = CGFloat(size)
        let bounds = NSRect(x: 0, y: 0, width: side, height: side)
        let inset = side * 0.025
        let shape = NSBezierPath(roundedRect: bounds.insetBy(dx: inset, dy: inset),
                                 xRadius: side * 0.22, yRadius: side * 0.22)
        shape.addClip()
        NSGradient(starting: NSColor(calibratedRed: 0.055, green: 0.13, blue: 0.20, alpha: 1),
                   ending: NSColor(calibratedRed: 0.36, green: 0.065, blue: 0.13, alpha: 1))?
            .draw(in: shape, angle: 135)

        let glow = NSBezierPath(ovalIn: NSRect(x: side * 0.12, y: side * 0.52,
                                               width: side * 0.78, height: side * 0.78))
        NSColor(calibratedRed: 0.30, green: 0.76, blue: 0.88, alpha: 0.12).setFill()
        glow.fill()

        let ring = NSBezierPath(ovalIn: bounds.insetBy(dx: side * 0.14, dy: side * 0.14))
        ring.lineWidth = max(1, side * 0.013)
        NSColor(calibratedRed: 0.72, green: 0.81, blue: 0.81, alpha: 0.65).setStroke()
        ring.stroke()

        let glyph = NSAttributedString(string: "♆", attributes: [
            .font: NSFont(name: "Times New Roman", size: side * 0.64) ?? NSFont.systemFont(ofSize: side * 0.64),
            .foregroundColor: NSColor(calibratedRed: 0.92, green: 0.97, blue: 0.98, alpha: 1),
        ])
        let measured = glyph.size()
        glyph.draw(at: NSPoint(x: (side - measured.width) / 2,
                               y: (side - measured.height) / 2 + side * 0.045))

        let border = NSBezierPath(roundedRect: bounds.insetBy(dx: inset + side * 0.008,
                                                               dy: inset + side * 0.008),
                                  xRadius: side * 0.21, yRadius: side * 0.21)
        border.lineWidth = max(1, side * 0.012)
        NSColor(calibratedRed: 0.79, green: 0.68, blue: 0.61, alpha: 0.8).setStroke()
        border.stroke()
        graphics.flushGraphics()
        NSGraphicsContext.restoreGraphicsState()
        guard let png = bitmap.representation(using: .png, properties: [:]) else { throw IconError.cannotDraw }
        return png
    }
}

enum IconError: Error { case missingDirectory, cannotDraw }
