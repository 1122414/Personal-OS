import Foundation
import PDFKit

@main
struct ExtractPDF {
    static func main() {
        guard CommandLine.arguments.count == 2,
              let document = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1])),
              !document.isLocked else { exit(1) }
        var pages: [[String: Any]] = []
        var remaining = 80000
        for index in 0..<min(document.pageCount, 200) {
            let raw = document.page(at: index)?.string ?? ""
            let text = String(raw.prefix(remaining))
            pages.append(["page": index + 1, "text": text])
            remaining -= text.count
            if remaining <= 0 { break }
        }
        let result: [String: Any] = ["page_count": document.pageCount, "pages": pages,
                                      "truncated": remaining <= 0 || document.pageCount > 200]
        guard let data = try? JSONSerialization.data(withJSONObject: result),
              let json = String(data: data, encoding: .utf8) else { exit(1) }
        print(json)
    }
}
