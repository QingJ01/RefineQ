import type { Metadata } from "next";

import { GlobalCalendarRoute } from "@/components/global-calendar-route";


export const metadata: Metadata = {
  title: "总日历",
  description: "汇总查看所有 RefineQ 学习空间的任务与学习时间。",
};

export default function CalendarPage() {
  return <GlobalCalendarRoute />;
}
