import "@fontsource-variable/manrope";
import "./styles.css";

import type { Metadata } from "next";


const description = "自动理解学习目标，用计划、练习、资料和证据陪你持续进步。";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.REFINEQ_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  applicationName: "RefineQ",
  title: {
    default: "RefineQ · 个人学习 Agent",
    template: "%s · RefineQ",
  },
  description,
  icons: {
    icon: "/icon.svg",
  },
  openGraph: {
    type: "website",
    locale: "zh_CN",
    siteName: "RefineQ",
    title: "RefineQ · 个人学习 Agent",
    description,
    images: [
      {
        url: "/assets/refineq-learning-illustration.png",
        width: 1254,
        height: 1254,
        alt: "RefineQ 个人学习 Agent",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "RefineQ · 个人学习 Agent",
    description,
    images: ["/assets/refineq-learning-illustration.png"],
  },
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
