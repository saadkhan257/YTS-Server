// utils.js

// Format timestamp as [HH:MM:SS]
function formatTimestamp(date = new Date()) {
  return `[${date.toLocaleTimeString()}]`;
}

// Create a log entry DOM element
function createLogEntry(logData) {
  const entry = document.createElement('div');
  entry.classList.add('log-entry');

  // Detect log type for styling
  const type = detectLogType(logData.message);
  entry.classList.add(`log-${type}`);

  // Format message
  const timestamp = formatTimestamp(new Date(logData.timestamp));
  entry.innerHTML = `<span class="log-time">${timestamp}</span> <span class="log-msg">${escapeHtml(logData.message)}</span>`;

  return entry;
}

// Escape HTML to prevent injection
function escapeHtml(text) {
  const div = document.createElement('div');
  div.innerText = text;
  return div.innerHTML;
}

// Detect type of log: info, warning, error, debug
function detectLogType(message) {
  const lower = message.toLowerCase();
  if (lower.includes('error') || lower.includes('failed')) return 'error';
  if (lower.includes('warn')) return 'warn';
  if (lower.includes('debug')) return 'debug';
  return 'info';
}
