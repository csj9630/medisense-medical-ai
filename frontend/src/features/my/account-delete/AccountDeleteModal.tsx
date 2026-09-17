import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { myPageApi } from '../myPageApi';

export function AccountDeleteModal({ onClose }: { onClose: () => void }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  // 소셜 로그인/게스트 계정은 비밀번호가 없어서 입력받을 게 없다.
  const needsPassword = user?.has_password ?? true;

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setIsSubmitting(true);
    try {
      await myPageApi.deleteAccount(needsPassword ? password : undefined);
      logout(); navigate('/', { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '회원 탈퇴에 실패했습니다.');
      setIsSubmitting(false);
    }
  };

  return <div className="password-modal-backdrop" role="presentation">
    <section className="password-modal" role="dialog" aria-modal="true" aria-labelledby="delete-account-title">
      <header className="password-modal-header"><div><p>ACCOUNT</p><h2 id="delete-account-title">회원 탈퇴</h2></div></header>
      <p className="delete-warning">탈퇴하면 계정과 상담 기록이 삭제되며 복구할 수 없습니다.</p>
      <form className="password-modal-form" onSubmit={submit}>
        {needsPassword && (
          <label>현재 비밀번호<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus required /></label>
        )}
        {error && <p className="password-modal-error">{error}</p>}
        <div className="password-modal-actions">
          <button type="button" className="modal-cancel-button" onClick={onClose}>취소</button>
          <button className="delete-confirm-button" disabled={isSubmitting}>{isSubmitting ? '처리 중...' : '회원 탈퇴'}</button>
        </div>
      </form>
    </section>
  </div>;
}
