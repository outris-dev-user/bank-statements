import { createRoot } from "react-dom/client";
import App from "./app/App.tsx";
import { DemoGate } from "./app/components/DemoGate.tsx";
import "./styles/index.css";

createRoot(document.getElementById("root")!).render(
  <DemoGate>
    <App />
  </DemoGate>,
);
