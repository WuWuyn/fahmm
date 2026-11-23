import ReactMarkdown from "react-markdown";

type Block = { kind: "markdown"; text: string } | { kind: "table"; rows: string[][] };

function isRule(line: string): boolean {
  return /^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/.test(line);
}

function cells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

export function MinutesMarkdown({ source }: { source: string }) {
  const lines = source.split("\n");
  const blocks: Block[] = [];
  let text: string[] = [];
  const flush = () => {
    if (text.length) blocks.push({ kind: "markdown", text: text.join("\n") });
    text = [];
  };
  for (let index = 0; index < lines.length;) {
    if (lines[index].trim().startsWith("|") && index + 1 < lines.length && isRule(lines[index + 1])) {
      flush();
      const rows = [cells(lines[index])];
      index += 2;
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        const row = cells(lines[index]);
        if (row.length === rows[0].length) rows.push(row);
        index++;
      }
      blocks.push({ kind: "table", rows });
    } else {
      text.push(lines[index]);
      index++;
    }
  }
  flush();
  return <>{blocks.map((block, index) => block.kind === "markdown"
    ? <ReactMarkdown key={index}>{block.text}</ReactMarkdown>
    : <div className="minutes-table-scroll" key={index}><table><thead><tr>{block.rows[0].map((cell, column) =>
        <th key={column}>{cell}</th>)}</tr></thead><tbody>{block.rows.slice(1).map((row, rowIndex) =>
          <tr key={rowIndex}>{row.map((cell, column) => <td key={column}>{cell}</td>)}</tr>)}</tbody></table></div>)}</>;
}
