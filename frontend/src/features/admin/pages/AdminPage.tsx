import { useState } from "react";
import { AdminHeader } from "../components/AdminHeader";
import { AdminTabs } from "../components/AdminTabs";
import { EvaluationPanel } from "../components/evaluation/EvaluationPanel";
import { LlmPanel } from "../components/llm/LlmPanel";
import { OcrPanel } from "../components/ocr/OcrPanel";
import type { AdminTab } from "../types/common";
import "../admin.css";

export function AdminPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>("ocr");
  return (
    <div className="admin-page">
      <AdminHeader />
      <AdminTabs value={activeTab} onChange={setActiveTab} />
      <div
        id="ocr-tabpanel"
        role="tabpanel"
        aria-labelledby="ocr-tab"
        className="admin-tabpanel"
        hidden={activeTab !== "ocr"}
      >
        <OcrPanel />
      </div>
      <div
        id="llm-tabpanel"
        role="tabpanel"
        aria-labelledby="llm-tab"
        className="admin-tabpanel"
        hidden={activeTab !== "llm"}
      >
        <LlmPanel />
      </div>
      <div
        id="eval-tabpanel"
        role="tabpanel"
        aria-labelledby="eval-tab"
        className="admin-tabpanel"
        hidden={activeTab !== "eval"}
      >
        <EvaluationPanel />
      </div>
    </div>
  );
}
