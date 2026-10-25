import { FakeBle } from '../radio/fake-ble';
import { openScreen } from '../screens.testing';
import { ANDROID, APACHE, BUILT, CAPACITOR_ANDROID, parseNotices } from './licenses-screen';

const DASHES = '-'.repeat(80);
/** As angular.json's production build writes it. */
const NOTICES = [
  '',
  'Package: @liamcottle/meshcore.js',
  'License: "MIT"',
  '',
  'MIT License',
  '',
  'Copyright (c) 2025-2026 Liam Cottle',
  '',
  DASHES,
  'Package: rxjs',
  'License: "Apache-2.0"',
  '',
  '                               Apache License',
  '',
  DASHES,
  'Package: @fontsource/inter',
  'License: "OFL-1.1"',
  '',
  'This license is copied below.',
  '-'.repeat(59),
  'SIL OPEN FONT LICENSE Version 1.1',
  '',
  DASHES,
  'Package: no-text',
  'License: "ISC"',
  '',
  DASHES,
  '',
]
  .join('\n')
  .replace(/^/, DASHES);

describe('LicensesScreen', () => {
  let files: Record<string, string>;

  beforeEach(() => {
    localStorage.clear();
    files = {
      [BUILT]: NOTICES,
      [CAPACITOR_ANDROID]: 'MIT License\n\nCopyright (c) 2017-present Drifty Co.\n',
      [APACHE]: 'Apache License\nVersion 2.0, January 2004\n',
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string) =>
        path in files ? new Response(files[path]) : new Response('not found', { status: 404 }),
      ),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  async function open() {
    const screen = await openScreen('/radio/licenses', new FakeBle(), false);
    await vi.waitFor(() => {
      screen.fixture.detectChanges();
      expect(screen.page.querySelector('[role="status"]')).toBeNull();
    });
    const names = (section: string) =>
      [...screen.page.querySelectorAll(`.${section} .name`)].map((e) => e.textContent?.trim());
    return { ...screen, names };
  }

  it("reads the build's notices: each package, its license and its text", () => {
    expect(parseNotices(NOTICES)).toEqual([
      {
        name: '@liamcottle/meshcore.js',
        license: 'MIT',
        text: 'MIT License\n\nCopyright (c) 2025-2026 Liam Cottle',
      },
      { name: 'rxjs', license: 'Apache-2.0', text: `${' '.repeat(31)}Apache License` },
      {
        name: '@fontsource/inter',
        license: 'OFL-1.1',
        text: `This license is copied below.\n${'-'.repeat(59)}\nSIL OPEN FONT LICENSE Version 1.1`,
      },
      { name: 'no-text', license: 'ISC', text: null },
    ]);
    expect(parseNotices('')).toEqual([]);
  });

  it('lists the packages in the app, and the Android libraries, with their licenses', async () => {
    const { page, names } = await open();
    expect(names('app')).toEqual([
      '@liamcottle/meshcore.js',
      'rxjs',
      '@fontsource/inter',
      'no-text',
    ]);
    expect(names('android')).toEqual(['Capacitor (Android)', ...ANDROID.map((a) => a.name)]);
    const meshcore = page.querySelector('.app details')!;
    expect(meshcore.querySelector('.license')?.textContent).toBe('MIT');
    expect(meshcore.querySelector('pre')?.textContent).toContain('Liam Cottle');
    const android = [...page.querySelectorAll('.android details')];
    expect(android[0].querySelector('pre')?.textContent).toContain('Drifty Co.');
    expect(android[1].textContent).toContain('Copyright The Android Open Source Project');
    expect(android[1].querySelector('pre')?.textContent).toContain('Version 2.0');
  });

  it("says so when the build didn't write the notices (a browser's dev server)", async () => {
    delete files[BUILT];
    const { page, names } = await open();
    expect(names('app')).toEqual([]);
    expect(page.querySelector('.app')?.textContent).toContain("this build doesn't have it");
    expect(names('android')).toHaveLength(ANDROID.length + 1);
  });

  it('opens from Radio, which stays the tab lit, not from the tab bar', async () => {
    const { page, fixture } = await openScreen('/radio', new FakeBle(), false);
    const link = page.querySelector<HTMLAnchorElement>('a[href="#/radio/licenses"]');
    expect(link?.textContent).toContain('Open-source licenses');
    expect(page.querySelector('.tabs a[href="#/radio/licenses"]')).toBeNull();
    link!.click();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(page.querySelector('h1')?.textContent).toContain('Open-source licenses');
    });
    expect(page.querySelector('.tabs a.active')?.textContent).toContain('Radio');
  });
});
