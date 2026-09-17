import { BrainCircuit } from "lucide-react";

export function AdminHeader() {
  return (
    <header className="admin-hero">
      <div className="admin-hero-icon" aria-hidden="true">
        <BrainCircuit size={27} />
      </div>
      <div>
        <span className="admin-eyebrow">ADMIN EXPERIMENT SPACE</span>
        <h1>관리자 페이지</h1>
        <p>
          RAG 문서 준비 상태를 시험하고 여러 LLM의 응답을 같은 조건에서
          비교합니다.
        </p>
      </div>
    </header>
  );
}
