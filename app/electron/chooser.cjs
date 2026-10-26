// The desktop app's own small windows: a list to pick a radio (or a USB
// port) from, and a box for a radio's Bluetooth PIN. Each is a page built
// here, shown over the app's window, answering through chooser-preload.cjs.

const path = require('node:path');
const { BrowserWindow, ipcMain } = require('electron');

const STYLE = `
  :root { color-scheme: dark; font: 15px system-ui, sans-serif; }
  body { margin: 0; padding: 16px; background: #0e1116; color: #e6e8eb; display: grid; gap: 12px; }
  h1 { margin: 0; font-size: 1.1rem; }
  p { margin: 0; color: #9aa3ad; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; max-height: 240px; overflow: auto; }
  button { font: inherit; color: inherit; border: 1px solid #2a313a; background: #161b22;
           border-radius: 8px; padding: 8px 12px; cursor: pointer; text-align: left; width: 100%; }
  button:hover, button:focus { border-color: #4f9cf9; outline: none; }
  .item small { display: block; color: #9aa3ad; font-size: 0.8rem; }
  .actions { display: flex; gap: 8px; justify-content: flex-end; }
  .actions button { width: auto; }
  input { font: inherit; color: inherit; background: #161b22; border: 1px solid #2a313a;
          border-radius: 8px; padding: 8px 12px; }
`;

const esc = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );

let next = 0;

/** Show a page in a small window over `parent`, and resolve with what it answers (null if closed). */
function ask(parent, title, body, height) {
  const id = `chooser-${++next}`;
  return new Promise((resolve) => {
    const win = new BrowserWindow({
      parent: parent ?? undefined,
      modal: Boolean(parent),
      width: 420,
      height,
      resizable: false,
      minimizable: false,
      maximizable: false,
      title,
      backgroundColor: '#0e1116',
      autoHideMenuBar: true,
      webPreferences: {
        preload: path.join(__dirname, 'chooser-preload.cjs'),
        additionalArguments: [`--chooser=${id}`],
        contextIsolation: true,
        sandbox: true,
      },
    });
    let answered = false;
    const done = (_event, value) => {
      answered = true;
      resolve(value ?? null);
      win.close();
    };
    ipcMain.once(id, done);
    win.on('closed', () => {
      ipcMain.removeListener(id, done);
      if (!answered) {
        resolve(null);
      }
    });
    const page = `<!doctype html><meta charset="utf-8"><title>${esc(title)}</title><style>${STYLE}</style>${body}`;
    void win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(page)}`);
  });
}

/** A list to pick one of `items` ({ id, label, detail }) from: its id, or null. */
function choose(parent, { title, empty, items }) {
  const list = items.length
    ? `<ul>${items
        .map(
          (item) =>
            `<li><button class="item" data-id="${esc(item.id)}">${esc(item.label)}` +
            (item.detail && item.detail !== item.label
              ? `<small>${esc(item.detail)}</small>`
              : '') +
            `</button></li>`,
        )
        .join('')}</ul>`
    : `<p>${esc(empty)}</p>`;
  const body = `<h1>${esc(title)}</h1>${list}
    <div class="actions"><button id="cancel">Cancel</button></div>
    <script>
      for (const b of document.querySelectorAll('.item')) b.onclick = () => chooser.done(b.dataset.id);
      document.getElementById('cancel').onclick = () => chooser.done(null);
      document.onkeydown = (e) => e.key === 'Escape' && chooser.done(null);
      document.querySelector('button').focus();
    </script>`;
  return ask(parent, title, body, Math.min(460, 150 + items.length * 56));
}

/** A box for a radio's Bluetooth PIN: what was typed, or null. */
function askPin(parent, deviceId) {
  const body = `<h1>Bluetooth PIN</h1>
    <p>Type the radio's Bluetooth PIN (${esc(deviceId)}). It's on the radio's screen, or 123456 if it has none.</p>
    <form id="f"><input id="pin" inputmode="numeric" autocomplete="off" autofocus required />
    <div class="actions" style="margin-top:12px"><button type="button" id="cancel">Cancel</button><button>Pair</button></div></form>
    <script>
      document.getElementById('f').onsubmit = (e) => { e.preventDefault(); chooser.done(document.getElementById('pin').value.trim()); };
      document.getElementById('cancel').onclick = () => chooser.done(null);
      document.onkeydown = (e) => e.key === 'Escape' && chooser.done(null);
    </script>`;
  return ask(parent, 'Bluetooth PIN', body, 240);
}

module.exports = { askPin, choose };
