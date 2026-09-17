import { useState } from 'react';
import { myPageApi } from '../myPageApi';

interface ConsultationDeleteModalProps {
  onClose: () => void;
  onDeleted: () => void;
}

export function ConsultationDeleteModal({ onClose, onDeleted }: ConsultationDeleteModalProps) {
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const remove = async () => {
    setError(''); setIsSubmitting(true);
    try {
      await myPageApi.deleteAllConsultations();
      onDeleted(); onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '상담 데이터 삭제에 실패했습니다.');
      setIsSubmitting(false);
    }
  };

  return <div className="password-modal-backdrop" role="presentation">
    <section className="password-modal" role="dialog" aria-modal="true" aria-labelledby="delete-consultations-title">
      <header className="password-modal-header"><div><p>DATA</p><h2 id="delete-consultations-title">모든 상담 데이터 삭제</h2></div></header>
      <p className="delete-warning">모든 상담과 메시지, 첨부 기록이 영구적으로 삭제되며 복구할 수 없습니다. 계정은 유지됩니다.</p>
      {error && <p className="password-modal-error">{error}</p>}
      <div className="password-modal-actions consultation-delete-actions">
        <button type="button" className="modal-cancel-button" onClick={onClose}>취소</button>
        <button type="button" className="delete-confirm-button" onClick={remove} disabled={isSubmitting}>{isSubmitting ? '삭제 중...' : '모두 삭제'}</button>
      </div>
    </section>
  </div>;
}
