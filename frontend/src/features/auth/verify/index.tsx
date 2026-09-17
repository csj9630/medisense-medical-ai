import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AuthCard } from '../components/AuthCard';
import { verificationApi } from './verificationApi';

interface VerifyLocationState { email?: string; devCode?: string | null }

export function VerifyEmailPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as VerifyLocationState | null;
  const [email, setEmail] = useState(state?.email ?? '');
  const [code, setCode] = useState(state?.devCode ?? '');
  const [notice, setNotice] = useState(state?.devCode ? `개발용 인증 코드: ${state.devCode}` : '');
  const [error, setError] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    try {
      await verificationApi.verifyEmail(email, code);
      navigate('/login', { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '인증에 실패했습니다.');
    }
  };

  const resend = async () => {
    setError('');
    try {
      const result = await verificationApi.resendVerification(email);
      setNotice(result.dev_verification_code ? `개발용 인증 코드: ${result.dev_verification_code}` : result.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '재발송에 실패했습니다.');
    }
  };

  return (
    <AuthCard title="이메일 인증" description="메일로 받은 6자리 인증 코드를 입력해주세요.">
      <form className="auth-form" onSubmit={submit}>
        <div className="auth-field"><label htmlFor="verify-email">이메일</label><input id="verify-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="auth-field"><label htmlFor="verify-code">인증 코드</label><input id="verify-code" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} required /></div>
        {notice && <p className="form-notice">{notice}</p>}
        {error && <p className="form-error">{error}</p>}
        <button className="auth-button">인증 완료</button>
      </form>
      <p className="auth-links"><button className="text-button" type="button" onClick={resend}>인증 코드 다시 받기</button> · <Link to="/login">로그인</Link></p>
    </AuthCard>
  );
}
