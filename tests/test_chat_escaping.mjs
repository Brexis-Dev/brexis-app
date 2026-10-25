// Guards the chat streaming-render XSS fix. Run: node tests/test_chat_escaping.mjs
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, '..', 'templates', 'chat.html'), 'utf8');

// 1. Behavioural: reproduce the exact streaming transform (esc then linkify)
//    and confirm injected markup is neutralised while URLs still linkify.
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const renderStreaming = (raw) =>
  esc(raw).replace(/(https?:\/\/[^\s<>"]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');

const malicious = 'see <img src=x onerror=alert(1)> and <script>alert(2)</script>';
const out = renderStreaming(malicious);
assert.ok(!/<img/i.test(out), 'raw <img> must not survive');
assert.ok(!/<script/i.test(out), 'raw <script> must not survive');
assert.ok(out.includes('&lt;img'), 'injected markup must be escaped');

const linked = renderStreaming('visit https://example.com/a?b=1 now');
assert.ok(linked.includes('<a href="https://example.com/a?b=1"'), 'URLs must still linkify');

// 2. Source guard: the streaming branch must escape before innerHTML, and the
//    old unescaped assignment must be gone.
assert.ok(
  html.includes('const raw = esc(bubble.textContent);'),
  'streaming render must escape via esc() before innerHTML'
);
assert.ok(
  !/const raw = bubble\.textContent;\s*\n\s*bubble\.innerHTML = raw\.replace/.test(html),
  'the old unescaped streaming assignment must be removed'
);

console.log('chat escaping tests passed');
