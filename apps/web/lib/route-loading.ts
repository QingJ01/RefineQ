import type { Locale } from "./types";


export function routeLoadingText(pathname: string, locale: Locale) {
  const route = pathname.startsWith("/admin")
    ? "admin"
    : pathname.startsWith("/account")
      ? "account"
      : pathname.startsWith("/learn")
        ? "learn"
        : "home";

  const copy = locale === "zh"
    ? {
      admin: {
        aria: "正在验证管理员权限",
        kicker: "权限验证",
        title: "正在验证管理员控制台",
        body: "正在确认管理员身份并读取受保护的运行信息。",
      },
      account: {
        aria: "正在验证账户访问权限",
        kicker: "安全验证",
        title: "正在验证账户安全设置",
        body: "正在确认登录状态并读取你的账户与安全设置。",
      },
      learn: {
        aria: "正在恢复学习空间",
        kicker: "恢复学习现场",
        title: "正在恢复学习空间",
        body: "正在恢复当前目标、计划、练习草稿与最近进度。",
      },
      home: {
        aria: "正在准备学习首页",
        kicker: "准备学习首页",
        title: "正在准备学习首页",
        body: "正在读取最近的学习空间与下一步建议。",
      },
    }
    : {
      admin: {
        aria: "Verifying administrator access",
        kicker: "Access check",
        title: "Verifying administrator access",
        body: "Confirming administrator identity before loading protected operations data.",
      },
      account: {
        aria: "Verifying account access",
        kicker: "Security check",
        title: "Verifying account access",
        body: "Confirming your session before loading account and security settings.",
      },
      learn: {
        aria: "Restoring learning workspace",
        kicker: "Restoring your session",
        title: "Restoring learning workspace",
        body: "Restoring the current goal, plan, practice draft, and recent progress.",
      },
      home: {
        aria: "Preparing learning home",
        kicker: "Preparing home",
        title: "Preparing learning home",
        body: "Loading recent learning spaces and the next recommended action.",
      },
    };

  return copy[route];
}
