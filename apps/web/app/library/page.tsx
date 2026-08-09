import type { Metadata } from "next";

import { GlobalMaterialLibraryRoute } from "@/components/global-material-library-route";

export const metadata: Metadata = { title: "总资料库" };

export default function LibraryPage() {
  return <GlobalMaterialLibraryRoute />;
}
