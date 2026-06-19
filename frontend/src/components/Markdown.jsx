import React from "react";

// Tiny markdown renderer: #/##/### headings, - and * lists, **bold**, *italic*, `code`.
function renderInline(text, keyBase) {
  const out = [];
  let rest = text;
  let k = 0;
  const re = /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)/;
  while (rest) {
    const m = rest.match(re);
    if (!m) {
      out.push(rest);
      break;
    }
    if (m.index > 0) out.push(rest.slice(0, m.index));
    if (m[2] != null) out.push(<strong key={`${keyBase}-${k++}`}>{m[2]}</strong>);
    else if (m[3] != null) out.push(<em key={`${keyBase}-${k++}`}>{m[3]}</em>);
    else if (m[4] != null)
      out.push(
        <code key={`${keyBase}-${k++}`} style={{ background: "#eef0f3", borderRadius: 4, padding: "0 4px" }}>
          {m[4]}
        </code>
      );
    rest = rest.slice(m.index + m[0].length);
  }
  return out;
}

export default function Markdown({ text }) {
  if (!text) return null;
  const lines = text.split(/\r?\n/);
  const blocks = [];
  let list = null;
  let key = 0;

  const flushList = () => {
    if (list && list.length) {
      blocks.push(<ul key={`ul-${key++}`}>{list}</ul>);
    }
    list = null;
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    const li = line.match(/^\s*[-*]\s+(.*)$/);
    if (h) {
      flushList();
      const Tag = `h${h[1].length}`;
      blocks.push(<Tag key={`h-${key++}`}>{renderInline(h[2], `h${key}`)}</Tag>);
    } else if (li) {
      if (!list) list = [];
      list.push(<li key={`li-${key++}`}>{renderInline(li[1], `li${key}`)}</li>);
    } else if (line.trim() === "") {
      flushList();
    } else {
      flushList();
      blocks.push(<p key={`p-${key++}`}>{renderInline(line, `p${key}`)}</p>);
    }
  }
  flushList();
  return <div className="md">{blocks}</div>;
}
