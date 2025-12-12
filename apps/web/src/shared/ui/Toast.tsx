// apps/web/src/shared/ui/Toast.tsx
import React, {
  useEffect,
  useState,
  createContext,
  useContext,
  useCallback,
  useRef,
} from 'react';
import { createPortal } from 'react-dom';
import styles from './Toast.module.css';

export interface ToastProps {
  message: string;
  type: 'success' | 'error' | 'info' | 'warning';
  duration?: number; // ms, 0 means sticky
  onClose?: () => void;
}

export function Toast({ message, type, duration = 6000, onClose }: ToastProps) {
  const [visible, setVisible] = useState(true);
  const [isExiting, setIsExiting] = useState(false);
  const cleanupTimerRef = useRef<NodeJS.Timeout | null>(null);
  const dismissTimerRef = useRef<NodeJS.Timeout | null>(null);
  const hoveredRef = useRef(false);

  useEffect(() => {
    if (!visible) return;
    if (!duration || duration <= 0) return; // sticky

    const scheduleDismiss = () => {
      dismissTimerRef.current = setTimeout(() => {
        if (hoveredRef.current) return; // pause while hovered
        setIsExiting(true);
        cleanupTimerRef.current = setTimeout(() => {
          setVisible(false);
          onClose?.();
        }, 300);
      }, duration);
    };

    scheduleDismiss();

    return () => {
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
      if (cleanupTimerRef.current) clearTimeout(cleanupTimerRef.current);
    };
  }, [duration, onClose, visible]);

  const getTypeClass = () => {
    return styles[type] || styles.info;
  };

  const getIcon = () => {
    switch (type) {
      case 'success':
        return (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        );
      case 'error':
        return (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
        );
      case 'warning':
        return (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        );
      case 'info':
        return (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        );
      default:
        return null;
    }
  };

  if (!visible) return null;

  const toastClasses = [
    styles.toast,
    getTypeClass(),
    isExiting ? styles.exiting : styles.visible,
  ].join(' ');

  return (
    <div
      className={toastClasses}
      onMouseEnter={() => {
        hoveredRef.current = true;
        if (dismissTimerRef.current) {
          clearTimeout(dismissTimerRef.current);
          dismissTimerRef.current = null;
        }
      }}
      onMouseLeave={() => {
        hoveredRef.current = false;
        if (duration && duration > 0 && !isExiting) {
          // reschedule full duration on leave; simple and UX-friendly
          if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
          dismissTimerRef.current = setTimeout(() => {
            setIsExiting(true);
            cleanupTimerRef.current = setTimeout(() => {
              setVisible(false);
              onClose?.();
            }, 300);
          }, duration);
        }
      }}
    >
      <div className={styles.content}>
        <span className={styles.icon}>{getIcon()}</span>
        <div className={styles.message}>{message}</div>
        <button
          onClick={() => {
            setIsExiting(true);
            setTimeout(() => {
              setVisible(false);
              onClose?.();
            }, 300);
          }}
          className={styles.closeButton}
          aria-label="Close"
        >
          ×
        </button>
      </div>
    </div>
  );
}

export interface ToastContainerProps {
  toasts: Array<ToastProps & { id: string }>;
  onRemoveToast: (id: string) => void;
}

export function ToastContainer({ toasts, onRemoveToast }: ToastContainerProps) {
  if (toasts.length === 0) return null;
  const node = (
    <div className={styles.toastContainer}>
      {toasts.map(toast => (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          duration={toast.duration}
          onClose={() => onRemoveToast(toast.id)}
        />
      ))}
    </div>
  );
  return createPortal(node, document.body);
}

// ToastProvider context
type ToastType = 'success' | 'error' | 'info' | 'warning';
type ShowToastOptions = { duration?: number; sticky?: boolean };
interface ToastContextType {
  showToast: (
    message: string,
    type: ToastType,
    optionsOrDuration?: number | ShowToastOptions
  ) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Array<ToastProps & { id: string }>>([]);

  const showToast = useCallback(
    (
      message: string,
      type: ToastType,
      optionsOrDuration: number | ShowToastOptions = 6000
    ) => {
      const id = Math.random().toString(36).substr(2, 9);
      let duration: number | undefined = 6000;
      let sticky = false;
      if (typeof optionsOrDuration === 'number') {
        duration = optionsOrDuration;
      } else if (optionsOrDuration && typeof optionsOrDuration === 'object') {
        duration = optionsOrDuration.duration ?? 6000;
        sticky = !!optionsOrDuration.sticky;
      }
      setToasts(prev => [
        ...prev,
        { id, message, type, duration: sticky ? 0 : duration },
      ]);
    },
    []
  );

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(toast => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <ToastContainer toasts={toasts} onRemoveToast={removeToast} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

// Convenience hooks for specific toast types
export function useErrorToast() {
  const { showToast } = useToast();
  return (message: string, duration?: number) =>
    showToast(message, 'error', duration);
}

export function useSuccessToast() {
  const { showToast } = useToast();
  return (message: string, duration?: number) =>
    showToast(message, 'success', duration);
}

export function useInfoToast() {
  const { showToast } = useToast();
  return (message: string, duration?: number) =>
    showToast(message, 'info', duration);
}

export function useWarningToast() {
  const { showToast } = useToast();
  return (message: string, duration?: number) =>
    showToast(message, 'warning', duration);
}
