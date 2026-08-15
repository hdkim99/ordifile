// Copyright 2026 hdkim99
// SPDX-License-Identifier: Apache-2.0

import AppKit
import Foundation
import ImageIO
import UniformTypeIdentifiers

struct WorkbookPreview: Decodable {
    let sheet_names: [String]
    let samples: [[String]]
    let peak_matrix: [[String]]
}

let arguments = CommandLine.arguments
guard arguments.count == 4 else {
    FileHandle.standardError.write(
        Data("Usage: render_demo_assets.swift TRANSCRIPT WORKBOOK_JSON OUTPUT_DIR\n".utf8)
    )
    exit(2)
}

let transcriptURL = URL(fileURLWithPath: arguments[1])
let workbookURL = URL(fileURLWithPath: arguments[2])
let outputURL = URL(fileURLWithPath: arguments[3], isDirectory: true)
let transcript = try String(contentsOf: transcriptURL, encoding: .utf8)
let workbook = try JSONDecoder().decode(
    WorkbookPreview.self,
    from: Data(contentsOf: workbookURL)
)

let navy = NSColor(calibratedRed: 0.055, green: 0.090, blue: 0.155, alpha: 1)
let navyLight = NSColor(calibratedRed: 0.090, green: 0.140, blue: 0.230, alpha: 1)
let blue = NSColor(calibratedRed: 0.110, green: 0.420, blue: 0.820, alpha: 1)
let cyan = NSColor(calibratedRed: 0.180, green: 0.760, blue: 0.850, alpha: 1)
let green = NSColor(calibratedRed: 0.250, green: 0.800, blue: 0.520, alpha: 1)
let offWhite = NSColor(calibratedRed: 0.955, green: 0.970, blue: 0.985, alpha: 1)
let muted = NSColor(calibratedRed: 0.620, green: 0.680, blue: 0.760, alpha: 1)

func bitmap(width: Int, height: Int) -> NSBitmapImageRep {
    guard let result = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: width,
        pixelsHigh: height,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ) else {
        fatalError("Unable to allocate bitmap")
    }
    result.size = NSSize(width: width, height: height)
    return result
}

func withContext(_ image: NSBitmapImageRep, draw: () -> Void) {
    NSGraphicsContext.saveGraphicsState()
    guard let context = NSGraphicsContext(bitmapImageRep: image) else {
        fatalError("Unable to create graphics context")
    }
    NSGraphicsContext.current = context
    draw()
    context.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()
}

func fill(_ rect: NSRect, color: NSColor, radius: CGFloat = 0) {
    color.setFill()
    let path = radius == 0
        ? NSBezierPath(rect: rect)
        : NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    path.fill()
}

func stroke(_ rect: NSRect, color: NSColor, radius: CGFloat = 0, width: CGFloat = 1) {
    color.setStroke()
    let path = radius == 0
        ? NSBezierPath(rect: rect)
        : NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    path.lineWidth = width
    path.stroke()
}

func text(
    _ value: String,
    x: CGFloat,
    top: CGFloat,
    canvasHeight: CGFloat,
    font: NSFont,
    color: NSColor,
    width: CGFloat? = nil,
    alignment: NSTextAlignment = .left
) {
    let style = NSMutableParagraphStyle()
    style.alignment = alignment
    style.lineBreakMode = .byTruncatingTail
    let attributes: [NSAttributedString.Key: Any] = [
        .font: font,
        .foregroundColor: color,
        .paragraphStyle: style,
    ]
    let height = font.ascender - font.descender + font.leading + 4
    let rect = NSRect(
        x: x,
        y: canvasHeight - top - height,
        width: width ?? 2_000,
        height: height
    )
    value.draw(in: rect, withAttributes: attributes)
}

func writePNG(_ image: NSBitmapImageRep, to url: URL) throws {
    guard let data = image.representation(using: .png, properties: [:]) else {
        fatalError("Unable to encode PNG")
    }
    try data.write(to: url, options: .atomic)
}

func terminalFrame(lines: [String], visible: Int) -> NSBitmapImageRep {
    let width = 1120
    let height = 660
    let image = bitmap(width: width, height: height)
    withContext(image) {
        fill(NSRect(x: 0, y: 0, width: width, height: height), color: navy)
        fill(NSRect(x: 45, y: 38, width: 1030, height: 584), color: navyLight, radius: 18)
        fill(NSRect(x: 45, y: 576, width: 1030, height: 46), color: NSColor.black.withAlphaComponent(0.18), radius: 18)
        for (index, color) in [NSColor.systemRed, NSColor.systemYellow, NSColor.systemGreen].enumerated() {
            fill(NSRect(x: 70 + CGFloat(index * 24), y: 592, width: 12, height: 12), color: color, radius: 6)
        }
        text(
            "Ordifile — actual CLI run",
            x: 160,
            top: 49,
            canvasHeight: CGFloat(height),
            font: NSFont.systemFont(ofSize: 16, weight: .semibold),
            color: offWhite
        )
        let terminalFont = NSFont.monospacedSystemFont(ofSize: 16, weight: .regular)
        let shown = Array(lines.prefix(visible))
        for (index, line) in shown.enumerated() {
            let color = line.hasPrefix("$") ? cyan : (line.hasPrefix("Status:") ? green : offWhite)
            text(
                line,
                x: 72,
                top: 102 + CGFloat(index * 23),
                canvasHeight: CGFloat(height),
                font: terminalFont,
                color: color,
                width: 970
            )
        }
        text(
            "Synthetic example data · source files stay unchanged",
            x: 72,
            top: 610,
            canvasHeight: CGFloat(height),
            font: NSFont.systemFont(ofSize: 13, weight: .medium),
            color: muted
        )
    }
    return image
}

func writeGIF(_ frames: [NSBitmapImageRep], to url: URL) throws {
    guard let destination = CGImageDestinationCreateWithURL(
        url as CFURL,
        UTType.gif.identifier as CFString,
        frames.count,
        nil
    ) else {
        fatalError("Unable to create GIF destination")
    }
    let gifProperties = [
        kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFLoopCount: 0]
    ] as CFDictionary
    CGImageDestinationSetProperties(destination, gifProperties)
    for (index, frame) in frames.enumerated() {
        guard let image = frame.cgImage else { fatalError("Unable to read GIF frame") }
        let delay = index == frames.count - 1 ? 2.8 : 0.75
        let frameProperties = [
            kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFDelayTime: delay]
        ] as CFDictionary
        CGImageDestinationAddImage(destination, image, frameProperties)
    }
    guard CGImageDestinationFinalize(destination) else {
        fatalError("Unable to finalize GIF")
    }
}

let transcriptLines = transcript
    .split(separator: "\n", omittingEmptySubsequences: false)
    .map(String.init)
    .filter { !$0.contains("/Users/") && !$0.contains("\\Users\\") }
let frameStops = stride(from: 4, through: transcriptLines.count, by: 4).map { $0 }
let stops = frameStops.last == transcriptLines.count
    ? frameStops
    : frameStops + [transcriptLines.count]
let terminalFrames = stops.map { terminalFrame(lines: transcriptLines, visible: $0) }
try writeGIF(terminalFrames, to: outputURL.appendingPathComponent("ordifile-demo.gif"))

let workbookWidth = 1280
let workbookHeight = 720
let workbookImage = bitmap(width: workbookWidth, height: workbookHeight)
withContext(workbookImage) {
    fill(NSRect(x: 0, y: 0, width: workbookWidth, height: workbookHeight), color: offWhite)
    fill(NSRect(x: 0, y: 642, width: workbookWidth, height: 78), color: navy)
    text(
        "Ordifile_Result.xlsx",
        x: 42,
        top: 24,
        canvasHeight: CGFloat(workbookHeight),
        font: NSFont.systemFont(ofSize: 26, weight: .bold),
        color: offWhite
    )
    text(
        "Actual workbook generated from examples/basic",
        x: 360,
        top: 30,
        canvasHeight: CGFloat(workbookHeight),
        font: NSFont.systemFont(ofSize: 16, weight: .medium),
        color: muted
    )

    var tabX: CGFloat = 34
    for (index, sheet) in workbook.sheet_names.enumerated() {
        let tabWidth = max(100, CGFloat(sheet.count * 9 + 28))
        fill(
            NSRect(x: tabX, y: 589, width: tabWidth, height: 38),
            color: index == 1 ? blue : NSColor.white,
            radius: 8
        )
        stroke(NSRect(x: tabX, y: 589, width: tabWidth, height: 38), color: muted, radius: 8)
        text(
            sheet,
            x: tabX + 12,
            top: 99,
            canvasHeight: CGFloat(workbookHeight),
            font: NSFont.systemFont(ofSize: 13, weight: index == 1 ? .bold : .medium),
            color: index == 1 ? NSColor.white : navy,
            width: tabWidth - 24
        )
        tabX += tabWidth + 7
    }

    let rows = workbook.samples
    let visibleColumns = min(rows.first?.count ?? 0, 8)
    let tableX: CGFloat = 34
    let tableTop: CGFloat = 160
    let tableWidth: CGFloat = 1212
    let rowHeight: CGFloat = 68
    let columnWidth = tableWidth / CGFloat(max(visibleColumns, 1))
    for (rowIndex, row) in rows.enumerated() {
        let y = CGFloat(workbookHeight) - tableTop - CGFloat(rowIndex + 1) * rowHeight
        fill(
            NSRect(x: tableX, y: y, width: tableWidth, height: rowHeight),
            color: rowIndex == 0 ? navyLight : (rowIndex.isMultiple(of: 2) ? NSColor.white : NSColor(calibratedWhite: 0.94, alpha: 1))
        )
        for columnIndex in 0..<visibleColumns {
            let x = tableX + CGFloat(columnIndex) * columnWidth
            stroke(NSRect(x: x, y: y, width: columnWidth, height: rowHeight), color: muted.withAlphaComponent(0.55))
            let value = columnIndex < row.count ? row[columnIndex] : ""
            text(
                value,
                x: x + 9,
                top: tableTop + CGFloat(rowIndex) * rowHeight + 21,
                canvasHeight: CGFloat(workbookHeight),
                font: NSFont.systemFont(ofSize: rowIndex == 0 ? 13 : 14, weight: rowIndex == 0 ? .bold : .regular),
                color: rowIndex == 0 ? offWhite : navy,
                width: columnWidth - 18
            )
        }
    }
    text(
        "Natural order preserved: sample_1 → sample_2 → sample_10",
        x: 38,
        top: 654,
        canvasHeight: CGFloat(workbookHeight),
        font: NSFont.systemFont(ofSize: 18, weight: .semibold),
        color: navy
    )
}
try writePNG(workbookImage, to: outputURL.appendingPathComponent("ordifile-workbook.png"))

let socialWidth = 1280
let socialHeight = 640
let socialImage = bitmap(width: socialWidth, height: socialHeight)
withContext(socialImage) {
    fill(NSRect(x: 0, y: 0, width: socialWidth, height: socialHeight), color: navy)
    fill(NSRect(x: 730, y: 70, width: 470, height: 500), color: navyLight, radius: 30)
    text(
        "Ordifile",
        x: 72,
        top: 104,
        canvasHeight: CGFloat(socialHeight),
        font: NSFont.systemFont(ofSize: 74, weight: .bold),
        color: offWhite
    )
    text(
        "Many instrument files.",
        x: 76,
        top: 224,
        canvasHeight: CGFloat(socialHeight),
        font: NSFont.systemFont(ofSize: 35, weight: .semibold),
        color: cyan
    )
    text(
        "One ordered workbook.",
        x: 76,
        top: 278,
        canvasHeight: CGFloat(socialHeight),
        font: NSFont.systemFont(ofSize: 35, weight: .semibold),
        color: green
    )
    text(
        "Batch conversion · deterministic ordering · auditable Excel output",
        x: 78,
        top: 386,
        canvasHeight: CGFloat(socialHeight),
        font: NSFont.systemFont(ofSize: 19, weight: .medium),
        color: muted,
        width: 600
    )

    let fileLabels = ["CSV", "TSV", "TXT", "XLSX"]
    for (index, label) in fileLabels.enumerated() {
        let x = 774 + CGFloat((index % 2) * 142)
        let y = 382 - CGFloat((index / 2) * 142)
        fill(NSRect(x: x, y: y, width: 112, height: 96), color: NSColor.white, radius: 12)
        text(
            label,
            x: x,
            top: CGFloat(socialHeight) - y - 61,
            canvasHeight: CGFloat(socialHeight),
            font: NSFont.monospacedSystemFont(ofSize: 18, weight: .bold),
            color: blue,
            width: 112,
            alignment: .center
        )
    }
    fill(NSRect(x: 1046, y: 210, width: 120, height: 250), color: NSColor.white, radius: 14)
    for row in 0..<7 {
        stroke(
            NSRect(x: 1062, y: 235 + CGFloat(row * 28), width: 88, height: 28),
            color: row == 6 ? green : muted.withAlphaComponent(0.7)
        )
    }
    text(
        "XLSX",
        x: 1050,
        top: 201,
        canvasHeight: CGFloat(socialHeight),
        font: NSFont.systemFont(ofSize: 18, weight: .bold),
        color: green,
        width: 112,
        alignment: .center
    )
    blue.setStroke()
    let arrow = NSBezierPath()
    arrow.lineWidth = 7
    arrow.move(to: NSPoint(x: 1005, y: 335))
    arrow.line(to: NSPoint(x: 1035, y: 335))
    arrow.line(to: NSPoint(x: 1020, y: 350))
    arrow.move(to: NSPoint(x: 1035, y: 335))
    arrow.line(to: NSPoint(x: 1020, y: 320))
    arrow.stroke()
}
try writePNG(socialImage, to: outputURL.appendingPathComponent("ordifile-social-preview.png"))
