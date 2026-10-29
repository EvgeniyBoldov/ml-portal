import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import styles from './ChatSidebar.module.css';
import Button from '@shared/ui/Button';
import { useNavigate, useParams } from 'react-router-dom';
import Modal from '@shared/ui/Modal';
import Input from '@shared/ui/Input';
import Popover from '@shared/ui/Popover';
import {
  useChats,
  useCreateChat,
  useDeleteChat,
  useRenameChat,
  useUpdateChatTags,
} from '@shared/api/hooks/useChats';
import { useToast } from '@shared/ui/Toast';
import { ChatTags } from '@domains/chat/components';
import { useChatStatuses } from '@shared/api/hooks/useChatStatuses';
import { useChatNotificationsStore } from '@domains/chat/model/chatNotifications.store';

function KebabIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24">
      <circle cx="12" cy="5" r="2" />
      <circle cx="12" cy="12" r="2" />
      <circle cx="12" cy="19" r="2" />
    </svg>
  );
}

export default function ChatSidebar() {
  const { chatId } = useParams();
  const nav = useNavigate();
  const { showToast } = useToast();

  // Server state
  const { data } = useChats();
  const createChatMutation = useCreateChat();
  const deleteChatMutation = useDeleteChat();
  const renameChatMutation = useRenameChat();
  const updateTagsMutation = useUpdateChatTags();

  // UI state
  const [renameTarget, setRenameTarget] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string;
    name?: string;
  } | null>(null);
  const [editTagsTarget, setEditTagsTarget] = useState<{
    id: string;
    tags: string[];
  } | null>(null);

  const chats = data?.items || [];
  const statuses = useChatStatuses().data || [];
  const unreadChatIds = useChatNotificationsStore(state => state.unreadChatIds);
  const setActiveChat = useChatNotificationsStore(state => state.setActiveChat);
  useLayoutEffect(() => {
    setActiveChat(chatId || null);
    return () => setActiveChat(null);
  }, [chatId, setActiveChat]);
  const statusByChatId = new Map(
    statuses.map(status => [status.chat_id, status.status])
  );
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [menuSide, setMenuSide] = useState<'top' | 'bottom'>('bottom');
  const menuTriggerRef = useRef<HTMLElement | null>(null);
  const isDialogOpen = !!(renameTarget || deleteTarget || editTagsTarget);

  useEffect(() => {
    if (!isDialogOpen) return;
    // The shared Modal owns keyboard focus; its opener may be a menu item
    // removed before mount, so restore the persistent chat action trigger here.
    return () => menuTriggerRef.current?.focus();
  }, [isDialogOpen]);

  function closeMenu() {
    setOpenMenuId(null);
  }

  async function onCreate() {
    try {
      const result = await createChatMutation.mutateAsync({
        name: 'Новый чат',
      });
      nav(`/gpt/chat/${result.chat_id}`);
    } catch {
      showToast('Ошибка создания чата', 'error');
    }
  }

  return (
    <aside className={styles.sidebar}>
      <div className={styles.head}>
        <div className={styles.title}>Чаты</div>
        <Button size="sm" onClick={onCreate}>
          + Новый
        </Button>
      </div>

      <div className={styles.list}>
        {chats.length === 0 && (
          <div className={styles.item} style={{ opacity: 0.7 }}>
            Нет чатов
          </div>
        )}
        {chats.map(
          chat =>
            chat && (
              <div
                key={chat.id}
                className={[
                  styles.row,
                  chatId === chat.id ? styles.active : '',
                ].join(' ')}
              >
                <button
                  className={styles.item}
                  onClick={() => nav(`/gpt/chat/${chat.id}`)}
                >
                  <div
                    className={styles.name}
                    title={chat.name || 'Без названия'}
                  >
                    {chat.name || 'Без названия'}
                  </div>
                  {Array.isArray(chat.tags) && chat.tags.length > 0 && (
                    <div className={styles.tags}>
                      {chat.tags.map(tag => (
                        <span key={tag} className={styles.tag} title={tag}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
                {(() => {
                  const isRunning = statusByChatId.get(chat.id) === 'running';
                  const hasUnread =
                    chatId !== chat.id && !!unreadChatIds[chat.id];
                  if (!isRunning && !hasUnread)
                    return (
                      <span className={styles.statusSlot} aria-hidden="true" />
                    );
                  const label = [
                    isRunning ? 'Ответ формируется' : '',
                    hasUnread ? 'Новый ответ' : '',
                  ]
                    .filter(Boolean)
                    .join('. ');
                  return (
                    <span
                      className={styles.statusSlot}
                      role="img"
                      aria-label={label}
                      title={label}
                    >
                      {isRunning && (
                        <span className={styles.spinner} aria-hidden="true" />
                      )}
                      {hasUnread && (
                        <span className={styles.unreadDot} aria-hidden="true" />
                      )}
                    </span>
                  );
                })()}
                <Popover
                  open={openMenuId === chat.id}
                  ariaLabel={`Действия чата «${chat.name || 'Без названия'}»`}
                  onOpenChange={isOpen => {
                    if (isOpen) {
                      menuTriggerRef.current =
                        document
                          .getElementById(`chat-menu-${chat.id}`)
                          ?.querySelector<HTMLElement>('[role="button"]') ||
                        null;
                      const bottom =
                        menuTriggerRef.current?.getBoundingClientRect()
                          .bottom || 0;
                      setMenuSide(
                        bottom + 160 > window.innerHeight ? 'top' : 'bottom'
                      );
                    } else if (
                      document.activeElement?.closest('[role="menu"]')
                    ) {
                      menuTriggerRef.current?.focus();
                    }
                    setOpenMenuId(isOpen ? chat.id : null);
                  }}
                  id={`chat-menu-${chat.id}`}
                  trigger={
                    <span className={styles.kebabBtn} aria-hidden="true">
                      <KebabIcon />
                    </span>
                  }
                  content={
                    <div className={styles.menu}>
                      <button
                        className={styles.item}
                        role="menuitem"
                        onClick={() => {
                          closeMenu();
                          setRenameTarget({
                            id: chat.id,
                            name: chat.name || '',
                          });
                        }}
                      >
                        Переименовать
                      </button>
                      <button
                        className={styles.item}
                        role="menuitem"
                        onClick={() => {
                          closeMenu();
                          setEditTagsTarget({
                            id: chat.id,
                            tags: chat.tags || [],
                          });
                        }}
                      >
                        Изменить теги
                      </button>
                      <button
                        className={`${styles.item} ${styles.danger}`}
                        role="menuitem"
                        onClick={() => {
                          closeMenu();
                          setDeleteTarget({
                            id: chat.id,
                            name: chat.name || '',
                          });
                        }}
                      >
                        Удалить
                      </button>
                    </div>
                  }
                  align="end"
                  side={menuSide}
                />
              </div>
            )
        )}
      </div>

      <Modal
        open={!!renameTarget}
        onClose={() => setRenameTarget(null)}
        title="Переименовать чат"
        footer={
          <>
            <Button variant="ghost" onClick={() => setRenameTarget(null)}>
              Отмена
            </Button>
            <Button
              onClick={async () => {
                if (!renameTarget) return;
                try {
                  await renameChatMutation.mutateAsync({
                    chatId: renameTarget.id,
                    name: renameTarget.name || 'Без названия',
                  });
                  setRenameTarget(null);
                  showToast('Чат переименован', 'success');
                } catch {
                  showToast('Ошибка переименования', 'error');
                }
              }}
            >
              Сохранить
            </Button>
          </>
        }
      >
        <label className={styles.fieldLabel} htmlFor="chat-name">
          Название чата
        </label>
        <Input
          id="chat-name"
          value={renameTarget?.name || ''}
          onChange={e =>
            setRenameTarget(v => (v ? { ...v, name: e.target.value } : v))
          }
          className="w-100"
        />
      </Modal>

      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Удалить чат"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              Отмена
            </Button>
            <Button
              variant="danger"
              onClick={async () => {
                if (!deleteTarget) return;
                try {
                  await deleteChatMutation.mutateAsync(deleteTarget.id);
                  if (chatId === deleteTarget.id) nav('/gpt/chat');
                  setDeleteTarget(null);
                  showToast('Чат удалён', 'success');
                } catch {
                  showToast('Ошибка удаления', 'error');
                }
              }}
            >
              Удалить
            </Button>
          </>
        }
      >
        Вы уверены, что хотите удалить чат «
        {deleteTarget?.name || 'Без названия'}»?
      </Modal>

      {editTagsTarget && (
        <ChatTags
          chatId={editTagsTarget.id}
          tags={editTagsTarget.tags}
          onClose={() => setEditTagsTarget(null)}
          onTagsChange={async tags => {
            try {
              await updateTagsMutation.mutateAsync({
                chatId: editTagsTarget.id,
                tags,
              });
              setEditTagsTarget(null);
              showToast('Теги обновлены', 'success');
            } catch (error) {
              showToast('Ошибка обновления тегов', 'error');
              throw error;
            }
          }}
        />
      )}
    </aside>
  );
}
