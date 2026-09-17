import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth } from '../AuthContext';
import { AuthCard } from '../components/AuthCard';

// 백엔드(app/api/auth/oauth_router.py)가 Google/GitHub 콜백을 처리한 뒤 여기로
// 리다이렉트한다 - 성공하면 ?token=, 실패/취소하면 ?error=가 붙어서 온다.
export function OAuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const { loginWithToken } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  // StrictMode가 effect를 두 번 실행해도 loginWithToken(토큰 검증 API 호출)이
  // 두 번 나가지 않도록 막는다.
  const handledRef = useRef(false);

  useEffect(() => {
    if (handledRef.current) return;
    handledRef.current = true;

    const token = searchParams.get('token');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setError(
        errorParam === 'cancelled'
          ? '로그인이 취소되었습니다.'
          : decodeURIComponent(errorParam),
      );
      return;
    }
    if (!token) {
      setError('로그인 정보를 받지 못했습니다.');
      return;
    }

    loginWithToken(token)
      .then(() => navigate('/', { replace: true }))
      .catch(() => setError('로그인 처리 중 문제가 발생했습니다.'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <AuthCard title="로그인 실패" description="">
        <p className="form-error">{error}</p>
        <p className="auth-links">
          <button type="button" className="text-button" onClick={() => navigate('/login', { replace: true })}>
            로그인 페이지로 돌아가기
          </button>
        </p>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="로그인 중..." description="">
      <div style={{ display: 'flex', justifyContent: 'center', padding: '24px 0' }}>
        <Loader2 className="animate-spin" />
      </div>
    </AuthCard>
  );
}
