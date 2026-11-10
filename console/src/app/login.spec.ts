import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { throwError } from 'rxjs';

import { Api } from './api';
import { Login } from './login';
import { FakeApi } from '../testing/fakes';

describe('Login', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render() {
    const fixture = TestBed.createComponent(Login);
    await fixture.whenStable();
    return fixture;
  }

  function type(element: HTMLElement, name: string, text: string): void {
    const input = element.querySelector<HTMLInputElement>(`input[name=${name}]`)!;
    input.value = text;
    input.dispatchEvent(new Event('input'));
  }

  it('logs in with a name and password', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    const button = element.querySelector<HTMLButtonElement>('button')!;
    expect(button.disabled).toBe(true);
    type(element, 'name', 'sam');
    type(element, 'password', 'correct horse battery');
    await fixture.whenStable();
    expect(button.disabled).toBe(false);
    button.click();
    expect(api.calls).toEqual([['logIn', 'sam', 'correct horse battery']]);
    expect(element.querySelector<HTMLInputElement>('input[type=password]')?.autocomplete).toBe(
      'current-password',
    );
  });

  it('says why a login failed, and forgets the password', async () => {
    api.logInAnswer = () =>
      throwError(
        () => new HttpErrorResponse({ status: 401, error: { error: 'Wrong name or password.' } }),
      );
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    type(element, 'name', 'sam');
    type(element, 'password', 'not it at all');
    await fixture.whenStable();
    element.querySelector<HTMLButtonElement>('button')!.click();
    await fixture.whenStable();
    expect(element.querySelector('[role=alert]')?.textContent).toContain('Wrong name or password.');
    expect(element.querySelector<HTMLInputElement>('input[name=password]')?.value).toBe('');
  });

  it("says when the bot can't be reached", async () => {
    api.logInAnswer = () => throwError(() => new HttpErrorResponse({ status: 0 }));
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    type(element, 'name', 'sam');
    type(element, 'password', 'correct horse battery');
    await fixture.whenStable();
    element.querySelector<HTMLButtonElement>('button')!.click();
    await fixture.whenStable();
    expect(element.querySelector('[role=alert]')?.textContent).toContain("Can't reach the bot");
  });
});
