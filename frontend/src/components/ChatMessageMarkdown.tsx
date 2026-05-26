import ReactMarkdown, { type Components } from 'react-markdown';
import remarkBreaks from 'remark-breaks';

const components: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0 first:mt-0">{children}</p>,
  em: ({ children }) => <em className="italic">{children}</em>,
  strong: ({ children }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  ul: ({ children }) => (
    <ul className="list-disc pl-4 mb-2 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-4 mb-2 space-y-0.5">{children}</ol>
  ),
  li: ({ children }) => <li className="[&>p]:mb-0">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="underline text-[#2A9FFF] hover:opacity-90"
    >
      {children}
    </a>
  ),
};

interface ChatMessageMarkdownProps {
  content: string;
}

export function ChatMessageMarkdown({ content }: ChatMessageMarkdownProps) {
  return (
    <div className="text-sm break-words">
      <ReactMarkdown remarkPlugins={[remarkBreaks]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
