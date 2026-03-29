import SwiftUI

struct SchedulesDashboardView: View {
    @EnvironmentObject var ws: WebSocketService
    var embedded = false

    @ViewBuilder
    var body: some View {
        if embedded {
            SchedulesDashboardContent(embedded: true)
                .environmentObject(ws)
        } else {
            SchedulesDashboardContent(embedded: false)
                .environmentObject(ws)
                .navigationTitle("Schedules")
                .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct TransparencyPortalView: View {
    @EnvironmentObject var ws: WebSocketService
    @State private var selectedTab = 0
    @State private var selectedWorkflow: LearnedSequence?

    var body: some View {
        VStack(spacing: 0) {
            Picker("View", selection: $selectedTab) {
                Text("Workflows").tag(0)
                Text("Schedules").tag(1)
                Text("All Actions").tag(2)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.top, 8)

            if selectedTab == 0 {
                workflowsTab
            } else if selectedTab == 1 {
                SchedulesDashboardView(embedded: true)
                    .environmentObject(ws)
            } else {
                actionsTab
            }
        }
        .navigationTitle("Automation")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            ws.requestSequences()
            ws.requestActionLog()
            ws.requestScheduledTasks()
        }
        .sheet(item: $selectedWorkflow) { workflow in
            WorkflowDetailSheet(sequence: workflow)
        }
    }

    private var workflowsTab: some View {
        ScrollView {
            if ws.learnedSequences.isEmpty {
                PortalEmptyState(
                    icon: "arrow.right.circle",
                    title: "No workflows yet",
                    subtitle: "Spectra learns your patterns. Use your phone naturally and workflows will appear here."
                )
            } else {
                LazyVStack(spacing: 12) {
                    ForEach(ws.learnedSequences) { seq in
                        WorkflowCard(sequence: seq)
                            .onTapGesture { selectedWorkflow = seq }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
            }
        }
    }

    private var actionsTab: some View {
        ScrollView {
            if ws.actionLog.isEmpty {
                PortalEmptyState(
                    icon: "list.bullet.rectangle",
                    title: "No actions recorded",
                    subtitle: "As you use apps, Spectra watches and records every action in natural language."
                )
            } else {
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(ws.actionLog.enumerated()), id: \.element.id) { index, entry in
                        ActionRow(entry: entry, isFirst: index == 0, isLast: index == ws.actionLog.count - 1)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
            }
        }
    }
}

private struct SchedulesDashboardContent: View {
    @EnvironmentObject var ws: WebSocketService
    let embedded: Bool

    private var activeRecurring: [ScheduledTask] {
        ws.scheduledTasks
            .filter(\.isActiveRecurring)
            .sorted { lhs, rhs in
                switch (lhs.nextRun, rhs.nextRun) {
                case let (l?, r?):
                    return l < r
                case (.some, .none):
                    return true
                case (.none, .some):
                    return false
                default:
                    return lhs.createdAt > rhs.createdAt
                }
            }
    }

    private var pausedRecurring: [ScheduledTask] {
        ws.scheduledTasks
            .filter(\.isPausedRecurring)
            .sorted { $0.createdAt > $1.createdAt }
    }

    private var pendingOneTime: [ScheduledTask] {
        ws.scheduledTasks
            .filter(\.isPendingOneTime)
            .sorted { lhs, rhs in
                switch (lhs.nextRun, rhs.nextRun) {
                case let (l?, r?):
                    return l < r
                case (.some, .none):
                    return true
                case (.none, .some):
                    return false
                default:
                    return lhs.createdAt > rhs.createdAt
                }
            }
    }

    private var completedOneTime: [ScheduledTask] {
        ws.scheduledTasks
            .filter(\.isCompletedOneTime)
            .sorted { ($0.lastFiredAt ?? $0.createdAt) > ($1.lastFiredAt ?? $1.createdAt) }
    }

    private var hasAnySchedules: Bool {
        !ws.scheduledTasks.isEmpty
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                if !hasAnySchedules {
                    PortalEmptyState(
                        icon: "repeat.circle",
                        title: "No scheduled tasks",
                        subtitle: "Recurring and one-time automations you schedule through Spectra will appear here."
                    )
                } else {
                    VStack(alignment: .leading, spacing: 20) {
                        if !activeRecurring.isEmpty {
                            SchedulesSection(
                                title: "Active recurring",
                                subtitle: "These will keep running until you stop them."
                            ) {
                                ForEach(activeRecurring) { task in
                                    ScheduledTaskCard(
                                        task: task,
                                        isHighlighted: ws.highlightedScheduleID == task.id
                                    )
                                    .id(task.id)
                                }
                            }
                        }

                        if !pausedRecurring.isEmpty {
                            SchedulesSection(
                                title: "Paused recurring",
                                subtitle: "These stay visible and can be resumed anytime."
                            ) {
                                ForEach(pausedRecurring) { task in
                                    ScheduledTaskCard(
                                        task: task,
                                        isHighlighted: ws.highlightedScheduleID == task.id
                                    )
                                    .id(task.id)
                                }
                            }
                        }

                        if !pendingOneTime.isEmpty {
                            SchedulesSection(
                                title: "Pending one-time",
                                subtitle: "Upcoming tasks that have not fired yet."
                            ) {
                                ForEach(pendingOneTime) { task in
                                    ScheduledTaskCard(
                                        task: task,
                                        isHighlighted: ws.highlightedScheduleID == task.id
                                    )
                                    .id(task.id)
                                }
                            }
                        }

                        if !completedOneTime.isEmpty {
                            SchedulesSection(
                                title: "Completed one-time",
                                subtitle: "Finished or expired one-time tasks stay here for reference."
                            ) {
                                ForEach(completedOneTime) { task in
                                    ScheduledTaskCard(
                                        task: task,
                                        isHighlighted: ws.highlightedScheduleID == task.id
                                    )
                                    .id(task.id)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 24)
                }
            }
            .onAppear {
                ws.requestScheduledTasks()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                    scrollToHighlightedTask(using: proxy)
                }
            }
            .onChange(of: ws.scheduledTasks) { _, _ in
                scrollToHighlightedTask(using: proxy)
            }
            .onChange(of: ws.highlightedScheduleID) { _, _ in
                scrollToHighlightedTask(using: proxy)
            }
            .onDisappear {
                if !embedded {
                    ws.clearScheduleHighlight()
                }
            }
        }
    }

    private func scrollToHighlightedTask(using proxy: ScrollViewProxy) {
        guard let taskID = ws.highlightedScheduleID,
              ws.scheduledTasks.contains(where: { $0.id == taskID }) else { return }
        withAnimation(.easeInOut(duration: 0.25)) {
            proxy.scrollTo(taskID, anchor: .center)
        }
    }
}

private struct SchedulesSection<Content: View>: View {
    let title: String
    let subtitle: String
    let content: Content

    init(title: String, subtitle: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.subheadline).fontWeight(.semibold)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 12) {
                content
            }
        }
    }
}

private struct PortalEmptyState: View {
    let icon: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 36))
                .foregroundStyle(.secondary)
            Text(title)
                .font(.subheadline).fontWeight(.medium)
                .foregroundStyle(.secondary)
            Text(subtitle)
                .font(.caption)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
        }
        .padding(.top, 60)
    }
}

private struct ScheduledTaskCard: View {
    @EnvironmentObject var ws: WebSocketService
    let task: ScheduledTask
    let isHighlighted: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(task.task)
                        .font(.subheadline).fontWeight(.medium)
                        .lineLimit(2)
                    Text(task.recurrence)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                statusBadge
            }

            HStack(spacing: 14) {
                Label(task.isRecurring ? "Recurring" : "One-time", systemImage: task.isRecurring ? "repeat" : "calendar")
                Label("Run \(task.fireCount)x", systemImage: "arrow.clockwise")
            }
            .font(.caption2)
            .foregroundStyle(.secondary)

            TimelineView(.periodic(from: .now, by: 1)) { context in
                if let subtitle = secondaryStatusText(relativeTo: context.date) {
                    Text(subtitle)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            if let actionTitle {
                Button(action: performPrimaryAction) {
                    HStack {
                        Image(systemName: actionIcon)
                        Text(actionTitle)
                    }
                    .font(.caption).fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(actionBackground)
                    .foregroundStyle(actionForeground)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(12)
        .background(cardBackground)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isHighlighted ? DS.primary.opacity(0.8) : Color.clear, lineWidth: 1.5)
        )
        .shadow(color: isHighlighted ? DS.primary.opacity(0.18) : .clear, radius: 14, y: 6)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var cardBackground: some View {
        RoundedRectangle(cornerRadius: 12, style: .continuous)
            .fill(Color(.secondarySystemBackground))
            .overlay {
                if isHighlighted {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(DS.primary.opacity(0.10))
                }
            }
    }

    private var statusBadge: some View {
        Text(statusText)
            .font(.caption2).fontWeight(.semibold)
            .foregroundStyle(statusForeground)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(statusBackground)
            .clipShape(Capsule())
    }

    private var statusText: String {
        if task.isActiveRecurring {
            return "Active"
        }
        if task.isPausedRecurring {
            return "Paused"
        }
        if task.isPendingOneTime {
            return "Pending"
        }
        return "Completed"
    }

    private var statusForeground: Color {
        if task.isActiveRecurring || task.isPendingOneTime {
            return DS.success
        }
        return .secondary
    }

    private var statusBackground: Color {
        if task.isActiveRecurring || task.isPendingOneTime {
            return DS.success.opacity(0.12)
        }
        return Color.secondary.opacity(0.12)
    }

    private var actionTitle: String? {
        if task.isActiveRecurring {
            return "Stop recurring"
        }
        if task.isPausedRecurring {
            return "Resume"
        }
        if task.isPendingOneTime {
            return "Cancel scheduled task"
        }
        return nil
    }

    private var actionIcon: String {
        if task.isPausedRecurring {
            return "play.circle.fill"
        }
        return task.isRecurring ? "stop.circle.fill" : "xmark.circle.fill"
    }

    private var actionBackground: Color {
        if task.isPausedRecurring {
            return DS.primaryTint
        }
        return DS.danger.opacity(0.10)
    }

    private var actionForeground: Color {
        if task.isPausedRecurring {
            return DS.primary
        }
        return DS.danger
    }

    private func secondaryStatusText(relativeTo now: Date) -> String? {
        if task.isActiveRecurring, let nextRun = task.nextRun {
            return "Next run \(relativeDate(nextRun, relativeTo: now))"
        }
        if task.isPausedRecurring, let lastFiredAt = task.lastFiredAt {
            return "Paused after running \(relativeDate(lastFiredAt, relativeTo: now))"
        }
        if task.isPausedRecurring, let nextRunDisplay = task.nextRunDisplay, !nextRunDisplay.isEmpty {
            return "Paused. The next run will be recalculated from \(nextRunDisplay) when resumed."
        }
        if task.isPendingOneTime, let nextRunDisplay = task.nextRunDisplay, !nextRunDisplay.isEmpty {
            return "Scheduled for \(nextRunDisplay)"
        }
        if let lastFiredAt = task.lastFiredAt {
            return "Last ran \(relativeDate(lastFiredAt, relativeTo: now))"
        }
        return nil
    }

    private func performPrimaryAction() {
        if task.isActiveRecurring {
            ws.pauseScheduledTask(task.id)
        } else if task.isPausedRecurring {
            ws.resumeScheduledTask(task.id)
        } else if task.isPendingOneTime {
            ws.cancelScheduledTask(task.id)
        }
    }

    private func relativeDate(_ timestamp: Double, relativeTo now: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .full
        return formatter.localizedString(for: Date(timeIntervalSince1970: timestamp), relativeTo: now)
    }
}

// MARK: - Workflow Card (initial state → goal state)

private struct WorkflowCard: View {
    let sequence: LearnedSequence

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack {
                Image(systemName: "bolt.fill")
                    .font(.caption2)
                    .foregroundStyle(DS.primary)
                Text("Workflow")
                    .font(.caption).fontWeight(.semibold)
                    .foregroundStyle(DS.primary)
                Spacer()
                Text("Seen \(sequence.occurrenceCount)x")
                    .font(.caption2).fontWeight(.medium)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(DS.primary.opacity(0.8))
                    .clipShape(Capsule())
            }

            // Two-column: initial state → goal state
            HStack(alignment: .top, spacing: 8) {
                // Initial state
                StateBox(
                    label: "WHEN",
                    text: sequence.initialState ?? "Unknown trigger",
                    color: DS.primary
                )

                // Arrow
                VStack {
                    Spacer()
                    Image(systemName: "arrow.right")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(DS.primary.opacity(0.5))
                    Spacer()
                }
                .frame(width: 20)

                // Goal state
                StateBox(
                    label: "THEN",
                    text: sequence.goalState ?? "Unknown action",
                    color: DS.success
                )
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

private struct StateBox: View {
    let label: String
    let text: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(color)
            Text(text)
                .font(.caption)
                .foregroundStyle(.primary)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(color.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Workflow Detail Sheet

private struct WorkflowDetailSheet: View {
    let sequence: LearnedSequence
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // WHEN section
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 6) {
                            Circle().fill(DS.primary).frame(width: 8, height: 8)
                            Text("WHEN")
                                .font(.caption).fontWeight(.bold)
                                .foregroundStyle(DS.primary)
                        }
                        Text(sequence.initialState ?? "Unknown trigger")
                            .font(.body)
                            .foregroundStyle(.primary)
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(DS.primary.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    // Arrow
                    HStack {
                        Spacer()
                        Image(systemName: "arrow.down")
                            .font(.title3.weight(.bold))
                            .foregroundStyle(DS.primary.opacity(0.4))
                        Spacer()
                    }

                    // THEN section
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 6) {
                            Circle().fill(DS.success).frame(width: 8, height: 8)
                            Text("THEN")
                                .font(.caption).fontWeight(.bold)
                                .foregroundStyle(DS.success)
                        }
                        Text(sequence.goalState ?? "Unknown action")
                            .font(.body)
                            .foregroundStyle(.primary)
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(DS.success.opacity(0.06))
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    // Meta
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Details")
                            .font(.caption).fontWeight(.semibold)
                            .foregroundStyle(.secondary)

                        HStack(spacing: 16) {
                            Label("Seen \(sequence.occurrenceCount)x", systemImage: "arrow.clockwise")
                            Label(formatDate(sequence.createdAt), systemImage: "calendar")
                        }
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    }
                    .padding(.top, 8)

                    // Raw actions
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Raw actions observed")
                            .font(.caption).fontWeight(.semibold)
                            .foregroundStyle(.secondary)

                        ForEach(Array(sequence.actions.enumerated()), id: \.offset) { i, action in
                            HStack(alignment: .top, spacing: 8) {
                                Text("\(i + 1).")
                                    .font(.caption2).monospacedDigit()
                                    .foregroundStyle(.tertiary)
                                    .frame(width: 16, alignment: .trailing)
                                Text(action)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding(.top, 4)
                }
                .padding(20)
            }
            .navigationTitle("Workflow Detail")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private func formatDate(_ ts: Double) -> String {
        let date = Date(timeIntervalSince1970: ts)
        let fmt = DateFormatter()
        fmt.dateStyle = .medium
        fmt.timeStyle = .short
        return fmt.string(from: date)
    }
}

// MARK: - Action Row (timeline)

private struct ActionRow: View {
    let entry: ActionLogEntry
    let isFirst: Bool
    let isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(spacing: 0) {
                Rectangle()
                    .fill(isFirst ? .clear : Color.secondary.opacity(0.2))
                    .frame(width: 1.5, height: 8)
                Circle()
                    .fill(appColor)
                    .frame(width: 7, height: 7)
                Rectangle()
                    .fill(isLast ? .clear : Color.secondary.opacity(0.2))
                    .frame(width: 1.5)
                    .frame(maxHeight: .infinity)
            }
            .frame(width: 7)

            VStack(alignment: .leading, spacing: 2) {
                Text(entry.action)
                    .font(.caption)
                HStack(spacing: 4) {
                    Text(appShort)
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(appColor)
                    Text(formatTime(entry.timestamp))
                        .font(.system(size: 9))
                        .foregroundStyle(.tertiary)
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var appShort: String {
        entry.app.split(separator: ".").last.map(String.init) ?? entry.app
    }

    private var appColor: Color {
        let hash = abs(appShort.hashValue)
        let colors: [Color] = [DS.primary, DS.success, .orange, .pink, .cyan, .indigo]
        return colors[hash % colors.count]
    }

    private func formatTime(_ ts: Double) -> String {
        let date = Date(timeIntervalSince1970: ts)
        let fmt = DateFormatter()
        fmt.dateFormat = "h:mm a"
        return fmt.string(from: date)
    }
}
