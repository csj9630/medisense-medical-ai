import { createBrowserRouter, redirectDocument } from "react-router-dom";
import { API_URL } from "../services/apiClient";
import { PROVIDER_CALLBACK_PATHS, providerCallbackUrl } from "../features/auth/oauth-callback/providerRedirect";
import { MainLayout } from "../components/Layout/MainLayout";
import { LoginPage } from "../features/auth/login";
import { OAuthCallbackPage } from "../features/auth/oauth-callback";
import { SignupPage } from "../features/auth/signup";
import { VerifyEmailPage } from "../features/auth/verify";
import { ForgotPasswordPage } from "../features/auth/password-reset/ForgotPasswordPage";
import { ResetPasswordPage } from "../features/auth/password-reset/ResetPasswordPage";
import { RequireAuth } from "../features/auth/RequireAuth";
import { RequireAdmin } from "../features/auth/RequireAdmin";
import { AdminPage } from "../features/admin";
import { DashboardPage } from "../features/dashboard";
import { ConsultationPage } from "../features/consultation";
import { ChatPage } from "../features/chat";
import { DocumentPage } from "../features/document";
import { EvaluationPage } from "../features/evaluation";
import { OcrPage } from "../features/ocr";
import { SearchPage } from "../features/search";
import { MyPage } from "../features/my";

export const router = createBrowserRouter([
  ...PROVIDER_CALLBACK_PATHS.map((path) => ({
    path,
    loader: ({ request }: { request: Request }) =>
      redirectDocument(providerCallbackUrl(request.url, API_URL)),
  })),
  {
    // 모든 화면을 하나의 사이드바 레이아웃 안에서 보여줍니다.
    element: <MainLayout />,
    children: [
      { path: "/", element: <ConsultationPage /> },
      { path: "/chat/:conversationId", element: <ChatPage /> },
      { path: "/login", element: <LoginPage /> },
      { path: "/signup", element: <SignupPage /> },
      { path: "/oauth-callback", element: <OAuthCallbackPage /> },
      { path: "/verify-email", element: <VerifyEmailPage /> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },
      { path: "/document", element: <DocumentPage /> },
      { path: "/ocr", element: <OcrPage /> },
      { path: "/search", element: <SearchPage /> },
      { path: "/evaluation", element: <EvaluationPage /> },
      {
        // 관리자(is_admin) 계정만 접근할 수 있습니다.
        element: <RequireAdmin />,
        children: [
          { path: "/admin", element: <AdminPage /> },
          { path: "/dashboard", element: <DashboardPage /> },
        ],
      },
      {
        // 로그인한 사용자만 사이드바 마이페이지에 접근할 수 있습니다.
        element: <RequireAuth />,
        children: [
          { path: "/mypage", element: <MyPage /> },
          { path: "/my", element: <MyPage /> },
        ],
      },
    ],
  },
]);
