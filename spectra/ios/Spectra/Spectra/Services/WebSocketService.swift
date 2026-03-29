import Foundation
import Combine

final class WebSocketService: ObservableObject {
    @Published var isConnected = false
    @Published var latestStatus: TaskStatus?
    @Published var confirmationRequest: ConfirmationRequest?
    @Published var handoffRequest: HandoffRequest?
    @Published var planPreview: PlanPreviewData?
    @Published var memoryItems: [MemoryItem] = []
    @Published var taskResult: TaskResult?
    @Published var statusHistory: [TaskStatus] = []
    @Published var askUserRequest: AskUserRequest?
    @Published var isVoiceListening = false
    @Published var voiceTranscript: String?
    @Published var voiceError: String?
    @Published var errorMessage: String?
    @Published var storedTasks: [StoredTask] = []
    @Published var scheduledTasks: [ScheduledTask] = []
    @Published var lastCreatedSchedule: ScheduledTask?
    @Published var highlightedScheduleID: String?
    @Published var scheduleNavigationRequestID = UUID()
    @Published var actionLog: [ActionLogEntry] = []
    @Published var learnedSequences: [LearnedSequence] = []
    @Published var sequenceSuggestion: SequenceSuggestion?

    private var webSocketTask: URLSessionWebSocketTask?
    private let url = URL(string: "ws://localhost:8765/ws")!
    private let session: URLSession = URLSession(configuration: .default)
    private let notificationCoordinator = NotificationCoordinator.shared
    private var connectionID = 0  // guards stale callbacks
    private var isConnecting = false

    func connect() {
        guard !isConnecting else { return }
        isConnecting = true

        // Tear down any existing connection
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        connectionID += 1
        let myID = connectionID

        let task = session.webSocketTask(with: url)
        webSocketTask = task
        task.resume()

        // Don't set isConnected until we get the first successful receive or ping-pong
        listenForMessages(id: myID)

        // Verify connection is alive after 2 seconds via ping
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) { [weak self] in
            self?.verifyAndStartPinging(id: myID)
        }

        isConnecting = false
    }

    private func verifyAndStartPinging(id: Int) {
        guard connectionID == id, let task = webSocketTask else { return }
        task.sendPing { [weak self] error in
            guard let self = self, self.connectionID == id else { return }
            if error != nil {
                // Connection failed — retry
                DispatchQueue.main.async {
                    self.isConnected = false
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                        guard self.connectionID == id else { return }
                        self.connect()
                    }
                }
            } else {
                // Connection is alive
                DispatchQueue.main.async {
                    self.isConnected = true
                }
                self.schedulePing(id: id)
            }
        }
    }

    private func schedulePing(id: Int) {
        DispatchQueue.global().asyncAfter(deadline: .now() + 15) { [weak self] in
            guard let self = self, self.connectionID == id, let task = self.webSocketTask else { return }
            task.sendPing { [weak self] error in
                guard let self = self, self.connectionID == id else { return }
                if error != nil {
                    DispatchQueue.main.async {
                        self.isConnected = false
                        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                            guard self.connectionID == id else { return }
                            self.connect()
                        }
                    }
                } else {
                    self.schedulePing(id: id)
                }
            }
        }
    }

    func disconnect() {
        connectionID += 1
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        DispatchQueue.main.async { self.isConnected = false }
    }

    // MARK: - Outgoing Messages

    func sendCommand(_ task: String) {
        resetTaskState()
        send(["type": "command", "task": task])
    }

    func sendConfirmation(_ approved: Bool) {
        notificationCoordinator.clearConfirmationNotification()
        DispatchQueue.main.async {
            self.confirmationRequest = nil
        }
        send(["type": "confirm", "approved": approved])
    }

    func sendPlanApproval(_ approved: Bool, modifiedSteps: [String]? = nil) {
        var msg: [String: Any] = ["type": "plan_approve", "approved": approved]
        if let steps = modifiedSteps { msg["modified_steps"] = steps }
        send(msg)
    }

    func sendStop() {
        send(["type": "stop"])
    }

    func sendVoiceStart() {
        voiceTranscript = nil
        voiceError = nil
        isVoiceListening = true
        send(["type": "voice_start"])
    }

    func sendVoiceStop() {
        isVoiceListening = false
        send(["type": "voice_stop"])
    }

    func sendTakeoverDone() {
        notificationCoordinator.clearHandoffNotification()
        DispatchQueue.main.async {
            self.handoffRequest = nil
        }
        send(["type": "takeover_done"])
    }

    func sendUserAnswer(_ answer: String) {
        notificationCoordinator.clearAskUserNotification()
        send(["type": "user_answer", "answer": answer])
        DispatchQueue.main.async { self.askUserRequest = nil }
    }

    func requestStoredTasks() {
        send(["type": "stored_tasks_request"])
    }

    func requestScheduledTasks() {
        send(["type": "schedule_list"])
    }

    func pauseScheduledTask(_ taskId: String) {
        send(["type": "schedule_pause", "task_id": taskId])
    }

    func resumeScheduledTask(_ taskId: String) {
        send(["type": "schedule_resume", "task_id": taskId])
    }

    func cancelScheduledTask(_ taskId: String) {
        send(["type": "schedule_cancel", "task_id": taskId])
    }

    func openSchedules(highlighting taskId: String? = nil) {
        DispatchQueue.main.async {
            self.highlightedScheduleID = taskId
            self.scheduleNavigationRequestID = UUID()
            self.requestScheduledTasks()
        }
    }

    func clearScheduleHighlight() {
        DispatchQueue.main.async {
            self.highlightedScheduleID = nil
        }
    }

    func dismissLastCreatedSchedule() {
        DispatchQueue.main.async {
            self.lastCreatedSchedule = nil
        }
    }

    func setAppIsActive(_ isActive: Bool) {
        notificationCoordinator.setAppIsActive(isActive)
    }

    func requestActionLog() {
        send(["type": "action_log_request"])
    }

    func requestSequences() {
        send(["type": "sequences_request"])
    }

    func acceptSequenceSuggestion(_ nextAction: String) {
        let sequenceID = sequenceSuggestion?.sequenceId ?? ""
        acceptSequenceSuggestion(sequenceID: sequenceID, nextAction: nextAction)
    }

    func acceptSequenceSuggestion(sequenceID: String, nextAction: String) {
        if !sequenceID.isEmpty {
            notificationCoordinator.clearSequenceSuggestionNotification(sequenceID: sequenceID)
        }
        send(["type": "sequence_suggestion_accept", "next_action": nextAction])
        DispatchQueue.main.async {
            if self.sequenceSuggestion?.sequenceId == sequenceID {
                self.sequenceSuggestion = nil
            }
        }
    }

    func declineSequenceSuggestion() {
        declineSequenceSuggestion(sequenceID: sequenceSuggestion?.sequenceId ?? "")
    }

    func declineSequenceSuggestion(sequenceID: String) {
        if !sequenceID.isEmpty {
            notificationCoordinator.clearSequenceSuggestionNotification(sequenceID: sequenceID)
        }
        send(["type": "sequence_suggestion_decline", "sequence_id": sequenceID])
        DispatchQueue.main.async {
            if self.sequenceSuggestion?.sequenceId == sequenceID {
                self.sequenceSuggestion = nil
            }
        }
    }

    // MARK: - Internal

    private func resetTaskState() {
        DispatchQueue.main.async {
            self.latestStatus = nil
            self.statusHistory = []
            self.memoryItems = []
            self.taskResult = nil
            self.planPreview = nil
            self.confirmationRequest = nil
            self.handoffRequest = nil
            self.askUserRequest = nil
            self.errorMessage = nil
            self.lastCreatedSchedule = nil
            self.sequenceSuggestion = nil
        }
    }

    private func send(_ message: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: message),
              let string = String(data: data, encoding: .utf8) else { return }
        guard let task = webSocketTask else {
            DispatchQueue.main.async {
                self.errorMessage = "Not connected to server"
            }
            return
        }
        task.send(.string(string)) { [weak self] error in
            if let error = error {
                DispatchQueue.main.async {
                    self?.errorMessage = error.localizedDescription
                }
            }
        }
    }

    private func listenForMessages(id: Int) {
        webSocketTask?.receive { [weak self] result in
            guard let self = self, self.connectionID == id else { return }
            switch result {
            case .success(let message):
                // First successful receive confirms the connection is alive
                DispatchQueue.main.async {
                    if !self.isConnected { self.isConnected = true }
                }
                switch message {
                case .string(let text):
                    self.handleRawMessage(text)
                case .data(let data):
                    if let text = String(data: data, encoding: .utf8) {
                        self.handleRawMessage(text)
                    }
                @unknown default:
                    break
                }
                self.listenForMessages(id: id)
            case .failure:
                DispatchQueue.main.async {
                    guard self.connectionID == id else { return }
                    self.isConnected = false
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                        guard self.connectionID == id else { return }
                        self.connect()
                    }
                }
            }
        }
    }

    private func handleRawMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }

        DispatchQueue.main.async { [self] in
            self.handleMessage(type: type, json: json)
        }
    }

    private func handleMessage(type: String, json: [String: Any]) {
        switch type {
        case "status":
            if let data = try? JSONSerialization.data(withJSONObject: json),
               let status = try? JSONDecoder().decode(TaskStatus.self, from: data) {
                latestStatus = status
                statusHistory.append(status)
            }

        case "memory_update":
            if let key = json["key"] as? String, let value = json["value"] as? String {
                let item = MemoryItem(key: key, value: value)
                if let idx = memoryItems.firstIndex(where: { $0.key == key }) {
                    memoryItems[idx] = item
                } else {
                    memoryItems.append(item)
                }
            }

        case "plan_preview":
            if let data = try? JSONSerialization.data(withJSONObject: json),
               let plan = try? JSONDecoder().decode(PlanPreviewData.self, from: data) {
                planPreview = plan
            }

        case "confirm_request":
            if let data = try? JSONSerialization.data(withJSONObject: json),
               let request = try? JSONDecoder().decode(ConfirmationRequest.self, from: data) {
                confirmationRequest = request
                notificationCoordinator.handle(.confirmRequest(request))
            }

        case "handoff_request":
            if let reason = json["reason"] as? String {
                handoffRequest = HandoffRequest(reason: reason)
                notificationCoordinator.handle(.handoff(reason: reason))
            }

        case "ask_user":
            if let data = try? JSONSerialization.data(withJSONObject: json),
               let request = try? JSONDecoder().decode(AskUserRequest.self, from: data) {
                askUserRequest = request
                notificationCoordinator.handle(.askUser(request))
            }

        case "done":
            if let data = try? JSONSerialization.data(withJSONObject: json),
               let result = try? JSONDecoder().decode(TaskResult.self, from: data) {
                taskResult = result
                confirmationRequest = nil
                handoffRequest = nil
                askUserRequest = nil
                notificationCoordinator.handle(.taskResult(result))
            }

        case "stuck":
            let reason = json["reason"] as? String ?? "Unknown"
            taskResult = TaskResult(success: false, summary: reason, steps: statusHistory.count, duration: 0)
            confirmationRequest = nil
            handoffRequest = nil
            askUserRequest = nil
            notificationCoordinator.handle(.taskStuck(reason: reason))

        case "voice_listening":
            isVoiceListening = true

        case "voice_result":
            isVoiceListening = false
            voiceTranscript = json["transcript"] as? String

        case "voice_error":
            isVoiceListening = false
            voiceError = json["error"] as? String

        case "voice_cancelled":
            isVoiceListening = false

        case "action_log_response":
            if let items = json["actions"] as? [[String: Any]] {
                actionLog = items.compactMap { d in
                    guard let id = d["id"] as? String,
                          let ts = d["timestamp"] as? Double,
                          let app = d["app"] as? String,
                          let action = d["action"] as? String else { return nil }
                    return ActionLogEntry(id: id, timestamp: ts, app: app, action: action)
                }
            }

        case "sequences_response":
            if let items = json["sequences"] as? [[String: Any]] {
                learnedSequences = items.compactMap { d in
                    guard let id = d["id"] as? String,
                          let actions = d["actions"] as? [String],
                          let count = d["occurrence_count"] as? Int else { return nil }
                    return LearnedSequence(id: id, actions: actions, occurrenceCount: count,
                                           createdAt: d["created_at"] as? Double ?? 0,
                                           initialState: d["initial_state"] as? String,
                                           goalState: d["goal_state"] as? String)
                }
            }

        case "sequence_suggestion":
            if let nextAction = json["next_action"] as? String,
               let prefix = json["prefix"] as? [String],
               let seqId = json["sequence_id"] as? String {
                let suggestion = SequenceSuggestion(
                    sequenceId: seqId,
                    nextAction: nextAction,
                    prefix: prefix,
                    occurrenceCount: json["occurrence_count"] as? Int ?? 0,
                    initialState: json["initial_state"] as? String,
                    goalState: json["goal_state"] as? String
                )
                sequenceSuggestion = suggestion
                notificationCoordinator.handle(.sequenceSuggestion(suggestion))
            }

        case "schedule_fired":
            if let taskId = json["task_id"] as? String,
               let taskDesc = json["task"] as? String {
                requestScheduledTasks()
                notificationCoordinator.handle(
                    .scheduleFired(
                        taskID: taskId,
                        task: taskDesc,
                        isRecurring: (json["schedule_type"] as? String) == "recurring"
                    )
                )
            }

        case "schedule_created":
            if let taskInfo = json["task"] as? [String: Any],
               let createdTask = makeScheduledTask(from: taskInfo) {
                notificationCoordinator.handle(.scheduleCreated(createdTask))
                if createdTask.isRecurring {
                    lastCreatedSchedule = createdTask
                }
                requestScheduledTasks()
            }

        case "scheduled_tasks_response":
            if let tasksArray = json["tasks"] as? [[String: Any]] {
                scheduledTasks = tasksArray.compactMap(makeScheduledTask)
                if let lastCreatedSchedule {
                    self.lastCreatedSchedule = scheduledTasks.first(where: { $0.id == lastCreatedSchedule.id })
                }
            }

        case "schedule_cancelled":
            let taskId = json["task_id"] as? String ?? ""
            let success = json["success"] as? Bool ?? false
            if success {
                scheduledTasks.removeAll { $0.id == taskId }
                notificationCoordinator.clearScheduleNotifications(taskID: taskId)
                if lastCreatedSchedule?.id == taskId {
                    lastCreatedSchedule = nil
                }
                requestScheduledTasks()
            } else if !taskId.isEmpty {
                errorMessage = "Couldn't cancel scheduled task"
            }

        case "schedule_paused":
            let taskId = json["task_id"] as? String ?? ""
            let success = json["success"] as? Bool ?? false
            if success {
                notificationCoordinator.clearScheduleNotifications(taskID: taskId)
                if let taskInfo = json["task"] as? [String: Any],
                   let updatedTask = makeScheduledTask(from: taskInfo) {
                    upsertScheduledTask(updatedTask)
                }
                requestScheduledTasks()
            } else if !taskId.isEmpty {
                errorMessage = "Couldn't stop recurring schedule"
            }

        case "schedule_resumed":
            let taskId = json["task_id"] as? String ?? ""
            let success = json["success"] as? Bool ?? false
            if success {
                if let taskInfo = json["task"] as? [String: Any],
                   let updatedTask = makeScheduledTask(from: taskInfo) {
                    upsertScheduledTask(updatedTask)
                }
                requestScheduledTasks()
            } else if !taskId.isEmpty {
                errorMessage = "Couldn't resume recurring schedule"
            }

        case "stored_tasks_response":
            if let tasksArray = json["tasks"] as? [[String: Any]] {
                storedTasks = tasksArray.compactMap { dict in
                    guard let id = dict["id"] as? String,
                          let desc = dict["task_description"] as? String,
                          let steps = dict["step_count"] as? Int,
                          let occ = dict["occurrence_count"] as? Int,
                          let created = dict["created_at"] as? Double,
                          let hour = dict["hour_of_day"] as? Int,
                          let dow = dict["day_of_week"] as? Int,
                          let triggersRaw = dict["triggers"] as? [[String: Any]] else { return nil }
                    let triggers = triggersRaw.compactMap { t -> ContextTrigger? in
                        guard let type = t["type"] as? String,
                              let label = t["label"] as? String,
                              let detail = t["detail"] as? String else { return nil }
                        return ContextTrigger(type: type, label: label, detail: detail)
                    }
                    return StoredTask(id: id, taskDescription: desc, stepCount: steps,
                                      occurrenceCount: occ, createdAt: created,
                                      hourOfDay: hour, dayOfWeek: dow, triggers: triggers)
                }
            }

        case "error":
            errorMessage = json["message"] as? String

        default:
            break
        }
    }

    private func makeScheduledTask(from dict: [String: Any]) -> ScheduledTask? {
        guard let id = dict["id"] as? String,
              let task = dict["task"] as? String,
              let scheduleType = dict["schedule_type"] as? String,
              let recurrence = dict["recurrence"] as? String,
              let enabled = dict["enabled"] as? Bool else { return nil }

        let nextRun = (dict["next_run"] as? NSNumber)?.doubleValue
        let createdAt = (dict["created_at"] as? NSNumber)?.doubleValue ?? 0
        let fireCount = (dict["fire_count"] as? NSNumber)?.intValue ?? 0
        let lastFiredAt = (dict["last_fired_at"] as? NSNumber)?.doubleValue

        return ScheduledTask(
            id: id,
            task: task,
            scheduleType: scheduleType,
            recurrence: recurrence,
            nextRun: nextRun,
            nextRunDisplay: dict["next_run_display"] as? String,
            enabled: enabled,
            createdAt: createdAt,
            fireCount: fireCount,
            lastFiredAt: lastFiredAt
        )
    }

    private func upsertScheduledTask(_ task: ScheduledTask) {
        if let existingIndex = scheduledTasks.firstIndex(where: { $0.id == task.id }) {
            scheduledTasks[existingIndex] = task
        } else {
            scheduledTasks.append(task)
        }
        if lastCreatedSchedule?.id == task.id {
            lastCreatedSchedule = task
        }
    }
}
