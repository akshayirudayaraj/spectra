import SwiftUI

struct ResultView: View {
    @EnvironmentObject var ws: WebSocketService
    /// Pops the whole task flow so home is visible again.
    var onNewTask: () -> Void = {}

    private var result: TaskResult? { ws.taskResult }
    private var success: Bool { result?.success ?? false }

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            // Success / failure icon
            Image(systemName: success ? "checkmark.circle.fill" : "xmark.circle.fill")
                .font(.system(size: 64))
                .foregroundStyle(success ? DS.success : DS.danger)

            // Summary
            Text(result?.summary ?? "Task finished")
                .font(.system(size: 16, weight: .semibold))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            // Stats pills
            if let result = result {
                HStack(spacing: 12) {
                    StatPill(text: "\(result.steps) steps")
                    StatPill(text: "\(String(format: "%.1f", result.duration))s")
                    if !ws.memoryItems.isEmpty {
                        StatPill(text: "\(ws.memoryItems.count) saved")
                    }
                }
            }

            if let schedule = ws.lastCreatedSchedule, schedule.isRecurring {
                RecurringScheduleSummaryCard(schedule: schedule)
                    .padding(.horizontal, 20)
            }

            // Memory section
            if !ws.memoryItems.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("MEMORY")
                        .font(.caption).fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                    FlowLayout(spacing: 8) {
                        ForEach(ws.memoryItems) { item in
                            MemoryPill(item: item)
                        }
                    }
                }
                .padding(.horizontal, 20)
            }

            Spacer()

            // New task button — pop entire task stack back to home
            Button {
                onNewTask()
            } label: {
                Text("New task")
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(DS.primary)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: DS.cardRadius))
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 16)
        }
        .navigationBarBackButtonHidden(true)
    }
}

private struct RecurringScheduleSummaryCard: View {
    @EnvironmentObject var ws: WebSocketService
    let schedule: ScheduledTask

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(schedule.enabled ? "Recurring schedule ready" : "Recurring schedule paused")
                        .font(.caption).fontWeight(.semibold)
                        .foregroundStyle(schedule.enabled ? DS.primary : .secondary)
                    Text(schedule.task)
                        .font(.subheadline).fontWeight(.semibold)
                        .foregroundStyle(.primary)
                        .lineLimit(2)
                    Text(schedule.recurrence)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    ws.dismissLastCreatedSchedule()
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .padding(6)
                        .background(Color(.tertiarySystemFill))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }

            TimelineView(.periodic(from: .now, by: 1)) { context in
                if let subtitle = scheduleSubtitle(relativeTo: context.date) {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 10) {
                Button {
                    if schedule.enabled {
                        ws.pauseScheduledTask(schedule.id)
                    } else {
                        ws.resumeScheduledTask(schedule.id)
                    }
                } label: {
                    Text(schedule.enabled ? "Stop recurring" : "Resume")
                        .font(.caption).fontWeight(.semibold)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 11)
                        .background(schedule.enabled ? DS.danger.opacity(0.12) : DS.primaryTint)
                        .foregroundStyle(schedule.enabled ? DS.danger : DS.primary)
                        .clipShape(RoundedRectangle(cornerRadius: DS.buttonRadius))
                }
                .buttonStyle(.plain)

                NavigationLink {
                    SchedulesDashboardView()
                        .environmentObject(ws)
                } label: {
                    Text("View schedules")
                        .font(.caption).fontWeight(.semibold)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 11)
                        .background(Color(.tertiarySystemBackground))
                        .overlay(
                            RoundedRectangle(cornerRadius: DS.buttonRadius)
                                .stroke(DS.primary.opacity(0.18), lineWidth: 1)
                        )
                        .foregroundStyle(.primary)
                        .clipShape(RoundedRectangle(cornerRadius: DS.buttonRadius))
                }
                .simultaneousGesture(TapGesture().onEnded {
                    ws.highlightedScheduleID = schedule.id
                })
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .overlay(
            RoundedRectangle(cornerRadius: DS.cardRadius)
                .stroke(schedule.enabled ? DS.primary.opacity(0.18) : Color.primary.opacity(0.10), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: DS.cardRadius))
    }

    private func scheduleSubtitle(relativeTo now: Date) -> String? {
        if schedule.enabled, let nextRun = schedule.nextRun {
            return "Next run \(relativeDate(nextRun, relativeTo: now))"
        }
        if schedule.enabled, let nextRunDisplay = schedule.nextRunDisplay, !nextRunDisplay.isEmpty {
            return "Next run \(nextRunDisplay)"
        }
        if let lastFiredAt = schedule.lastFiredAt {
            return "Paused after running \(relativeDate(lastFiredAt, relativeTo: now))"
        }
        return "Paused. Resume whenever you want it to start again."
    }

    private func relativeDate(_ timestamp: Double, relativeTo now: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .full
        return formatter.localizedString(for: Date(timeIntervalSince1970: timestamp), relativeTo: now)
    }
}

private struct StatPill: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.caption).fontWeight(.medium)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color(.secondarySystemBackground))
            .clipShape(Capsule())
    }
}
