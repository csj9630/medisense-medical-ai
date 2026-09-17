import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { PasswordChangeModal } from './password-change/PasswordChangeModal';
import { ProfileImageUploader } from './profile-image/ProfileImageUploader';
import { AccountDeleteModal } from './account-delete/AccountDeleteModal';
import { ModelPreference } from './ModelPreference';
import { myPageApi, type UsageSummary } from './myPageApi';
import { ConsultationDeleteModal } from './consultation-delete/ConsultationDeleteModal';
import './myPage.css';

export function MyPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isConsultationDeleteOpen, setIsConsultationDeleteOpen] = useState(false);
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  useEffect(() => { myPageApi.getUsage().then(setUsage).catch(() => setUsage(null)); }, []);

  const formatDate = (value?: string | null) => value
    ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
    : '기록 없음';

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <section className="my-page overflow-y-auto p-8">
      <header><p>MY PAGE</p><h1>마이 페이지</h1></header>
      <div className="profile-panel">
        <ProfileImageUploader />
        <div>
          <h2>계정 관리</h2>
          <p>프로필 이미지와 이메일 인증 상태를 확인하고 비밀번호를 변경할 수 있습니다.</p>
        </div>
      </div>
      <div className="profile-form">
        <label>
          <span className="email-label">
            이메일
            <span className={user?.is_email_verified ? 'verification-status verified' : 'verification-status unverified'}>
              <span className="status-dot" aria-hidden="true" />
              {user?.is_email_verified ? '( 인증된 유저 )' : '( 인증이 안된 유저 )'}
            </span>
          </span>
          <input value={user?.email ?? ''} readOnly />
        </label>
        {user?.has_password && (
          <div className="password-change-field">
            <span>비밀번호 변경</span>
            <button className="password-change-button" onClick={() => setIsPasswordModalOpen(true)}>
              비밀번호 변경
            </button>
          </div>
        )}
        <label>계정 생성일<input value={formatDate(user?.created_at)} readOnly /></label>
      </div>

      <section className="mypage-section">
        <h2>이용 현황</h2>
        <div className="summary-grid">
          <article><span>전체 상담 수</span><strong>{usage?.consultation_count ?? 0}회</strong></article>
          <article><span>최근 상담 날짜</span><strong>{formatDate(usage?.last_consultation_at)}</strong></article>
        </div>
      </section>

      <section className="mypage-section">
        <h2>환경 설정</h2>
        <ModelPreference />
      </section>

      <section className="mypage-section account-actions">
        <h2>계정 작업</h2>
        <button className="logout-button" onClick={handleLogout}>로그아웃</button>
        <button className="consultation-delete-button" onClick={() => setIsConsultationDeleteOpen(true)}>모든 상담 데이터 삭제</button>
        <button className="delete-account-button" onClick={() => setIsDeleteModalOpen(true)}>회원 탈퇴</button>
      </section>
      {isPasswordModalOpen && <PasswordChangeModal onClose={() => setIsPasswordModalOpen(false)} />}
      {isDeleteModalOpen && <AccountDeleteModal onClose={() => setIsDeleteModalOpen(false)} />}
      {isConsultationDeleteOpen && <ConsultationDeleteModal
        onClose={() => setIsConsultationDeleteOpen(false)}
        onDeleted={() => setUsage({ consultation_count: 0, last_consultation_at: null })}
      />}
    </section>
  );
}
