// The desktop app (roadmap item 18): the app's web build (dist/) in an
// Electron window, so a radio is reached over Web Bluetooth or Web Serial
// (USB), which Chromium has and the systems' own web views don't. Chromium
// asks the browser to show its device choosers and PIN prompts; Electron
// leaves them to the app, so they're here: chooser.cjs asks the user.

const { execFile } = require('node:child_process');
const fs = require('node:fs');
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

/**
 * A USB device as the permission check sees it: maker, model and serial
 * number. Not which port: two radios of the same model (a CP2102 board's
 * serial number is often 0001) look the same, so the app reconnects without
 * asking only when one allowed port matches (radio.ts).
 */
const device = (vendor, product, serial) => `${Number(vendor)}:${Number(product)}:${serial ?? ''}`;

/**
 * Chromium on Linux takes an idle read on a port left with VMIN=0 (by
 * another program) as the device lost (Chromium issue 559872992): set it
 * back to waiting for a byte, as a freshly plugged-in port is.
 */
function readyPort(port) {
  return new Promise((resolve) => {
    if (process.platform !== 'linux') {
      resolve();
      return;
    }
    execFile('stty', ['-F', `/dev/${port.portName}`, 'min', '1', 'time', '0'], () => resolve());
  });
}

/**
 * Web Serial: the user picks a USB port from a list, and the app may use
 * that device again, after a restart too (getPorts, to reconnect without
 * asking), but no other.
 */
function allowSerial(ses) {
  const file = path.join(app.getPath('userData'), 'usb-devices.json');
  let allowed = new Set();
  try {
    allowed = new Set(JSON.parse(fs.readFileSync(file, 'utf8')));
  } catch {
    // None yet.
  }
  ses.setPermissionCheckHandler((_contents, permission) =>
    ['serial', 'bluetooth'].includes(permission),
  );
  ses.setDevicePermissionHandler(
    ({ deviceType, device: d }) =>
      deviceType === 'serial' && allowed.has(device(d.vendor_id, d.product_id, d.serial_number)),
  );
  ses.on('select-serial-port', async (event, ports, contents, callback) => {
    event.preventDefault();
    // USB ports only: not the computer's own serial ports (ttyS0...).
    const usb = ports.filter((p) => p.vendorId);
    const id = await choose(BrowserWindow.fromWebContents(contents), {
      title: 'Connect over USB',
      empty:
        'No USB serial port found. Plug the radio in with a USB cable that carries data, then try again.',
      items: usb.map((p) => ({
        id: p.portId,
        label: p.displayName || p.portName,
        detail: p.portName,
      })),
    });
    const picked = usb.find((p) => p.portId === id);
    if (picked) {
      allowed.add(device(picked.vendorId, picked.productId, picked.serialNumber));
      fs.writeFileSync(file, JSON.stringify([...allowed]));
      await readyPort(picked);
    }
    callback(picked?.portId ?? '');
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
