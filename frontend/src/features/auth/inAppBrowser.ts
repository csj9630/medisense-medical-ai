// 카카오톡/네이버/인스타그램 등 인앱 브라우저는 구글이 보안 정책상 OAuth 로그인
// 자체를 차단한다("This browser or app may not be secure", disallowed_useragent) -
// 우리 코드로 고칠 수 없는 구글 서버 쪽 정책이라, 대신 감지해서 외부 브라우저로
// 열도록 안내한다(OAuthButtons.tsx 참고).
const IN_APP_BROWSER_PATTERNS = [
  { name: 'KAKAOTALK', label: '카카오톡' },
  { name: 'NAVER', label: '네이버' },
  { name: 'Instagram', label: '인스타그램' },
  { name: 'FBAN', label: '페이스북' }, // Facebook 앱 iOS
  { name: 'FBAV', label: '페이스북' }, // Facebook 앱 Android
  { name: 'Line', label: '라인' },
];

export function detectInAppBrowser(): string | null {
  const ua = navigator.userAgent;
  const match = IN_APP_BROWSER_PATTERNS.find((p) => ua.includes(p.name));
  return match?.label ?? null;
}

// 카카오톡은 이 스킴으로 링크를 열면 인앱 브라우저 대신 시스템 기본 브라우저로
// 강제 이동시켜준다(카카오 공식 문서에 있는 방식). 다른 인앱 브라우저는 이런
// 스킴이 없는 경우가 많아서, 그런 경우엔 사용자가 우측 상단 메뉴에서 직접
// "다른 브라우저로 열기"를 선택하도록 안내 문구만 보여준다.
export function openInExternalBrowser(url: string): void {
  window.location.href = `kakaotalk://web/openExternal?url=${encodeURIComponent(url)}`;
}
