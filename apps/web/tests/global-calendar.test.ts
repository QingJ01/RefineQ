import { describe, expect, it } from "vitest";

import {
  calendarDateKey,
  calendarGridRange,
  filterCalendarTasks,
  groupCalendarTasks,
  summarizeCalendarTasks,
  workspaceColorIndex,
} from "../lib/global-calendar";
import type { CalendarTask } from "../lib/types";


const tasks: CalendarTask[] = [
  {
    id: "session-math-1",
    workspace_id: "math",
    workspace_title: "Mathematics",
    workspace_archived: false,
    topic_id: "limits",
    topic_label: "Limits",
    planned_at: "2026-08-08T01:00:00.000Z",
    minutes: 30,
    activity: "practice",
    status: "planned",
  },
  {
    id: "session-english-1",
    workspace_id: "english",
    workspace_title: "English",
    workspace_archived: false,
    topic_id: "speaking",
    topic_label: "Speaking",
    planned_at: "2026-08-08T09:00:00.000Z",
    minutes: 45,
    activity: "apply",
    status: "completed",
  },
  {
    id: "session-math-2",
    workspace_id: "math",
    workspace_title: "Mathematics",
    workspace_archived: false,
    topic_id: "derivatives",
    topic_label: "Derivatives",
    planned_at: "2026-08-09T01:00:00.000Z",
    minutes: 60,
    activity: "learn",
    status: "planned",
  },
];


describe("global calendar view model", () => {
  it("builds a fixed six-week local calendar range", () => {
    const range = calendarGridRange(new Date(2026, 7, 18));

    expect(calendarDateKey(range.startsAt)).toBe("2026-07-26");
    expect(calendarDateKey(new Date(range.endsAt.getTime() - 1))).toBe("2026-09-05");
    expect((range.endsAt.getTime() - range.startsAt.getTime()) / 86_400_000).toBe(42);
  });

  it("groups tasks by the learner's local date and preserves API order", () => {
    const grouped = groupCalendarTasks(tasks);

    expect(grouped.get("2026-08-08")?.map((task) => task.id)).toEqual([
      "session-math-1",
      "session-english-1",
    ]);
    expect(grouped.get("2026-08-09")?.map((task) => task.id)).toEqual([
      "session-math-2",
    ]);
  });

  it("filters by workspace and calculates visible summary values", () => {
    const visible = filterCalendarTasks(tasks, new Set(["math"]));

    expect(visible.map((task) => task.id)).toEqual(["session-math-1", "session-math-2"]);
    expect(filterCalendarTasks(tasks, new Set())).toEqual(tasks);
    expect(summarizeCalendarTasks(visible)).toEqual({
      tasks: 2,
      minutes: 90,
      workspaces: 1,
    });
  });

  it("assigns stable workspace color slots", () => {
    expect(workspaceColorIndex("math")).toBe(workspaceColorIndex("math"));
    expect(workspaceColorIndex("math")).toBeGreaterThanOrEqual(0);
    expect(workspaceColorIndex("math")).toBeLessThan(8);
  });
});

