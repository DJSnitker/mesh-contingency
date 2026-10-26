// The desktop app (roadmap item 18): the app's web build (dist/) in an
// Electron window, so a radio is reached over Web Bluetooth or Web Serial
// (USB), which Chromium has and the systems' own web views don't. Chromium
// asks the browser to show its device choosers and PIN prompts; Electron
// leaves them to the app, so they're here: chooser.cjs asks the user.

const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { app, BrowserWindow, net, protocol, session, shell } = require('electron');

const { askPin, choose } = require('./chooser.cjs');

const DIST = path.join(__dirname, '..', 'dist');
// The app is served as app://mesh/: a secure origin, as Web Bluetooth and
// Web Serial need, unlike file://.
const ORIGIN = 'app://mesh';
// How long to look for radios before showing the list (ms): the list fills as they're heard.
const SCAN_MS = 4000;

// Chromium on Linux keeps Web Bluetooth behind this switch.
if (process.platform === 'linux') {
  app.commandLine.appendSwitch('enable-experimental-web-platform-features');
}

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

/** Serve dist/ at app://mesh/, and nothing outside it. */
function serve() {
  protocol.handle('app', (request) => {
    const { pathname } = new URL(request.url);
    const file = path.join(DIST, decodeURIComponent(pathname === '/' ? '/index.html' : pathname));
    if (!file.startsWith(DIST + path.sep)) {
      return new Response('Not found', { status: 404 });
    }
    return net.fetch(pathToFileURL(file).toString());
  });
}

/** Web Serial: the app may use the ports, and the user picks one from a list. */
function allowSerial(ses) {
  ses.setPermissionCheckHandler((_contents, permission) =>
    ['serial', 'bluetooth'].includes(permission),
  );
  // So getPorts() returns the ports to reconnect to without asking.
  ses.setDevicePermissionHandler((details) => details.deviceType === 'serial');
  ses.on('select-serial-port', async (event, ports, contents, callback) => {
    event.preventDefault();
    const picked = await choose(BrowserWindow.fromWebContents(contents), {
      title: 'Connect over USB',
      empty:
        'No serial port found. Plug the radio in with a USB cable that carries data, then try again.',
      items: ports.map((p) => ({
        id: p.portId,
        label: p.displayName || p.portName,
        detail: p.portName,
      })),
    });
    callback(picked ?? '');
  });
}

/** Web Bluetooth: look for radios a moment, then let the user pick one. */
function chooseBluetooth(win) {
  let latest = null; // { devices, callback } from the newest event
  let waiting = null;
  win.webContents.on('select-bluetooth-device', (event, devices, callback) => {
    event.preventDefault();
    latest = { devices, callback };
    if (waiting) {
      return;
    }
    waiting = setTimeout(async () => {
      const { devices: found } = latest;
      const picked = await choose(win, {
        title: 'Find my radio',
        empty: 'No MeshCore radio found. Turn it on, bring it near the computer, and try again.',
        items: found.map((d) => ({
          id: d.deviceId,
          label: d.deviceName || d.deviceId,
          detail: d.deviceId,
        })),
      });
      // The newest callback answers the request; '' cancels it.
      latest.callback(picked ?? '');
      latest = null;
      waiting = null;
    }, SCAN_MS);
  });
}

/** A radio's Bluetooth PIN, or confirming its pairing (Windows and Linux ask the app). */
function pairBluetooth(ses, win) {
  ses.setBluetoothPairingHandler(async (details, callback) => {
    if (details.pairingKind === 'providePin') {
      const pin = await askPin(win, details.deviceId);
      callback(pin ? { confirmed: true, pin } : { confirmed: false });
    } else {
      callback({ confirmed: true });
    }
  });
}

function open() {
  const win = new BrowserWindow({
    width: 1100,
    height: 820,
    minWidth: 360,
    minHeight: 560,
    title: 'Mesh Contingency',
    backgroundColor: '#0e1116',
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, sandbox: true },
  });
  // Links out (a license's page, say) open in the browser, not in the app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) {
      void shell.openExternal(url);
    }
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(ORIGIN)) {
      event.preventDefault();
    }
  });
  chooseBluetooth(win);
  pairBluetooth(session.defaultSession, win);
  void win.loadURL(`${ORIGIN}/`);
}

app.whenReady().then(() => {
  serve();
  allowSerial(session.defaultSession);
  open();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      open();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
