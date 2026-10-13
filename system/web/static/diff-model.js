(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  else root.DiffModel = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function gitPath(value) {
    let path = value;
    if (path.startsWith('"') && path.endsWith('"')) {
      path = path.slice(1, -1).replace(/(?:\\[0-7]{3})+/g, (bytes) => {
        try {
          return decodeURIComponent(bytes.replace(/\\([0-7]{3})/g, (_, octal) => `%${parseInt(octal, 8).toString(16).padStart(2, "0")}`));
        } catch { return bytes; }
      }).replace(/\\([abtnvfr"\\])/g, (_, char) => ({a:"\x07", b:"\b", t:"\t", n:"\n", v:"\v", f:"\f", r:"\r", '"':'"', "\\":"\\"}[char]));
    }
    return path.replace(/^[ab]\//, "");
  }

  function parse(text = "") {
    const files = [];
    let current = null;
    let oldLine = 0, newLine = 0, oldRemaining = 0, newRemaining = 0;
    for (const raw of String(text).split("\n")) {
      const header = raw.match(/^diff --git ("(?:\\.|[^"])*"|a\/.*?) ("(?:\\.|[^"])*"|b\/.*)$/);
      if (header) {
        if (current && (oldRemaining || newRemaining)) current.partial = true;
        current = {path:gitPath(header[2]), oldPath:gitPath(header[1]), status:"modified", additions:0, deletions:0, rows:[], binary:false};
        files.push(current);
        oldRemaining = newRemaining = 0;
        continue;
      }
      if (!current) continue;
      const hunk = raw.match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/);
      if (hunk) {
        oldLine = Number(hunk[1]); newLine = Number(hunk[3]);
        oldRemaining = Number(hunk[2] ?? 1); newRemaining = Number(hunk[4] ?? 1);
        current.rows.push({kind:"hunk", text:raw});
      } else if (raw.startsWith("\\")) {
        current.rows.push({kind:"note", text:raw});
      } else if (oldRemaining || newRemaining) {
        if (raw.startsWith("+")) {
          current.additions += 1;
          current.rows.push({kind:"add", text:raw.slice(1), newLine:newLine++});
          newRemaining = Math.max(0, newRemaining - 1);
        } else if (raw.startsWith("-")) {
          current.deletions += 1;
          current.rows.push({kind:"del", text:raw.slice(1), oldLine:oldLine++});
          oldRemaining = Math.max(0, oldRemaining - 1);
        } else if (raw.startsWith(" ")) {
          current.rows.push({kind:"ctx", text:raw.slice(1), oldLine:oldLine++, newLine:newLine++});
          oldRemaining = Math.max(0, oldRemaining - 1);
          newRemaining = Math.max(0, newRemaining - 1);
        }
      } else if (raw) {
        if (raw.startsWith("new file mode")) current.status = "added";
        if (raw.startsWith("deleted file mode")) current.status = "deleted";
        if (/^rename (from|to) /.test(raw)) current.status = "renamed";
        if (/^(Binary files|GIT binary patch)/.test(raw)) current.binary = true;
        current.rows.push({kind:"meta", text:raw});
      }
    }
    if (current && (oldRemaining || newRemaining)) current.partial = true;
    return files;
  }

  function fileView(paths = [], files = [], selectedPath = null, query = "") {
    const byPath = new Map(files.map(file => [file.path, file]));
    const all = [...new Set([...paths, ...byPath.keys()])].map(path => ({path, file:byPath.get(path) || null}));
    const needle = query.trim().toLowerCase();
    const matches = all.filter(item => item.path.toLowerCase().includes(needle));
    const selected = matches.find(item => item.path === selectedPath) || matches[0] || null;
    const index = matches.indexOf(selected);
    return {all, matches, selected, total:all.length, position:index + 1, previous:matches[index - 1]?.path || null, next:matches[index + 1]?.path || null};
  }

  function annotations(file, findings = []) {
    const byRow = {}, unplaced = [];
    for (const item of findings.filter(item => item.path === file.path)) {
      // Findings refer to the target snapshot. Never attach them to a removed
      // line just because its old line number happens to match.
      const index = item.line ? file.rows.findIndex(row => row.newLine === item.line) : -1;
      if (index < 0) unplaced.push(item);
      else (byRow[index] ||= []).push(item);
    }
    return {byRow, unplaced};
  }

  return {parse, fileView, annotations};
});
