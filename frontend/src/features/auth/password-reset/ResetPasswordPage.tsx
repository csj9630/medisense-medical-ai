import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AuthCard } from '../components/AuthCard';
import { passwordResetApi } from './passwordResetApi';

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') ?? '';
  const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState(token ? '' : '재설정 토큰이 없습니다. 이메일 링크를 다시 확인해주세요.');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isValidating, setIsValidating] = useState(Boolean(token));
  const [isTokenValid, setIsTokenValid] = useState(false);

  useEffect(() => {
    if (!token) return;

    // 링크에 다시 들어왔을 때 만료되거나 이미 사용된 토큰인지 즉시 검사합니다.
    passwordResetApi.validate(token)
      .then(() => setIsTokenValid(true))
      .catch((reason) => setError(
        reason instanceof Error ? reason.message : '재설정 링크가 만료되었습니다.',
      ))
      .finally(() => setIsValidating(false));
  }, [token]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (password !== confirm) { setError('비밀번호 확인이 일치하지 않습니다.'); return; }
    setError(''); setIsSubmitting(true);
    try {
      const result = await passwordResetApi.reset(token, password);
      setNotice(result.message); setPassword(''); setConfirm('');
      // 안내 문구가 잠시 보인 뒤 로그인 화면으로 이동합니다.
      window.setTimeout(() => navigate('/login', { replace: true }), 800);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '비밀번호 변경에 실패했습니다.');
    } finally { setIsSubmitting(false); }
  };

  if (isValidating) {
    return <AuthCard title="링크 확인 중" description="비밀번호 재설정 링크를 확인하고 있습니다."><p className="form-notice">잠시만 기다려주세요.</p></AuthCard>;
  }

  return <AuthCard title="비밀번호 재설정" description="새로 사용할 비밀번호를 입력해주세요.">
    <form className="auth-form" onSubmit={submit}>
      <div className="auth-field"><label htmlFor="new-password">새 비밀번호</label><input id="new-password" type="password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
      <div className="auth-field"><label htmlFor="confirm-password">비밀번호 확인</label><input id="confirm-password" type="password" minLength={8} value={confirm} onChange={(e) => setConfirm(e.target.value)} required /></div>
      {notice && <p className="form-notice">{notice}</p>}{error && <p className="form-error">{error}</p>}
      <button className="auth-button" disabled={isSubmitting || !isTokenValid}>{isSubmitting ? '변경 중...' : '비밀번호 변경'}</button>
    </form>
    <p className="auth-links"><Link to="/login">로그인으로 이동</Link></p>
  </AuthCard>;
}
