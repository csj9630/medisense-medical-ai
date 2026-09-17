import { useRef, useState, type ChangeEvent } from 'react';
import { Camera, UserRound } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { uploadProfileImage } from './profileImageApi';
import './profileImageUploader.css';

export function ProfileImageUploader() {
  const { user, updateUser } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  const selectImage = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setError(''); setIsUploading(true);
    try {
      updateUser(await uploadProfileImage(file));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '업로드에 실패했습니다.');
    } finally {
      setIsUploading(false);
      event.target.value = '';
    }
  };

  return <div className="profile-image-control">
    <button type="button" className="profile-image-button" onClick={() => inputRef.current?.click()} disabled={isUploading} aria-label="프로필 이미지 변경">
      {user?.profile_image_url ? <img src={user.profile_image_url} alt="프로필" /> : <UserRound size={30} />}
      <span className="profile-camera"><Camera size={13} /></span>
    </button>
    <input ref={inputRef} className="profile-file-input" type="file" accept="image/jpeg,image/png,image/webp" onChange={selectImage} />
    {isUploading && <span className="profile-upload-message">업로드 중...</span>}
    {error && <span className="profile-upload-error">{error}</span>}
  </div>;
}
