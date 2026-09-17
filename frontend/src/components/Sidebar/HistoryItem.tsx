import { useEffect, useRef, useState } from 'react';
import { MoreVertical, Pencil, Trash2 } from 'lucide-react';
import type { Conversation } from '../../api/types';
import { formatRelativeDate } from '../../utils/formatDate';

type HistoryItemProps = {
  conversation: Conversation;
  active: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
};

export function HistoryItem({ conversation, active, onSelect, onRename, onDelete }: HistoryItemProps) {
  const [editing, setEditing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [draftTitle, setDraftTitle] = useState(conversation.title);
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpen]);

  function startEditing() {
    setDraftTitle(conversation.title);
    setEditing(true);
    setMenuOpen(false);
  }

  function commit() {
    const trimmed = draftTitle.trim();
    setEditing(false);
    if (trimmed && trimmed !== conversation.title) onRename(trimmed);
  }

  function cancel() {
    setDraftTitle(conversation.title);
    setEditing(false);
  }

  function handleDelete() {
    setMenuOpen(false);
    if (window.confirm(`'${conversation.title}' 대화를 삭제할까요?`)) onDelete();
  }

  return (
    <div
      className={`group relative flex flex-col rounded-lg px-3 py-2 cursor-pointer ${
        active ? 'bg-blue-50 dark:bg-blue-950' : 'hover:bg-neutral-100 dark:hover:bg-neutral-800'
      }`}
      onClick={editing ? undefined : onSelect}
    >
      {editing ? (
        <input
          ref={inputRef}
          value={draftTitle}
          onChange={(e) => setDraftTitle(e.target.value)}
          onClick={(e) => e.stopPropagation()}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') cancel();
          }}
          className="w-full rounded border border-blue-300 bg-white px-1.5 py-0.5 text-sm outline-none dark:border-blue-700 dark:bg-neutral-900 dark:text-neutral-100"
          autoFocus
        />
      ) : (
        <div className="flex items-center justify-between gap-1">
          <div className="flex min-w-0 items-baseline gap-1.5">
            <span className="truncate text-sm font-medium text-neutral-800 dark:text-neutral-100">
              {conversation.title}
            </span>
            <span className="shrink-0 text-[11px] text-neutral-400 dark:text-neutral-500">
              {formatRelativeDate(conversation.updatedAt)}
            </span>
          </div>
          <div ref={menuRef} className="relative shrink-0">
            <button
              type="button"
              title="더보기"
              aria-label="더보기"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((open) => !open);
              }}
              className={`rounded p-1 text-neutral-400 hover:bg-neutral-200 hover:text-neutral-700 dark:hover:bg-neutral-700 dark:hover:text-neutral-200 ${
                menuOpen ? 'flex' : 'hidden group-hover:flex'
              }`}
            >
              <MoreVertical size={14} />
            </button>

            {menuOpen && (
              <div
                role="menu"
                onClick={(e) => e.stopPropagation()}
                className="absolute right-0 top-full z-10 mt-1 w-36 overflow-hidden rounded-lg border border-neutral-200 bg-white py-1 shadow-lg dark:border-neutral-700 dark:bg-neutral-800"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={startEditing}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-700"
                >
                  <Pencil size={13} /> 이름 변경
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={handleDelete}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-red-500 hover:bg-neutral-100 dark:hover:bg-neutral-700"
                >
                  <Trash2 size={13} /> 삭제
                </button>
              </div>
            )}
          </div>
        </div>
      )}
      {conversation.category && !editing && (
        <span className="text-xs text-neutral-400 dark:text-neutral-500">{conversation.category}</span>
      )}
    </div>
  );
}
