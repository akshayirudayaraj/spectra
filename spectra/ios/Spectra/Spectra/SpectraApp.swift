import Foundation
import SwiftUI
import UserNotifications

class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    private enum PendingNotificationAction {
        case confirmation(Bool)
        case acceptSequenceSuggestion(sequenceID: String, nextAction: String)
        case declineSequenceSuggestion(String)
        case openSchedules(String?)
    }

    /// Shared reference so notification actions can reach the WebSocketService.
    weak var ws: WebSocketService? {
        didSet {
            flushPendingNotificationActions()
        }
    }
    private var pendingNotificationActions: [PendingNotificationAction] = []

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        NotificationService.shared.requestPermission()
        return true
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        if shouldPresentForegroundBanner(for: notification.request) {
            completionHandler([.banner, .list, .sound])
        } else {
            completionHandler([])
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let request = response.notification.request
        let userInfo = response.notification.request.content.userInfo
        let taskID = userInfo[NotificationService.UserInfoKey.taskID] as? String
        let sequenceID = userInfo[NotificationService.UserInfoKey.sequenceID] as? String
        let nextAction = userInfo[NotificationService.UserInfoKey.nextAction] as? String

        switch response.actionIdentifier {
        case NotificationService.Action.approve:
            performOrQueue(.confirmation(true))
        case NotificationService.Action.deny:
            performOrQueue(.confirmation(false))
        case NotificationService.Action.doIt:
            if let sequenceID, let nextAction {
                performOrQueue(.acceptSequenceSuggestion(sequenceID: sequenceID, nextAction: nextAction))
            }
        case NotificationService.Action.notNow:
            if let sequenceID {
                performOrQueue(.declineSequenceSuggestion(sequenceID))
            }
        case NotificationService.Action.stopRecurring,
             NotificationService.Action.stopFutureRuns,
             NotificationService.Action.legacyStop:
            if let taskID {
                handleBackgroundSchedulePause(taskID: taskID, completionHandler: completionHandler)
                return
            }
        case UNNotificationDefaultActionIdentifier:
            if isScheduleNotification(request, taskID: taskID) {
                performOrQueue(.openSchedules(taskID))
            }
        default:
            break
        }
        completionHandler()
    }

    private func performOrQueue(_ action: PendingNotificationAction) {
        guard let ws else {
            pendingNotificationActions.append(action)
            return
        }
        perform(action, with: ws)
    }

    private func flushPendingNotificationActions() {
        guard let ws, !pendingNotificationActions.isEmpty else { return }
        let actions = pendingNotificationActions
        pendingNotificationActions.removeAll()
        actions.forEach { perform($0, with: ws) }
    }

    private func perform(_ action: PendingNotificationAction, with ws: WebSocketService) {
        switch action {
        case .confirmation(let approved):
            ws.sendConfirmation(approved)
        case .acceptSequenceSuggestion(let sequenceID, let nextAction):
            ws.acceptSequenceSuggestion(sequenceID: sequenceID, nextAction: nextAction)
        case .declineSequenceSuggestion(let sequenceID):
            ws.declineSequenceSuggestion(sequenceID: sequenceID)
        case .openSchedules(let taskId):
            ws.openSchedules(highlighting: taskId)
        }
    }

    private func shouldPresentForegroundBanner(for request: UNNotificationRequest) -> Bool {
        let identifier = request.identifier
        let categoryIdentifier = request.content.categoryIdentifier

        if categoryIdentifier == NotificationService.Category.scheduleCreatedControl ||
            categoryIdentifier == NotificationService.Category.scheduleRunningControl ||
            categoryIdentifier == NotificationService.Category.legacyScheduleControl {
            return true
        }

        return identifier.hasPrefix("schedule-created-") ||
            identifier.hasPrefix("schedule-fired-") ||
            identifier.hasPrefix("schedule-pause-failed-")
    }

    private func isScheduleNotification(_ request: UNNotificationRequest, taskID: String?) -> Bool {
        guard taskID != nil else { return false }
        return shouldPresentForegroundBanner(for: request)
    }

    private func handleBackgroundSchedulePause(taskID: String, completionHandler: @escaping () -> Void) {
        let application = UIApplication.shared
        let lock = NSLock()
        var backgroundTaskID: UIBackgroundTaskIdentifier = .invalid
        var didFinish = false

        let finish: () -> Void = {
            lock.lock()
            defer { lock.unlock() }
            guard !didFinish else { return }
            didFinish = true
            if backgroundTaskID != .invalid {
                application.endBackgroundTask(backgroundTaskID)
                backgroundTaskID = .invalid
            }
            completionHandler()
        }

        backgroundTaskID = application.beginBackgroundTask(withName: "pause-recurring-schedule") {
            finish()
        }

        Task {
            let success = await BackgroundScheduleActionSender.pause(taskId: taskID)
            if success {
                NotificationCoordinator.shared.clearScheduleNotifications(taskID: taskID)
            } else {
                NotificationService.shared.postSchedulePauseFailed(taskId: taskID)
            }
            finish()
        }
    }
}

private enum BackgroundScheduleActionSender {
    private static let socketURL = URL(string: "ws://localhost:8765/ws")!
    private static let timeoutNanoseconds: UInt64 = 3_000_000_000

    static func pause(taskId: String) async -> Bool {
        let socket = URLSession(configuration: .default).webSocketTask(with: socketURL)
        socket.resume()
        defer { socket.cancel(with: .goingAway, reason: nil) }

        guard let payload = pausePayload(taskId: taskId) else { return false }

        do {
            try await socket.send(.string(payload))
        } catch {
            return false
        }

        return await waitForPauseResponse(from: socket, taskId: taskId)
    }

    private static func pausePayload(taskId: String) -> String? {
        let payload: [String: Any] = [
            "type": "schedule_pause",
            "task_id": taskId,
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: payload) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func waitForPauseResponse(from socket: URLSessionWebSocketTask, taskId: String) async -> Bool {
        await withTaskGroup(of: Bool.self) { group in
            group.addTask {
                await receivePauseResponse(from: socket, taskId: taskId)
            }
            group.addTask {
                try? await Task.sleep(nanoseconds: timeoutNanoseconds)
                return false
            }

            let result = await group.next() ?? false
            group.cancelAll()
            return result
        }
    }

    private static func receivePauseResponse(from socket: URLSessionWebSocketTask, taskId: String) async -> Bool {
        while !Task.isCancelled {
            do {
                let message = try await socket.receive()
                guard let json = decodeMessage(message),
                      let type = json["type"] as? String else {
                    continue
                }

                if type == "schedule_paused" {
                    let responseTaskID = json["task_id"] as? String ?? taskId
                    let success = json["success"] as? Bool ?? false
                    return responseTaskID == taskId && success
                }

                if type == "error" {
                    return false
                }
            } catch {
                return false
            }
        }

        return false
    }

    private static func decodeMessage(_ message: URLSessionWebSocketTask.Message) -> [String: Any]? {
        let data: Data?

        switch message {
        case .string(let text):
            data = text.data(using: .utf8)
        case .data(let rawData):
            data = rawData
        @unknown default:
            data = nil
        }

        guard let data,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return json
    }
}

@main
struct SpectraApp: App {
    @Environment(\.scenePhase) private var scenePhase
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var ws = WebSocketService()

    var body: some Scene {
        WindowGroup {
            HomeView()
                .environmentObject(ws)
                .onAppear {
                    ws.connect()
                    ws.setAppIsActive(scenePhase == .active)
                    appDelegate.ws = ws
                }
                .onChange(of: scenePhase) { _, newPhase in
                    ws.setAppIsActive(newPhase == .active)
                }
        }
    }
}
