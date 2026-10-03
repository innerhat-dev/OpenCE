#!/usr/bin/swift
import AppKit
import Foundation

// Render the versioned SVG with macOS' native SVG support. The PNG stores the
// logical point size, including for a 2x bitmap, so Finder can retain its layout.
func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

let arguments = CommandLine.arguments
guard arguments.count == 3 || arguments.count == 4 else {
    fail("Usage: render_background.swift <source.svg> <output.png> [scale: 1 or 2]")
}
let input = URL(fileURLWithPath: arguments[1]).standardizedFileURL
let output = URL(fileURLWithPath: arguments[2]).standardizedFileURL
let scale = arguments.count == 4 ? Int(arguments[3]) ?? 0 : 2
guard [1, 2].contains(scale), input.pathExtension.lowercased() == "svg",
      output.pathExtension.lowercased() == "png" else {
    fail("Choose an SVG source, PNG output, and scale 1 or 2.")
}
guard let source = NSImage(contentsOf: input), source.isValid,
      source.size.width == 680, source.size.height == 440 else {
    fail("Cannot read the 680 by 440 installer SVG.")
}
source.cacheMode = .never
let width = 680 * scale
let height = 440 * scale
guard let bitmap = NSBitmapImageRep(
    bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
    colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
), let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
    fail("Cannot allocate the installer background.")
}
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = context
context.cgContext.scaleBy(x: CGFloat(scale), y: CGFloat(scale))
source.draw(in: NSRect(x: 0, y: 0, width: 680, height: 440),
            from: .zero, operation: .copy, fraction: 1)
NSGraphicsContext.restoreGraphicsState()
bitmap.size = NSSize(width: 680, height: 440)
guard let data = bitmap.representation(using: .png, properties: [:]) else {
    fail("Cannot encode the installer background.")
}
do {
    try FileManager.default.createDirectory(at: output.deletingLastPathComponent(),
                                            withIntermediateDirectories: true)
    try data.write(to: output, options: .atomic)
} catch {
    fail("Cannot save the installer background: \(error.localizedDescription)")
}
print("Rendered \(width) by \(height) pixels at \(scale)x: \(output.path)")
