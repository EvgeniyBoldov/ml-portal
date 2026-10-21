import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { ChatTimelineMessage } from '../types';

export function useChatScroll(
  chatId: string | undefined,
  messages: ChatTimelineMessage[]
) {
  const historyRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);
  const [hasUnread, setHasUnread] = useState(false);

  const scrollToBottom = useCallback(() => {
    followRef.current = true;
    const container = historyRef.current;
    if (container) container.scrollTop = container.scrollHeight;
    setHasUnread(false);
  }, []);

  useLayoutEffect(() => {
    scrollToBottom();
  }, [chatId, scrollToBottom]);

  const followContent = useCallback(() => {
    if (followRef.current) scrollToBottom();
    else setHasUnread(true);
  }, [scrollToBottom]);

  useLayoutEffect(() => {
    followContent();
  }, [messages, followContent]);

  useLayoutEffect(() => {
    const container = historyRef.current;
    if (!container) return;
    const onScroll = () => {
      followRef.current =
        container.scrollHeight - container.scrollTop - container.clientHeight <=
        80;
      if (followRef.current) setHasUnread(false);
    };
    container.addEventListener('scroll', onScroll);
    // Images, expanded sources and progress can also change the transcript
    // height without changing its messages.
    const observer =
      typeof window.ResizeObserver === 'undefined'
        ? null
        : new window.ResizeObserver(followContent);
    if (contentRef.current) observer?.observe(contentRef.current);
    return () => {
      container.removeEventListener('scroll', onScroll);
      observer?.disconnect();
    };
  }, [chatId, followContent]);

  return { historyRef, contentRef, hasUnread, scrollToBottom };
}
