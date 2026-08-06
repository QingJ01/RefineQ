import "@fontsource-variable/manrope";
import "@fontsource-variable/newsreader";
import "./styles.css";

import type { Metadata } from "next";


export const metadata: Metadata = {
  title: "RefineQ — Personal Learning Agent",
  description: "Evidence-driven study planning, practice, materials, and coaching.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
