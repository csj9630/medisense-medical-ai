import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  SquarePen,
  User,
  LogOut,
  X,
} from 'lucide-react';
import { useSidebar } from './SidebarContext';
import { useAuth } from '../../features/auth/AuthContext';
import { getGuestDisplayName } from '../../features/auth/guestSession';
import { HistoryItem } from './HistoryItem';
import {
  getConversations,
  renameConversation,
  deleteConversation,
  searchConversations,
} from '../../api/conversations';
import { onConversationsChanged } from '../../api/conversationsEvents';
import type { Conversation } from '../../api/types';

type FilterMode = 'all' | 'category';

// 키 입력마다 바로 검색 API를 부르면 낭비라 이만큼 멈춘 뒤에만 요청한다.
const SEARCH_DEBOUNCE_MS = 300;

export function Sidebar() {
  const { collapsed, toggle } = useSidebar();
  const { user, isLoading, logout } = useAuth();
  const isLoggedIn = Boolean(user);
  const navigate = useNavigate();
  const { conversationId } = useParams();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [filter, setFilter] = useState<FilterMode>('all');
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  // 검색: 제목·카테고리(진료과)·대화 내용을 한 번에 검색한다(모드 선택 없음).
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Conversation[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isSearchActive = searchQuery.trim().length > 0;

  useEffect(() => {
    function refresh() {
      getConversations()
        .then(setConversations)
        .catch((error) => {
          // 여기서 실패해도 사이드바 자체가 죽으면 안 되니 목록을 비워둔 채로 넘어간다.
          console.error('대화 목록을 불러오지 못했습니다.', error);
          setConversations([]);
        });
    }

    // conversationId가 바뀔 때마다 다시 불러온다 — 메인 화면에서 새 대화를 만들어
    // 이동해온 경우처럼, 사이드바 바깥에서 목록이 바뀐 경우를 반영하기 위함.
    refresh();
    // 첫 메시지로 제목이 자동으로 바뀌는 경우처럼, conversationId는 안 바뀌어도
    // 목록이 갱신돼야 하는 경우를 위한 별도 알림 채널 (ChatPage 참고).
    return onConversationsChanged(refresh);
    // isLoggedIn도 의존성에 넣는다 — Sidebar는 라우트 전체를 감싸는 MainLayout 안에
    // 있어서 로그인해도(같은 SPA 세션 안에서 /login → / 로 navigate) 언마운트되지
    // 않는다. conversationId만 보고 있으면 로그인 직후 여전히 로그인 전(게스트/빈)
    // 목록이 그대로 남아 "카테고리(대화 내역)가 로드 안 된 것"처럼 보인다.
  }, [conversationId, isLoggedIn]);

  function runSearch(query: string) {
    setIsSearching(true);
    searchConversations(query)
      .then(setSearchResults)
      .catch((error) => {
        console.error('대화 검색에 실패했습니다.', error);
        setSearchResults([]);
      })
      .finally(() => setIsSearching(false));
  }

  // 검색어가 바뀔 때마다 SEARCH_DEBOUNCE_MS만큼 기다렸다가 검색 API를 부른다.
  // 빈 검색어면 아예 요청하지 않고 검색 결과를 비워서 평소 목록(전체/진료과별)으로 돌아간다.
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);

    if (!isSearchActive) {
      setSearchResults(null);
      setIsSearching(false);
      return;
    }

    searchDebounceRef.current = setTimeout(() => runSearch(searchQuery.trim()), SEARCH_DEBOUNCE_MS);

    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  // 검색 버튼 클릭(또는 입력창에서 Enter) 시 디바운스를 기다리지 않고 바로 검색한다.
  function handleSearchSubmit(event: FormEvent) {
    event.preventDefault();
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    if (isSearchActive) runSearch(searchQuery.trim());
  }

  async function handleRename(id: string, title: string) {
    const patch = (c: Conversation) => (c.id === id ? { ...c, title, isTitleCustom: true } : c);
    setConversations((current) => current.map(patch));
    setSearchResults((current) => (current ? current.map(patch) : current));
    await renameConversation(id, title);
  }

  async function handleDelete(id: string) {
    setConversations((current) => current.filter((c) => c.id !== id));
    setSearchResults((current) => (current ? current.filter((c) => c.id !== id) : current));
    await deleteConversation(id);
    if (conversationId === id) navigate('/');
  }

  function toggleCategory(label: string) {
    setCollapsedCategories((current) => {
      const next = new Set(current);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }

  function goToProfile() {
    if (isLoading) return;
    // 비로그인 사용자가 로그인 버튼을 누른 경우에만 사이드바를 접습니다.
    if (!isLoggedIn && !collapsed) toggle();
    navigate(isLoggedIn ? '/mypage' : '/login');
  }

  function handleLogout() {
    logout();
    navigate('/');
  }

  if (collapsed) {
    return (
      <aside className="flex h-full w-14 shrink-0 flex-col items-center gap-3 border-r border-neutral-200 bg-neutral-50 py-3 dark:border-neutral-800 dark:bg-neutral-900">
        <button
          type="button"
          title="사이드바 펼치기"
          aria-label="사이드바 펼치기"
          onClick={toggle}
          className="rounded-lg p-2 text-neutral-500 hover:bg-neutral-200 dark:text-neutral-400 dark:hover:bg-neutral-800"
        >
          <PanelLeftOpen size={18} />
        </button>
        <button
          type="button"
          title="메인으로 이동"
          aria-label="메인으로 이동"
          onClick={() => navigate('/')}
          className="rounded-lg p-0.5 hover:bg-neutral-200 dark:hover:bg-neutral-800"
        >
          <img src="/logo-mark.png" alt="MediSense" className="h-5 w-5" />
        </button>
        <button
          type="button"
          title="새 채팅"
          aria-label="새 채팅"
          onClick={() => navigate('/')}
          className="rounded-lg p-2 text-neutral-500 hover:bg-neutral-200 dark:text-neutral-400 dark:hover:bg-neutral-800"
        >
          <SquarePen size={18} />
        </button>
        <div className="mt-auto">
          <button
            type="button"
            title={isLoggedIn ? '마이페이지' : '로그인'}
            aria-label={isLoggedIn ? '마이페이지' : '로그인'}
            disabled={isLoading}
            onClick={goToProfile}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-neutral-200 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400"
          >
            {user?.profile_image_url
              ? <img src={user.profile_image_url} alt="" className="h-full w-full rounded-full object-cover" />
              : <User size={16} />}
          </button>
        </div>
      </aside>
    );
  }

  const grouped = isSearchActive
    ? [{ label: null, items: searchResults ?? [] }]
    : filter === 'category'
      ? groupByCategory(conversations)
      : [{ label: null, items: conversations }];

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex items-center justify-between px-4 py-4">
        <button
          type="button"
          title="메인으로 이동"
          aria-label="메인으로 이동"
          onClick={() => navigate('/')}
          className="flex items-center gap-1.5 rounded-lg py-0.5 pl-0.5 pr-1.5 hover:bg-neutral-200 dark:hover:bg-neutral-800"
        >
          <img src="/logo-mark.png" alt="MediSense" className="h-5 w-5" />
          <span className="font-semibold text-neutral-800 dark:text-neutral-100">MediSense</span>
        </button>
        <button
          type="button"
          title="사이드바 접기"
          aria-label="사이드바 접기"
          onClick={toggle}
          className="rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-200 hover:text-neutral-600 dark:text-neutral-500 dark:hover:bg-neutral-800 dark:hover:text-neutral-300"
        >
          <PanelLeftClose size={18} />
        </button>
      </div>

      <div className="px-4 pb-2.5">
        <form className="relative" onSubmit={handleSearchSubmit}>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="제목·진료과·내용 검색"
            aria-label="대화 검색"
            className="w-full rounded-lg border border-neutral-200 bg-white py-1.5 pl-3 pr-14 text-xs text-neutral-700 placeholder:text-neutral-400 focus:border-neutral-400 focus:outline-none dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-100"
          />
          {searchQuery && (
            <button
              type="button"
              title="검색어 지우기"
              aria-label="검색어 지우기"
              onClick={() => setSearchQuery('')}
              className="absolute right-8 top-1/2 -translate-y-1/2 rounded p-0.5 text-neutral-400 hover:bg-neutral-200 hover:text-neutral-600 dark:hover:bg-neutral-700"
            >
              <X size={13} />
            </button>
          )}
          <button
            type="submit"
            title="검색"
            aria-label="검색"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-neutral-400 hover:bg-neutral-200 hover:text-neutral-600 dark:hover:bg-neutral-700"
          >
            <Search size={14} />
          </button>
        </form>
      </div>

      <div className="flex items-center justify-between px-4 pb-3">
        {isSearchActive ? (
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            {isSearching ? '검색 중...' : `검색 결과 ${searchResults?.length ?? 0}건`}
          </p>
        ) : (
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setFilter('all')}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                filter === 'all'
                  ? 'bg-white text-neutral-800 shadow-sm dark:bg-neutral-700 dark:text-neutral-50'
                  : 'text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              전체
            </button>
            <button
              type="button"
              onClick={() => setFilter('category')}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                filter === 'category'
                  ? 'bg-white text-neutral-800 shadow-sm dark:bg-neutral-700 dark:text-neutral-50'
                  : 'text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200'
              }`}
            >
              진료과별
            </button>
          </div>
        )}
        <button
          type="button"
          title="새 채팅"
          aria-label="새 채팅"
          onClick={() => navigate('/')}
          className="rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-200 hover:text-neutral-600 dark:text-neutral-500 dark:hover:bg-neutral-800 dark:hover:text-neutral-300"
        >
          <SquarePen size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {!isLoggedIn && conversations.length === 0 ? (
          // 게스트는 대화 기록이 로그인한 사용자처럼 계속 보관된다는 보장이 없다 —
          // 첫 대화를 시작하기 전에 로그인을 유도한다.
          <div className="flex h-full flex-col items-center justify-center gap-3 px-4 text-center">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              로그인하면 상담 기록을 계속 보관하고
              <br />
              이어서 확인할 수 있어요.
            </p>
            <button
              type="button"
              onClick={goToProfile}
              className="rounded-lg bg-neutral-800 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            >
              로그인하기
            </button>
          </div>
        ) : grouped.map((group) => {
          const isCollapsed = group.label ? collapsedCategories.has(group.label) : false;
          return (
            <div key={group.label ?? 'all'} className="mb-2">
              {group.label && (
                <button
                  type="button"
                  onClick={() => toggleCategory(group.label!)}
                  className="flex w-full items-center gap-1 px-2 pb-1 pt-2 text-xs font-medium text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                >
                  {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                  {group.label}
                  <span className="text-neutral-300 dark:text-neutral-600">({group.items.length})</span>
                </button>
              )}
              {!isCollapsed && (
                <div className="flex flex-col gap-0.5">
                  {group.items.map((conversation) => (
                    <HistoryItem
                      key={conversation.id}
                      conversation={conversation}
                      active={conversation.id === conversationId}
                      onSelect={() => navigate(`/chat/${conversation.id}`)}
                      onRename={(title) => handleRename(conversation.id, title)}
                      onDelete={() => handleDelete(conversation.id)}
                    />
                  ))}
                  {group.items.length === 0 && !isSearching && (
                    <p className="px-2 py-1 text-xs text-neutral-400 dark:text-neutral-600">
                      {isSearchActive ? '검색 결과가 없습니다.' : '대화 내역이 없습니다.'}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex items-center border-t border-neutral-200 dark:border-neutral-800">
        <button
          type="button"
          title={isLoggedIn ? '마이페이지로 이동' : '로그인하러 가기'}
          onClick={goToProfile}
          disabled={isLoading}
          className="flex min-w-0 flex-1 items-center gap-2 px-4 py-3 text-left hover:bg-neutral-100 dark:hover:bg-neutral-800"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-neutral-200 text-neutral-500 dark:bg-neutral-700 dark:text-neutral-300">
            {user?.profile_image_url
              ? <img src={user.profile_image_url} alt="" className="h-full w-full rounded-full object-cover" />
              : <User size={16} />}
          </span>
          <span className="min-w-0 truncate text-sm text-neutral-700 dark:text-neutral-200">
            {isLoading
              ? '로그인 확인 중...'
              : user
                ? user.email
                // 게스트라도 대화가 생기기 전(=아직 채팅을 시작 안 함)에는 로그인
                // 유도 문구를 그대로 보여주고, 대화가 인식되면 게스트 식별 표시로 바꾼다.
                : conversations.length > 0
                  ? getGuestDisplayName()
                  : '로그인 / 회원가입'}
          </span>
        </button>
        {user && (
          <button
            type="button"
            title="로그아웃"
            aria-label="로그아웃"
            onClick={handleLogout}
            className="mr-3 rounded-lg p-2 text-neutral-400 hover:bg-neutral-200 hover:text-red-500 dark:text-neutral-500 dark:hover:bg-neutral-800 dark:hover:text-red-400"
          >
            <LogOut size={17} />
          </button>
        )}
      </div>
    </aside>
  );
}

function groupByCategory(conversations: Conversation[]) {
  const categories = new Map<string, Conversation[]>();
  for (const conversation of conversations) {
    const key = conversation.category ?? '기타';
    if (!categories.has(key)) categories.set(key, []);
    categories.get(key)!.push(conversation);
  }
  return Array.from(categories.entries()).map(([label, items]) => ({ label, items }));
}
