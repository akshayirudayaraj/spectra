import Foundation

struct ContextTrigger: Identifiable {
    let id = UUID()
    let type: String   // "time", "location", "app"
    let label: String
    let detail: String
}

struct StoredTask: Identifiable {
    let id: String
    let taskDescription: String
    let stepCount: Int
    let occurrenceCount: Int
    let createdAt: Double
    let hourOfDay: Int
    let dayOfWeek: Int
    let triggers: [ContextTrigger]
}

struct ScheduledTask: Identifiable, Equatable {
    let id: String
    let task: String
    let scheduleType: String
    let recurrence: String
    let nextRun: Double?
    let nextRunDisplay: String?
    let enabled: Bool
    let createdAt: Double
    let fireCount: Int
    let lastFiredAt: Double?

    var isRecurring: Bool { scheduleType == "recurring" }
    var isActiveRecurring: Bool { isRecurring && enabled }
    var isPausedRecurring: Bool { isRecurring && !enabled }
    var isPendingOneTime: Bool { !isRecurring && enabled }
    var isCompletedOneTime: Bool { !isRecurring && !enabled }
}

struct ActionLogEntry: Identifiable {
    let id: String
    let timestamp: Double
    let app: String
    let action: String
}

struct LearnedSequence: Identifiable {
    let id: String
    let actions: [String]
    let occurrenceCount: Int
    let createdAt: Double
    let initialState: String?
    let goalState: String?
}

struct SequenceSuggestion: Identifiable {
    var id: String { sequenceId }
    let sequenceId: String
    let nextAction: String
    let prefix: [String]
    let occurrenceCount: Int
    let initialState: String?
    let goalState: String?
}
