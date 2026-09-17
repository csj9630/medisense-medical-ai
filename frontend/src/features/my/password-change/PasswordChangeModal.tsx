import { useEffect, useState, type FormEvent, type MouseEvent } from 'react';
import { X } from 'lucide-react';
import { changePassword } from './passwordChangeApi';
import './passwordChangeModal.css';

interface PasswordChangeModalProps {
  onClose: () => void;
}

export function PasswordChangeModal({ onClose }: PasswordChangeModalProps) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const closeWithEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeWithEscape);
    return () => window.removeEventListener('keydown', closeWithEscape);
  }, [onClose]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirm) {
      setError('새 비밀번호 확인이 일치하지 않습니다.');
      return;
    }

    setError('');
    setNotice('');
    setIsSubmitting(true);
    try {
      const result = await changePassword(currentPassword, newPassword, confirm);
      setNotice(result.message);
      setCurrentPassword('');
      setNewPassword('');
      setConfirm('');
      window.setTimeout(onClose, 900);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '비밀번호 변경에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const closeFromBackdrop = (event: MouseEvent<HTMLDivElement>) => {
    if (event.currentTarget === event.target) onClose();
  };

  return (
    <div className="password-modal-backdrop" role="presentation" onMouseDown={closeFromBackdrop}>
      <section className="password-modal" role="dialog" aria-modal="true" aria-labelledby="password-modal-title">
        <header className="password-modal-header">
          <div><p>SECURITY</p><h2 id="password-modal-title">비밀번호 변경</h2></div>
          <button type="button" aria-label="모달 닫기" onClick={onClose}><X size={18} /></button>
        </header>
        <form className="password-modal-form" onSubmit={submit}>
          <label>현재 비밀번호<input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} autoFocus required /></label>
          <label>새 비밀번호<input type="password" minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required /></label>
          <label>새 비밀번호 확인<input type="password" minLength={8} value={confirm} onChange={(e) => setConfirm(e.target.value)} required /></label>
          {error && <p className="password-modal-error">{error}</p>}
          {notice && <p className="password-modal-notice">{notice}</p>}
          <div className="password-modal-actions">
            <button type="button" className="modal-cancel-button" onClick={onClose}>취소</button>
            <button className="modal-submit-button" disabled={isSubmitting}>{isSubmitting ? '변경 중...' : '비밀번호 변경'}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
