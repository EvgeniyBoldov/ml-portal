import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeRaw from 'rehype-raw';
import rehypePrism from 'rehype-prism-plus';
import styles from './MarkdownMessage.module.css';

type Props = { content: string };

const MarkdownMessage: React.FC<Props> = ({ content }) => {
  return (
    <div className={styles.markdown}>
      <ReactMarkdown
        // GitHub-flavored Markdown + single-line breaks + allow basic raw HTML (e.g., <br/>)
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={[rehypeRaw, rehypePrism]}
      >
        {content ?? ''}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownMessage;
