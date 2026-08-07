import "@fontsource-variable/manrope";
import "./styles.css";

import type { Metadata } from "next";


export const metadata: Metadata = {
  title: "RefineQ · 个人学习 Agent",
  description: "自动理解学习目标，用计划、练习、资料和证据陪你持续进步。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">跳到主要内容</a>
        {children}
      </body>
    </html>
  );
}
