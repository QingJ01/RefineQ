import type { CalendarTask } from "./types";


export const WORKSPACE_COLOR_COUNT = 8;

export function calendarDateKey(value: Date | string): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

export function calendarGridRange(month: Date): { startsAt: Date; endsAt: Date } {
  const startsAt = new Date(month.getFullYear(), month.getMonth(), 1);
  startsAt.setDate(startsAt.getDate() - startsAt.getDay());
  const endsAt = new Date(startsAt);
  endsAt.setDate(endsAt.getDate() + 42);
  return { startsAt, endsAt };
}

export function groupCalendarTasks(tasks: CalendarTask[]): Map<string, CalendarTask[]> {
  const grouped = new Map<string, CalendarTask[]>();
  for (const task of tasks) {
    const key = calendarDateKey(task.planned_at);
    grouped.set(key, [...(grouped.get(key) ?? []), task]);
  }
  return grouped;
}

export function filterCalendarTasks(
  tasks: CalendarTask[],
  workspaceIds: ReadonlySet<string>,
): CalendarTask[] {
  if (workspaceIds.size === 0) return tasks;
  return tasks.filter((task) => workspaceIds.has(task.workspace_id));
}

export function summarizeCalendarTasks(tasks: CalendarTask[]): {
  tasks: number;
  minutes: number;
  workspaces: number;
} {
  return {
    tasks: tasks.length,
    minutes: tasks.reduce((total, task) => total + task.minutes, 0),
    workspaces: new Set(tasks.map((task) => task.workspace_id)).size,
  };
}

export function workspaceColorIndex(workspaceId: string): number {
  let hash = 0;
  for (const character of workspaceId) {
    hash = (hash * 31 + character.codePointAt(0)!) >>> 0;
  }
  return hash % WORKSPACE_COLOR_COUNT;
}
