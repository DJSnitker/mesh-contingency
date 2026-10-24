import type { CapacitorConfig } from '@capacitor/cli';

// The phone app: its Android package id, and the Angular build it ships.
const config: CapacitorConfig = {
  appId: 'com.meshcontingency',
  appName: 'Mesh Contingency',
  webDir: 'dist',
  plugins: {
    SystemBars: {
      // Draw under the status and gesture bars, as index.html's
      // viewport-fit=cover asks; the header and tabs pad themselves by
      // env(safe-area-inset-*).
      insetsHandling: 'native',
      initialViewportFitValueHint: 'cover',
      // Light icons, for the dark app.
      style: 'DARK',
    },
  },
};

// scripts/android.sh live: load the dev server (npm start) instead, so the
// app reloads as src/ changes. Only for trying it on this computer; a normal
// cap sync (npm run android) puts the built app back.
const live = process.env['CAPACITOR_LIVE'];
if (live) {
  config.server = { url: live, cleartext: true };
}

export default config;
