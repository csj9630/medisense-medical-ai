import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { AuthCard } from '../components/AuthCard';
import { OAuthButtons } from '../components/OAuthButtons';

const REMEMBERED_EMAIL_KEY = 'thegpt_remembered_email';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState(() => localStorage.getItem(REMEMBERED_EMAIL_KEY) ?? '');
  const [password, setPassword] = useState('');
  // 저장된 이메일이 있으면(=예전에 체크하고 로그인한 적 있으면) 기본으로 다시 체크해둔다.
  const [rememberEmail, setRememberEmail] = useState(() => Boolean(localStorage.getItem(REMEMBERED_EMAIL_KEY)));
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      await login(email, password);
      // 비밀번호는 절대 저장하지 않는다 — 아이디(이메일)만 다음 방문을 위해 남긴다.
      if (rememberEmail) {
        localStorage.setItem(REMEMBERED_EMAIL_KEY, email);
      } else {
        localStorage.removeItem(REMEMBERED_EMAIL_KEY);
      }
      // 로그인에 성공하면 항상 메인 페이지로 이동합니다.
      navigate('/', { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '로그인에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthCard title="로그인" description="계정으로 로그인하고 상담 기록을 확인하세요.">
      <form className="auth-form" onSubmit={submit}>
        <div className="auth-field"><label htmlFor="login-email">이메일</label><input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="auth-field"><label htmlFor="login-password">비밀번호</label><input id="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        <div className="auth-options">
          <label className="remember-me" htmlFor="login-remember">
            <input
              id="login-remember"
              type="checkbox"
              checked={rememberEmail}
              onChange={(e) => setRememberEmail(e.target.checked)}
            />
            아이디 저장
          </label>
          <Link to="/forgot-password">비밀번호를 잊으셨나요?</Link>
        </div>
        {error && <p className="form-error">{error}</p>}
        <button className="auth-button" disabled={isSubmitting}>{isSubmitting ? '로그인 중...' : '로그인'}</button>
      </form>
      <OAuthButtons />
      <p className="auth-links">계정이 없나요? <Link to="/signup">회원가입</Link></p>
    </AuthCard>
  );
}
