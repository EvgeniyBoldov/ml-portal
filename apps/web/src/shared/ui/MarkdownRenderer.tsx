import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import styles from './MarkdownRenderer.module.css';

interface MarkdownRendererProps {
  content: string;
  enableSyntaxHighlighting?: boolean; // Новый пропс для управления подсветкой
}

export default function MarkdownRenderer({
  content,
  enableSyntaxHighlighting = true,
}: MarkdownRendererProps) {
  return (
    <div className={styles.markdown}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Стилизация для инлайн кода
          code({ inline, className, children, ...props }) {
            if (inline) {
              return (
                <code className={styles.inlineCode} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className={styles.codeBlock} {...props}>
                {children}
              </code>
            );
          },
          // Стилизация для блоков кода с подсветкой синтаксиса
          pre({ children, ...props }) {
            const match = /language-(\w+)/.exec(props.className || '');
            const language = match ? match[1] : '';

            // Используем подсветку только если включена
            if (language && enableSyntaxHighlighting) {
              return (
                <SyntaxHighlighter
                  style={oneDark}
                  language={language}
                  PreTag="div"
                  className={styles.preBlock}
                  {...props}
                >
                  {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
              );
            }

            // Простой блок кода без подсветки
            return (
              <pre className={styles.preBlock} {...props}>
                {children}
              </pre>
            );
          },
          // Стилизация для параграфов
          p({ children, ...props }) {
            return (
              <p className={styles.paragraph} {...props}>
                {children}
              </p>
            );
          },
          // Стилизация для списков
          ul({ children, ...props }) {
            return (
              <ul className={styles.list} {...props}>
                {children}
              </ul>
            );
          },
          ol({ children, ...props }) {
            return (
              <ol className={styles.orderedList} {...props}>
                {children}
              </ol>
            );
          },
          li({ children, ...props }) {
            return (
              <li className={styles.listItem} {...props}>
                {children}
              </li>
            );
          },
          // Стилизация для заголовков
          h1({ children, ...props }) {
            return (
              <h1 className={styles.h1} {...props}>
                {children}
              </h1>
            );
          },
          h2({ children, ...props }) {
            return (
              <h2 className={styles.h2} {...props}>
                {children}
              </h2>
            );
          },
          h3({ children, ...props }) {
            return (
              <h3 className={styles.h3} {...props}>
                {children}
              </h3>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
