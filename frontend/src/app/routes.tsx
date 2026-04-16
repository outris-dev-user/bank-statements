import { createBrowserRouter } from "react-router";
import { Root } from "./components/Root";
import { CaseDashboard } from "./components/CaseDashboard";
import { CaseOverview } from "./components/CaseOverview";
import { Workbench } from "./components/Workbench";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Root,
    children: [
      { index: true, Component: CaseDashboard },
      { path: "cases/:caseId", Component: CaseOverview },
      { path: "cases/:caseId/workbench", Component: Workbench },
    ],
  },
]);
