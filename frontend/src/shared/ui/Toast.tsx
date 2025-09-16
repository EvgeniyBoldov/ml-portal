import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import styles from './Toast.module.css';

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title?: string;
  message: string;
  duration?: number;
  actions?: Array<{
    label: string;
    onClick: () => void;
  }>;
}

interface ToastContextType {
  showToast: (toast: Omit<Toast, 'id'>) => string;
  hideToast: (id: string) => void;
  hideAllToasts: () => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

interface ToastProviderProps {
  children: React.ReactNode;
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = Math.random().toString(36).substr(2, 9);
    const newToast: Toast = {
      id,
      duration: 5000,
      ...toast,
    };
    
    setToasts(prev => [...prev, newToast]);
    
    // Auto-hide after duration
    if (newToast.duration && newToast.duration > 0) {
      setTimeout(() => {
        hideToast(id);
      }, newToast.duration);
    }
    
    return id;
  }, []);

  const hideToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(toast => toast.id !== id));
  }, []);

  const hideAllToasts = useCallback(() => {
    setToasts([]);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast, hideToast, hideAllToasts }}>
      {children}
      <ToastContainer toasts={toasts} onHide={hideToast} />
    </ToastContext.Provider>
  );
}

interface ToastContainerProps {
  toasts: Toast[];
  onHide: (id: string) => void;
}

function ToastContainer({ toasts, onHide }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className={styles.toastContainer}>
      {toasts.map(toast => (
        <ToastItem key={toast.id} toast={toast} onHide={onHide} />
      ))}
    </div>
  );
}

interface ToastItemProps {
  toast: Toast;
  onHide: (id: string) => void;
}

function ToastItem({ toast, onHide }: ToastItemProps) {
  const getIcon = (type: Toast['type']) => {
    switch (type) {
      case 'success':
        return '✓';
      case 'error':
        return '✕';
      case 'warning':
        return '⚠';
      case 'info':
        return 'ℹ';
      default:
        return 'ℹ';
    }
  };

  return (
    <div className={`${styles.toast} ${styles[toast.type]}`}>
      <div className={styles.toastIcon}>
        {getIcon(toast.type)}
      </div>
      
      <div className={styles.toastContent}>
        {toast.title && (
          <div className={styles.toastTitle}>
            {toast.title}
          </div>
        )}
        <div className={styles.toastMessage}>
          {toast.message}
        </div>
        
        {toast.actions && toast.actions.length > 0 && (
          <div className={styles.toastActions}>
            {toast.actions.map((action, index) => (
              <button
                key={index}
                onClick={action.onClick}
                className="text-sm text-primary hover:text-primary-dark underline"
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>
      
      <button
        className={styles.toastClose}
        onClick={() => onHide(toast.id)}
        aria-label="Close notification"
      >
        ×
      </button>
      
      {toast.duration && toast.duration > 0 && (
        <div
          className={styles.toastProgress}
          style={{ animationDuration: `${toast.duration}ms` }}
        />
      )}
    </div>
  );
}

// Convenience hooks
export function useSuccessToast() {
  const { showToast } = useToast();
  return useCallback((message: string, title?: string) => {
    return showToast({ type: 'success', message, title });
  }, [showToast]);
}

export function useErrorToast() {
  const { showToast } = useToast();
  return useCallback((message: string, title?: string) => {
    return showToast({ type: 'error', message, title });
  }, [showToast]);
}

export function useWarningToast() {
  const { showToast } = useToast();
  return useCallback((message: string, title?: string) => {
    return showToast({ type: 'warning', message, title });
  }, [showToast]);
}

export function useInfoToast() {
  const { showToast } = useToast();
  return useCallback((message: string, title?: string) => {
    return showToast({ type: 'info', message, title });
  }, [showToast]);
}

export default Toast;
