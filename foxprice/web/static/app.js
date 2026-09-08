/*
 * Log color classes used by colorizeLog() below are defined in
 * base.html's <style> block, not here:
 *   .log-error { color: #ff6b6b; }
 *   .log-warn  { color: #ffd700; }
 *   .log-info  { color: #7fdbff; }
 */

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function colorizeLog(line) {
  const escaped = escapeHtml(line);

  if (/ERROR|error/.test(line)) {
    return `<span class="log-error">${escaped}</span>`;
  }
  if (/WARNING/i.test(line)) {
    return `<span class="log-warn">${escaped}</span>`;
  }
  if (/INFO/.test(line)) {
    return `<span class="log-info">${escaped}</span>`;
  }
  return escaped;
}

window.colorizeLog = colorizeLog;
window.escapeHtml = escapeHtml;
