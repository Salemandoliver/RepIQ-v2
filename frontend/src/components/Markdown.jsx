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

const isRow = (s) => /^\s*\|.*\|\s*$/.test(s || "");
const isSep = (s) => /\|/.test(s || "") && /^[\s|:-]+$/.test(s || "") && /-/.test(s || "");
const cells = (s) => s.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

export default function Markdown({ text }) {
  if (!text) return null;
  const lines = text.split(/\r?\n/);
  const blocks = [];
  let list = null;
  let listType = null;
  let key = 0;

  const flushList = () => {
    if (list && list.length) {
      const Tag = listType === "ol" ? "ol" : "ul";
      blocks.push(<Tag key={`l-${key++}`}>{list}</Tag>);
    }
    list = null;
    listType = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd();
    // GitHub-style table: a header row followed by a |---|---| separator row.
    if (isRow(line) && isSep(lines[i + 1])) {
      flushList();
      const header = cells(line);
      const rows = [];
      i += 2;
      while (i < lines.length && isRow(lines[i])) { rows.push(cells(lines[i])); i++; }
      i--;
      blocks.push(
        <table className="md-table" key={`t-${key++}`}>
          <thead><tr>{header.map((c, ci) => <th key={ci}>{renderInline(c, `th${key}-${ci}`)}</th>)}</tr></thead>
          <tbody>{rows.map((r, ri) => <tr key={ri}>{header.map((_, ci) => <td key={ci}>{renderInline(r[ci] || "", `td${key}-${ri}-${ci}`)}</td>)}</tr>)}</tbody>
        </table>
      );
      continue;
    }
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {          // --- horizontal rule
      flushList();
      blocks.push(<hr key={`hr-${key++}`} />);
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    const ol = line.match(/^\s*\d+\.\s+(.*)$/);
    const li = line.match(/^\s*[-*]\s+(.*)$/);
    if (h) {
      flushList();
      const Tag = `h${Math.min(h[1].length, 4)}`;
      blocks.push(<Tag key={`h-${key++}`}>{renderInline(h[2], `h${key}`)}</Tag>);
    } else if (ol) {
      if (!list || listType !== "ol") { flushList(); list = []; listType = "ol"; }
      list.push(<li key={`li-${key++}`}>{renderInline(ol[1], `li${key}`)}</li>);
    } else if (li) {
      if (!list || listType !== "ul") { flushList(); list = []; listType = "ul"; }
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
