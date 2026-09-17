import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';

/** 관리자(is_admin) 계정만 하위 라우트에 접근할 수 있게 막는다. 버튼을 비활성화해도
 * 주소창에 직접 /admin을 쳐서 들어오는 건 못 막으므로, 라우트 자체를 이걸로 감싼다. */
export function RequireAdmin() {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <p className="route-loading">권한을 확인하고 있습니다...</p>;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (!user.is_admin) return <Navigate to="/" replace />;
  return <Outlet />;
}
