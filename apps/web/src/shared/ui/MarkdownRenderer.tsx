import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import styles from './MarkdownRenderer.module.css';

interface MarkdownRendererProps {
  content: string;
  enableSyntaxHighlighting?: boolean;
  enableLineBreaks?: boolean;
}

export default function MarkdownRenderer({
  content,
  enableSyntaxHighlighting = true,
  enableLineBreaks = true,
}: MarkdownRendererProps) {
  const isSafeHref = (href?: string) => {
    if (!href) return false;
    const normalized = href.trim().toLowerCase();
    if (normalized.startsWith('javascript:')) return false;
    if (normalized.startsWith('data:')) return false;
    return true;
  };

  const isFileLink = (href: string) => {
    return /\/api\/v1\/files\/[^/]+\/download/i.test(href) || /\/files\/[^/]+\/download/i.test(href);
  };

  const renderCode = ({
    className,
    children,
    ...props
  }: React.HTMLAttributes<HTMLElement> & { children?: React.ReactNode }) => {
    const match = /language-(\w+)/.exec(className || '');
    const language = match ? match[1] : '';
    const code = String(children ?? '').replace(/\n$/, '');
    const isBlockCode = Boolean(language) || code.includes('\n');

    if (isBlockCode && enableSyntaxHighlighting) {
      const label = language || 'text';
      return (
        <div className={styles.codeContainer}>
          <div className={styles.codeHeader}>{label}</div>
          <SyntaxHighlighter
            style={oneDark}
            language={language || 'text'}
            PreTag="div"
            className={styles.preBlock}
            customStyle={{ margin: 0, borderRadius: 0, border: 'none', background: 'transparent' }}
            codeTagProps={{ style: { fontFamily: 'inherit' } }}
            {...props}
          >
            {code}
          </SyntaxHighlighter>
        </div>
      );
    }

    return (
      <code className={styles.inlineCode} {...props}>
        {children}
      </code>
    );
  };

  return (
    <div className={styles.markdown}>
      <ReactMarkdown
        remarkPlugins={enableLineBreaks ? [remarkGfm, remarkBreaks] : [remarkGfm]}
        urlTransform={(url) => (isSafeHref(url) ? url : '')}
        components={{
          code: renderCode,
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
          a({ href, children, ...props }) {
            const safeHref = isSafeHref(href) ? (href as string) : '#';
            const external = /^https?:\/\//i.test(safeHref);
            const fileLink = isFileLink(safeHref);
            return (
              <a
                href={safeHref}
                className={fileLink ? styles.fileLink : undefined}
                target={external || fileLink ? '_blank' : undefined}
                rel={external || fileLink ? 'noopener noreferrer' : undefined}
                {...props}
              >
                {children}
              </a>
            );
          },
          table({ children, ...props }) {
            return (
              <div className={styles.tableWrap}>
                <table className={styles.table} {...props}>
                  {children}
                </table>
              </div>
            );
          },
          th({ children, ...props }) {
            return (
              <th className={styles.tableHead} {...props}>
                {children}
              </th>
            );
          },
          td({ children, ...props }) {
            return (
              <td className={styles.tableCell} {...props}>
                {children}
              </td>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
