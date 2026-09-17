import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { AuthCard } from '../components/AuthCard';
import { passwordResetApi } from './passwordResetApi';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [notice, setNotice] = useState('');
  const [devUrl, setDevUrl] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setIsSubmitting(true);
    try {
      const result = await passwordResetApi.request(email);
      setNotice(result.message); setDevUrl(result.dev_reset_url ?? '');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '재설정 메일 발송에 실패했습니다.');
    } finally { setIsSubmitting(false); }
  };

  return <AuthCard title="비밀번호 찾기" description="가입한 이메일로 비밀번호 재설정 링크를 보내드립니다.">
    <form className="auth-form" onSubmit={submit}>
      <div className="auth-field"><label htmlFor="forgot-email">이메일</label><input id="forgot-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
      {notice && <p className="form-notice">{notice}</p>}
      {/* SMTP가 없는 로컬 환경에서만 테스트 링크가 나타납니다. */}
      {devUrl && <a className="dev-reset-link" href={devUrl}>개발용 재설정 링크 열기</a>}
      {error && <p className="form-error">{error}</p>}
      <button className="auth-button" disabled={isSubmitting}>{isSubmitting ? '발송 중...' : '재설정 링크 받기'}</button>
    </form>
    <p className="auth-links"><Link to="/login">로그인으로 돌아가기</Link></p>
  </AuthCard>;
}
