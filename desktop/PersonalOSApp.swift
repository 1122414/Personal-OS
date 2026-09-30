import AppKit
import Foundation
import WebKit
import UniformTypeIdentifiers
import UserNotifications

@main
struct PersonalOSMain {
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let delegate = DesktopDelegate()
        app.delegate = delegate
        app.run()
    }
}

final class DesktopDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate,
                             WKScriptMessageHandler, UNUserNotificationCenterDelegate {
    private var window: NSWindow!
    private var webView: WKWebView?
    private var server: Process?
    private var serverLog: FileHandle?
    private var readyFile: URL?
    private var baseURL: URL?
    private var readyTimer: Timer?
    private var launchStarted = Date()
    private var isQuitting = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let icon = Bundle.main.url(forResource: "AppIcon", withExtension: "png"),
           let image = NSImage(contentsOf: icon) {
            NSApp.applicationIconImage = image
        }
        installMenus()
        UNUserNotificationCenter.current().delegate = self
        let frame = NSRect(x: 0, y: 0, width: 1380, height: 860)
        window = NSWindow(contentRect: frame,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Personal OS"
        window.minSize = NSSize(width: 900, height: 620)
        window.setFrameAutosaveName("PersonalOSMainWindow")
        window.center()
        showStatus("正在启动 Personal OS…", "正在准备本地工作空间。", retry: false)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startServer()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        isQuitting = true
        readyTimer?.invalidate()
        if let server, server.isRunning { server.terminate() }
        if let readyFile { try? FileManager.default.removeItem(at: readyFile) }
        try? serverLog?.close()
    }

    private func installMenus() {
        let bar = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(NSMenuItem(title: "关于 Personal OS", action: #selector(showAbout), keyEquivalent: ""))
        appMenu.addItem(.separator())
        appMenu.addItem(NSMenuItem(title: "退出 Personal OS", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        appItem.submenu = appMenu
        bar.addItem(appItem)

        let editItem = NSMenuItem()
        let editMenu = NSMenu(title: "编辑")
        for (title, action, key) in [
            ("撤销", "undo:", "z"), ("重做", "redo:", "Z"),
            ("剪切", "cut:", "x"), ("复制", "copy:", "c"),
            ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")
        ] {
            editMenu.addItem(NSMenuItem(title: title, action: Selector((action)), keyEquivalent: key))
        }
        editItem.submenu = editMenu
        bar.addItem(editItem)

        let viewItem = NSMenuItem()
        let viewMenu = NSMenu(title: "显示")
        let reload = NSMenuItem(title: "重新载入", action: #selector(reloadPage), keyEquivalent: "r")
        reload.target = self
        viewMenu.addItem(reload)
        viewItem.submenu = viewMenu
        bar.addItem(viewItem)
        NSApp.mainMenu = bar
    }

    private func showStatus(_ title: String, _ detail: String, retry: Bool) {
        let background = NSView()
        background.wantsLayer = true
        background.layer?.backgroundColor = NSColor(calibratedRed: 0.075, green: 0.105, blue: 0.145, alpha: 1).cgColor
        let heading = NSTextField(labelWithString: title)
        heading.font = NSFont.systemFont(ofSize: 23, weight: .semibold)
        heading.textColor = .white
        heading.alignment = .center
        let explanation = NSTextField(labelWithString: detail)
        explanation.font = NSFont.systemFont(ofSize: 13)
        explanation.textColor = NSColor(calibratedWhite: 0.78, alpha: 1)
        explanation.alignment = .center
        explanation.maximumNumberOfLines = 5
        explanation.lineBreakMode = .byWordWrapping

        let stack = NSStackView(views: [heading, explanation])
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 14
        if retry {
            let button = NSButton(title: "重试", target: self, action: #selector(retryLaunch))
            button.bezelStyle = .rounded
            stack.addArrangedSubview(button)
        }
        stack.translatesAutoresizingMaskIntoConstraints = false
        background.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: background.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: background.centerYAnchor),
            stack.widthAnchor.constraint(lessThanOrEqualToConstant: 560),
        ])
        window.contentView = background
    }

    /// Set only for test instances, so they never touch the real database.
    private var dataDirectoryOverride: String? {
        let value = ProcessInfo.processInfo.environment["PERSONAL_OS_DATA_DIR"] ?? ""
        return value.isEmpty ? nil : value
    }

    private func applicationSupport() throws -> URL {
        if let override = dataDirectoryOverride {
            let directory = URL(fileURLWithPath: override, isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            return directory
        }
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let directory = root.appendingPathComponent("Personal OS", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }

    private func pythonExecutable() -> URL? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let configured = Bundle.main.object(forInfoDictionaryKey: "PersonalOSPythonPath") as? String
        let candidates = [
            ProcessInfo.processInfo.environment["PERSONAL_OS_PYTHON"], configured,
            "\(home)/.pyenv/shims/python3", "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3", "/usr/bin/python3",
        ].compactMap { $0 }
        for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
            let check = Process()
            check.executableURL = URL(fileURLWithPath: path)
            check.arguments = ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"]
            check.standardOutput = Pipe()
            check.standardError = Pipe()
            guard (try? check.run()) != nil else { continue }
            check.waitUntilExit()
            if check.terminationStatus == 0 { return URL(fileURLWithPath: path) }
        }
        return nil
    }

    private func startServer() {
        guard let runtime = Bundle.main.resourceURL?.appendingPathComponent("runtime", isDirectory: true),
              FileManager.default.fileExists(atPath: runtime.appendingPathComponent("server/app.py").path),
              let python = pythonExecutable() else {
            showStatus("无法启动客户端", "找不到应用资源或 Python 3.12+。请按 README 中的构建说明检查环境。", retry: false)
            return
        }
        do {
            let support = try applicationSupport()
            let database = support.appendingPathComponent("personal-os.sqlite3")
            let ready = support.appendingPathComponent("ready-\(UUID().uuidString).txt")
            let log = support.appendingPathComponent("desktop.log")
            FileManager.default.createFile(atPath: log.path, contents: nil)
            let logHandle = try FileHandle(forWritingTo: log)
            try logHandle.seekToEnd()
            let process = Process()
            process.executableURL = python
            process.currentDirectoryURL = runtime
            process.arguments = ["-u", "-m", "server.app", "--port", "0", "--db", database.path,
                                 "--ready-file", ready.path]
            if dataDirectoryOverride == nil,
               let old = Bundle.main.object(forInfoDictionaryKey: "PersonalOSLegacyDataPath") as? String,
               FileManager.default.fileExists(atPath: old) {
                process.arguments! += ["--migrate-from", old]
            }
            var environment = ProcessInfo.processInfo.environment
            let home = FileManager.default.homeDirectoryForCurrentUser.path
            let search = ["/Applications/ChatGPT.app/Contents/Resources", "\(home)/.local/bin", "\(home)/.kimi-code/bin",
                          "\(home)/.pyenv/shims", "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
            environment["PATH"] = search.joined(separator: ":") + ":" + (environment["PATH"] ?? "")
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            process.environment = environment
            process.standardOutput = logHandle
            process.standardError = logHandle
            process.terminationHandler = { [weak self] ended in
                DispatchQueue.main.async { self?.serverExited(ended) }
            }
            try process.run()
            server = process
            serverLog = logHandle
            readyFile = ready
            launchStarted = Date()
            readyTimer?.invalidate()
            readyTimer = Timer.scheduledTimer(timeInterval: 0.15, target: self,
                                              selector: #selector(checkReady), userInfo: nil, repeats: true)
        } catch {
            showStatus("无法启动本地服务", error.localizedDescription, retry: true)
        }
    }

    @objc private func checkReady() {
        guard let readyFile else { return }
        if let value = try? String(contentsOf: readyFile, encoding: .utf8),
           let port = Int(value.trimmingCharacters(in: .whitespacesAndNewlines)),
           (1...65535).contains(port),
           let url = URL(string: "http://127.0.0.1:\(port)/") {
            readyTimer?.invalidate()
            readyTimer = nil
            baseURL = url
            showWebView(at: url)
        } else if Date().timeIntervalSince(launchStarted) > 30 {
            readyTimer?.invalidate()
            readyTimer = nil
            showStatus("启动超时", "本地服务未能就绪。日志位于 Application Support/Personal OS/desktop.log。", retry: true)
        }
    }

    private func showWebView(at url: URL) {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController.add(self, name: "notify")
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = self
        view.uiDelegate = self
        webView = view
        window.contentView = view
        view.load(URLRequest(url: url))
    }

    private func serverExited(_ process: Process) {
        guard !isQuitting, server === process else { return }
        server = nil
        readyTimer?.invalidate()
        readyTimer = nil
        showStatus("本地服务已停止", "请检查 Application Support/Personal OS/desktop.log，然后重试。", retry: true)
    }

    @objc private func retryLaunch() {
        if server?.isRunning == true, let baseURL { showWebView(at: baseURL) }
        else { showStatus("正在启动 Personal OS…", "正在准备本地工作空间。", retry: false); startServer() }
    }

    @objc private func reloadPage() { webView?.reload() }

    @objc private func showAbout() {
        let alert = NSAlert()
        alert.messageText = "Personal OS"
        alert.informativeText = "本地优先的个人工作台 · macOS 客户端"
        alert.runModal()
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if navigationAction.targetFrame == nil {
            decisionHandler(.allow)
        } else if url.scheme == "about" || (url.scheme == "http" && url.host == "127.0.0.1" && url.port == baseURL?.port) {
            decisionHandler(.allow)
        } else {
            if url.scheme == "https" || url.scheme == "http" { NSWorkspace.shared.open(url) }
            decisionHandler(.cancel)
        }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, url.scheme == "https" || url.scheme == "http" {
            NSWorkspace.shared.open(url)
        }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "确定")
        alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.allowedContentTypes = [.pdf, .png, .jpeg, .gif, .webP]
        panel.beginSheetModal(for: window) { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
    }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "notify", !NSApp.isActive,
              let body = message.body as? [String: Any],
              let title = body["title"] as? String, let text = body["body"] as? String else { return }
        let taskId = body["taskId"] as? String ?? ""
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = text
            content.sound = .default
            content.userInfo = ["taskId": taskId]
            center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        let taskId = response.notification.request.content.userInfo["taskId"] as? String ?? ""
        DispatchQueue.main.async { [weak self] in
            NSApp.activate(ignoringOtherApps: true)
            self?.window.makeKeyAndOrderFront(nil)
            if taskId.range(of: "^[A-Za-z0-9-]+$", options: .regularExpression) != nil {
                self?.webView?.evaluateJavaScript("location.hash = 'tasks/\(taskId)'")
            }
            completionHandler()
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        showStatus("页面载入失败", error.localizedDescription, retry: true)
    }
}
