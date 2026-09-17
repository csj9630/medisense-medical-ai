// 다른 화면에서 사이드바를 재사용할 때는 이 파일에서만 import하면 된다.
//
//   import { Sidebar, SidebarProvider } from '@/components/Sidebar';
//
//   function SomeLayout() {
//     return (
//       <SidebarProvider>          // collapsed 상태를 Sidebar와 공유하려면 반드시 감싸야 함
//         <div className="flex h-screen">
//           <Sidebar />
//           <main>...</main>
//         </div>
//       </SidebarProvider>
//     );
//   }
//
// 사이드바 접힘 여부를 다른 컴포넌트(예: 상단바)에서도 알아야 한다면 useSidebar() 훅을 쓰면 된다.
export { Sidebar } from './Sidebar';
export { SidebarProvider, useSidebar } from './SidebarContext';
