export interface PlanSettingsDraft {
  goal: string;
  examDate: string;
  dailyMinutes: number;
  topicOrder: string[];
  availableTopics: string[];
}

export type PlanSettingsErrors = Partial<Record<
  "goal" | "examDate" | "dailyMinutes" | "topicOrder",
  string
>>;

export function validatePlanSettings(
  draft: PlanSettingsDraft,
  now = new Date(),
): PlanSettingsErrors {
  const errors: PlanSettingsErrors = {};
  if (!draft.goal.trim()) errors.goal = "goal_required";
  const today = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.examDate) || draft.examDate <= today) {
    errors.examDate = "future_date_required";
  }
  if (!Number.isInteger(draft.dailyMinutes) || draft.dailyMinutes < 5 || draft.dailyMinutes > 480) {
    errors.dailyMinutes = "minutes_out_of_range";
  }
  if (
    draft.topicOrder.length !== new Set(draft.topicOrder).size
    || draft.topicOrder.length !== draft.availableTopics.length
    || draft.topicOrder.some((topic) => !draft.availableTopics.includes(topic))
  ) {
    errors.topicOrder = "topic_order_invalid";
  }
  return errors;
}
