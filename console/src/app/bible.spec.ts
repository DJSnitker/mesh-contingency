import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Answer, Api } from './api';
import { Bible, passage } from './bible';
import { FakeApi } from '../testing/fakes';

function answer(messages: string[], ok = true): Answer {
  return { command: 'verse', messages, asks: false, ok };
}

describe('passage', () => {
  it('splits the reference from the text, and joins numbered parts', () => {
    expect(passage(answer(['John 3:16 For God so loved the world']))).toEqual({
      reference: 'John 3:16',
      text: 'For God so loved the world',
    });
    expect(passage(answer(['(1/2) Psalm 23:1-2 The LORD is my', '(2/2) shepherd']))).toEqual({
      reference: 'Psalm 23:1-2',
      text: 'The LORD is my shepherd',
    });
    expect(passage(answer(['1 John 4:8 God is love']))?.reference).toBe('1 John 4:8');
  });

  it("isn't one for an error", () => {
    expect(passage(answer(['verse: not found: Hezekiah 1:1'], false))).toBeNull();
    expect(passage(answer(['usage: verse [book chapter:verse[-verse]]']))).toBeNull();
  });
});

describe('Bible', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    api.answer = (_command, text) =>
      of(
        text === ''
          ? answer(['Genesis 1:1 In the beginning God created the heavens and the earth.'])
          : text === 'jn 3:16'
            ? answer(['John 3:16 For God so loved the world'])
            : answer([`verse: not found: ${text}`], false),
      );
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render() {
    const fixture = TestBed.createComponent(Bible);
    await fixture.whenStable();
    return fixture;
  }

  it('shows the verse of the day', async () => {
    const element: HTMLElement = (await render()).nativeElement;
    expect(api.ran).toEqual([['verse', '']]);
    expect(element.querySelector('.today strong')?.textContent).toBe('Genesis 1:1');
    expect(element.querySelector('.today .passage')?.textContent).toContain('In the beginning');
  });

  it('looks up a verse, and says when it finds none', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    const box = element.querySelector<HTMLInputElement>('input[name=reference]')!;
    const look = [...element.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Look it up'),
    )!;
    expect(look.disabled).toBe(true);
    box.value = 'jn 3:16';
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    look.click();
    await fixture.whenStable();
    expect(api.ran.at(-1)).toEqual(['verse', 'jn 3:16']);
    expect(element.querySelector('.found strong')?.textContent).toBe('John 3:16');

    box.value = 'Hezekiah 1:1';
    box.dispatchEvent(new Event('input'));
    box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await fixture.whenStable();
    expect(element.querySelector('.found')).toBeNull();
    expect(element.querySelector('.lookup .problem')?.textContent).toContain(
      'verse: not found: Hezekiah 1:1',
    );
  });
});
