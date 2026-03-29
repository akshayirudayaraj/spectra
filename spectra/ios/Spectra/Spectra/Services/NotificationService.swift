import Foundation
import UserNotifications

final class NotificationService {
    static let shared = NotificationService()

    enum Category {
        static let taskConfirmation = "TASK_CONFIRMATION"
        static let sequenceSuggestion = "SEQUENCE_SUGGESTION"
        static let scheduleCreatedControl = "SCHEDULE_CREATED_CONTROL"
        static let scheduleRunningControl = "SCHEDULE_RUNNING_CONTROL"
        static let legacyScheduleControl = "SCHEDULE_CONTROL"
    }

    enum Action {
        static let approve = "APPROVE"
        static let deny = "DENY"
        static let doIt = "DO_IT"
        static let notNow = "NOT_NOW"
        static let stopRecurring = "STOP_RECURRING"
        static let stopFutureRuns = "STOP_FUTURE_RUNS"
        static let legacyStop = "STOP"
    }

    enum UserInfoKey {
        static let taskID = "task_id"
        static let sequenceID = "sequence_id"
        static let nextAction = "next_action"
    }

    enum Identifier {
        static let taskConfirmation = "task-confirmation"
        static let taskAskUser = "task-ask-user"
        static let taskHandoff = "task-handoff"
        static let taskResult = "task-result"
        static let taskSequencePrefix = "task-sequence-"

        static func taskSequence(_ sequenceID: String) -> String {
            "\(taskSequencePrefix)\(sequenceID)"
        }

        static func scheduleCreated(_ taskID: String) -> String {
            "schedule-created-\(taskID)"
        }

        static func scheduleFired(_ taskID: String) -> String {
            "schedule-fired-\(taskID)"
        }

        static func schedulePauseFailed(_ taskID: String) -> String {
            "schedule-pause-failed-\(taskID)"
        }

        static func scheduleThread(_ taskID: String) -> String {
            "schedule-thread-\(taskID)"
        }
    }

    private init() {}

    func requestPermission() {
        let approveAction = UNNotificationAction(
            identifier: Action.approve,
            title: "Approve",
            options: [.foreground]
        )
        let denyAction = UNNotificationAction(
            identifier: Action.deny,
            title: "Deny",
            options: [.destructive]
        )
        let confirmCategory = UNNotificationCategory(
            identifier: Category.taskConfirmation,
            actions: [approveAction, denyAction],
            intentIdentifiers: [],
            options: []
        )

        let doItAction = UNNotificationAction(
            identifier: Action.doIt,
            title: "Yes, do it",
            options: [.foreground]
        )
        let notNowAction = UNNotificationAction(
            identifier: Action.notNow,
            title: "Not now",
            options: []
        )
        let sequenceSuggestionCategory = UNNotificationCategory(
            identifier: Category.sequenceSuggestion,
            actions: [doItAction, notNowAction],
            intentIdentifiers: [],
            options: []
        )

        let stopRecurringAction = UNNotificationAction(
            identifier: Action.stopRecurring,
            title: "Stop recurring",
            options: [.destructive]
        )
        let stopFutureRunsAction = UNNotificationAction(
            identifier: Action.stopFutureRuns,
            title: "Stop future runs",
            options: [.destructive]
        )
        let scheduleCreatedCategory = UNNotificationCategory(
            identifier: Category.scheduleCreatedControl,
            actions: [stopRecurringAction],
            intentIdentifiers: [],
            options: []
        )
        let scheduleRunningCategory = UNNotificationCategory(
            identifier: Category.scheduleRunningControl,
            actions: [stopFutureRunsAction],
            intentIdentifiers: [],
            options: []
        )
        let legacyScheduleControlCategory = UNNotificationCategory(
            identifier: Category.legacyScheduleControl,
            actions: [stopFutureRunsAction],
            intentIdentifiers: [],
            options: []
        )

        let center = UNUserNotificationCenter.current()
        center.setNotificationCategories([
            confirmCategory,
            sequenceSuggestionCategory,
            scheduleCreatedCategory,
            scheduleRunningCategory,
            legacyScheduleControlCategory,
        ])
        center.requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }

    func post(
        identifier: String,
        title: String,
        body: String,
        subtitle: String? = nil,
        categoryIdentifier: String? = nil,
        userInfo: [AnyHashable: Any] = [:],
        threadIdentifier: String? = nil
    ) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        if let subtitle, !subtitle.isEmpty {
            content.subtitle = subtitle
        }
        content.sound = .default
        if let categoryIdentifier {
            content.categoryIdentifier = categoryIdentifier
        }
        if !userInfo.isEmpty {
            content.userInfo = userInfo
        }
        if let threadIdentifier, !threadIdentifier.isEmpty {
            content.threadIdentifier = threadIdentifier
        }

        let request = UNNotificationRequest(identifier: identifier, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    func clearNotifications(withIdentifiers identifiers: [String]) {
        guard !identifiers.isEmpty else { return }
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: identifiers)
        center.removeDeliveredNotifications(withIdentifiers: identifiers)
    }

    func clearTaskInterruptionNotifications(sequenceID: String? = nil) {
        var identifiers = [
            Identifier.taskConfirmation,
            Identifier.taskAskUser,
            Identifier.taskHandoff,
        ]
        if let sequenceID, !sequenceID.isEmpty {
            identifiers.append(Identifier.taskSequence(sequenceID))
        }
        clearNotifications(withIdentifiers: identifiers)

        let center = UNUserNotificationCenter.current()
        center.getPendingNotificationRequests { requests in
            let sequenceIdentifiers = requests.compactMap { request -> String? in
                request.identifier.hasPrefix(Identifier.taskSequencePrefix) ? request.identifier : nil
            }
            guard !sequenceIdentifiers.isEmpty else { return }
            center.removePendingNotificationRequests(withIdentifiers: sequenceIdentifiers)
        }
        center.getDeliveredNotifications { notifications in
            let sequenceIdentifiers = notifications.compactMap { notification -> String? in
                let identifier = notification.request.identifier
                return identifier.hasPrefix(Identifier.taskSequencePrefix) ? identifier : nil
            }
            guard !sequenceIdentifiers.isEmpty else { return }
            center.removeDeliveredNotifications(withIdentifiers: sequenceIdentifiers)
        }
    }

    func clearConfirmationNotification() {
        clearNotifications(withIdentifiers: [Identifier.taskConfirmation])
    }

    func clearAskUserNotification() {
        clearNotifications(withIdentifiers: [Identifier.taskAskUser])
    }

    func clearHandoffNotification() {
        clearNotifications(withIdentifiers: [Identifier.taskHandoff])
    }

    func clearSequenceSuggestionNotification(sequenceID: String) {
        clearNotifications(withIdentifiers: [Identifier.taskSequence(sequenceID)])
    }

    func clearScheduleNotifications(taskId: String) {
        clearNotifications(withIdentifiers: [
            Identifier.scheduleCreated(taskId),
            Identifier.scheduleFired(taskId),
            Identifier.schedulePauseFailed(taskId),
        ])

        let center = UNUserNotificationCenter.current()
        center.getPendingNotificationRequests { requests in
            let identifiers = requests.compactMap { request -> String? in
                let content = request.content
                let contentTaskID = content.userInfo[UserInfoKey.taskID] as? String
                if contentTaskID == taskId || content.threadIdentifier == Identifier.scheduleThread(taskId) {
                    return request.identifier
                }
                return nil
            }
            guard !identifiers.isEmpty else { return }
            center.removePendingNotificationRequests(withIdentifiers: identifiers)
        }
        center.getDeliveredNotifications { notifications in
            let identifiers = notifications.compactMap { notification -> String? in
                let content = notification.request.content
                let contentTaskID = content.userInfo[UserInfoKey.taskID] as? String
                if contentTaskID == taskId || content.threadIdentifier == Identifier.scheduleThread(taskId) {
                    return notification.request.identifier
                }
                return nil
            }
            guard !identifiers.isEmpty else { return }
            center.removeDeliveredNotifications(withIdentifiers: identifiers)
        }
    }

    func postSchedulePauseFailed(taskId: String) {
        post(
            identifier: Identifier.schedulePauseFailed(taskId),
            title: "Spectra — Couldn't pause recurring task",
            body: "Try again from the Schedules screen.",
            userInfo: [UserInfoKey.taskID: taskId],
            threadIdentifier: Identifier.scheduleThread(taskId)
        )
    }
}

final class NotificationCoordinator {
    static let shared = NotificationCoordinator(service: .shared)

    enum Event {
        case confirmRequest(ConfirmationRequest)
        case handoff(reason: String)
        case askUser(AskUserRequest)
        case sequenceSuggestion(SequenceSuggestion)
        case scheduleCreated(ScheduledTask)
        case scheduleFired(taskID: String, task: String, isRecurring: Bool)
        case taskResult(TaskResult)
        case taskStuck(reason: String)
    }

    private let service: NotificationService
    private var isAppActive = true

    private init(service: NotificationService) {
        self.service = service
    }

    func setAppIsActive(_ isActive: Bool) {
        self.isAppActive = isActive
    }

    func handle(_ event: Event) {
        switch event {
        case .confirmRequest(let request):
            guard !isAppActive else { return }
            service.post(
                identifier: NotificationService.Identifier.taskConfirmation,
                title: "Spectra — Approval Needed",
                body: confirmationBody(for: request),
                categoryIdentifier: NotificationService.Category.taskConfirmation
            )

        case .handoff(let reason):
            guard !isAppActive else { return }
            service.post(
                identifier: NotificationService.Identifier.taskHandoff,
                title: "Spectra — Your Turn",
                body: reason
            )

        case .askUser(let request):
            guard !isAppActive else { return }
            service.post(
                identifier: NotificationService.Identifier.taskAskUser,
                title: "Spectra — Input Needed",
                body: request.question
            )

        case .sequenceSuggestion(let suggestion):
            guard !isAppActive else { return }
            let context = suggestion.prefix.last ?? "your recent actions"
            service.post(
                identifier: NotificationService.Identifier.taskSequence(suggestion.sequenceId),
                title: "Spectra — Suggestion",
                body: "After \(context), would you like me to: \(suggestion.nextAction)?",
                categoryIdentifier: NotificationService.Category.sequenceSuggestion,
                userInfo: [
                    NotificationService.UserInfoKey.sequenceID: suggestion.sequenceId,
                    NotificationService.UserInfoKey.nextAction: suggestion.nextAction,
                ]
            )

        case .scheduleCreated(let task):
            service.post(
                identifier: NotificationService.Identifier.scheduleCreated(task.id),
                title: "Spectra — Task Scheduled",
                body: "\(task.task) — \(task.recurrence)",
                categoryIdentifier: task.isRecurring ? NotificationService.Category.scheduleCreatedControl : nil,
                userInfo: [NotificationService.UserInfoKey.taskID: task.id],
                threadIdentifier: NotificationService.Identifier.scheduleThread(task.id)
            )

        case .scheduleFired(let taskID, let task, let isRecurring):
            service.post(
                identifier: NotificationService.Identifier.scheduleFired(taskID),
                title: "Spectra — Scheduled Task",
                body: "Running: \(task)",
                categoryIdentifier: isRecurring ? NotificationService.Category.scheduleRunningControl : nil,
                userInfo: [NotificationService.UserInfoKey.taskID: taskID],
                threadIdentifier: NotificationService.Identifier.scheduleThread(taskID)
            )

        case .taskResult(let result):
            service.clearTaskInterruptionNotifications()
            service.clearNotifications(withIdentifiers: [NotificationService.Identifier.taskResult])
            guard !isAppActive else { return }
            service.post(
                identifier: NotificationService.Identifier.taskResult,
                title: title(for: result),
                body: result.summary,
                subtitle: "\(result.steps) steps \u{00B7} \(String(format: "%.1f", result.duration))s"
            )

        case .taskStuck(let reason):
            service.clearTaskInterruptionNotifications()
            service.clearNotifications(withIdentifiers: [NotificationService.Identifier.taskResult])
            guard !isAppActive else { return }
            service.post(
                identifier: NotificationService.Identifier.taskResult,
                title: "Spectra — Task Stuck",
                body: reason
            )
        }
    }

    func clearConfirmationNotification() {
        service.clearConfirmationNotification()
    }

    func clearAskUserNotification() {
        service.clearAskUserNotification()
    }

    func clearHandoffNotification() {
        service.clearHandoffNotification()
    }

    func clearSequenceSuggestionNotification(sequenceID: String) {
        service.clearSequenceSuggestionNotification(sequenceID: sequenceID)
    }

    func clearScheduleNotifications(taskID: String) {
        service.clearScheduleNotifications(taskId: taskID)
    }

    private func confirmationBody(for request: ConfirmationRequest) -> String {
        let detail = [request.detail, request.label]
            .first { !$0.isEmpty } ?? ""
        if detail.isEmpty {
            return request.action
        }
        return "\(request.action): \(detail)"
    }

    private func title(for result: TaskResult) -> String {
        if result.success {
            return "Spectra — Done!"
        }
        if result.summary == "Stopped by user" {
            return "Spectra — Task Stopped"
        }
        return "Spectra — Task Ended"
    }
}
