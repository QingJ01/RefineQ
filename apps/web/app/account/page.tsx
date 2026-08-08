import type { Metadata } from "next";

import { AccountRoute } from "@/components/account-center";


export const metadata: Metadata = {
  title: "账户与安全",
  description: "管理 RefineQ 账户、登录凭据与个人学习数据。",
};

export default function AccountPage() {
  return <AccountRoute />;
}
