import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthCard } from '../components/AuthCard';
import { OAuthButtons } from '../components/OAuthButtons';
import { signupApi } from './signupApi';

export function SignupPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (password !== passwordConfirm) {
      setError('비밀번호 확인이 일치하지 않습니다.');
      return;
    }
    setError('');
    setIsSubmitting(true);
    try {
      const result = await signupApi.signup(email, password);
      navigate('/verify-email', {
        state: { email, devCode: result.dev_verification_code },
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '회원가입에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthCard title="회원가입" description="이메일 인증 후 MediSense를 이용할 수 있습니다.">
      <form className="auth-form" onSubmit={submit}>
        <div className="auth-field"><label htmlFor="signup-email">이메일</label><input id="signup-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="auth-field"><label htmlFor="signup-password">비밀번호</label><input id="signup-password" type="password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        <div className="auth-field"><label htmlFor="signup-confirm">비밀번호 확인</label><input id="signup-confirm" type="password" minLength={8} value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)} required /></div>
        {error && <p className="form-error">{error}</p>}
        <button className="auth-button" disabled={isSubmitting}>{isSubmitting ? '가입 중...' : '회원가입'}</button>
      </form>
      <OAuthButtons />
      <p className="auth-links">이미 계정이 있나요? <Link to="/login">로그인</Link></p>
    </AuthCard>
  );
}
