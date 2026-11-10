import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { throwError } from 'rxjs';

import { Account } from './account';
import { Api } from './api';
import { FakeApi, SAM } from '../testing/fakes';

describe('Account', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: Api, useValue: api }],
    });
  });

  async function render() {
    const fixture = TestBed.createComponent(Account);
    await fixture.whenStable();
    return fixture;
  }

  async function fill(
    fixture: { whenStable(): Promise<unknown>; nativeElement: HTMLElement },
    ...values: string[]
  ) {
    const inputs = fixture.nativeElement.querySelectorAll<HTMLInputElement>('input');
    values.forEach((value, i) => {
      inputs[i].value = value;
      inputs[i].dispatchEvent(new Event('input'));
    });
    await fixture.whenStable();
    fixture.nativeElement.querySelector<HTMLButtonElement>('button[type=submit]')!.click();
    await fixture.whenStable();
  }

  it('the console on the node has no password to change', async () => {
    const element: HTMLElement = (await render()).nativeElement;
    expect(element.textContent).toContain("The console on the node's own computer");
    expect(element.querySelector('form')).toBeNull();
    expect(element.textContent).not.toContain('Log out');
  });

  it("changes a console user's own password, the current one first", async () => {
    api.me.set(SAM);
    const fixture = await render();
    expect(fixture.nativeElement.textContent).toContain('sam (console)');
    await fill(fixture, 'the old password', 'a brand new password', 'a brand new password');
    expect(api.calls).toEqual([['changePassword', 'the old password', 'a brand new password']]);
    expect(fixture.nativeElement.querySelector('[role=status]')?.textContent).toContain(
      'Password changed',
    );
  });

  it('checks the new one before sending it', async () => {
    api.me.set(SAM);
    const fixture = await render();
    await fill(fixture, 'the old password', 'a brand new password', 'a different one!!');
    expect(fixture.nativeElement.querySelector('[role=alert]')?.textContent).toContain(
      "don't match",
    );
    await fill(fixture, 'the old password', 'short', 'short');
    expect(fixture.nativeElement.querySelector('[role=alert]')?.textContent).toContain(
      '12 or more',
    );
    expect(api.calls).toEqual([]);
  });

  it('says when the current one is wrong', async () => {
    api.me.set(SAM);
    api.changeAnswer = () =>
      throwError(
        () =>
          new HttpErrorResponse({
            status: 403,
            error: { error: "that isn't your current password" },
          }),
      );
    const fixture = await render();
    await fill(fixture, 'not it', 'a brand new password', 'a brand new password');
    expect(fixture.nativeElement.querySelector('[role=alert]')?.textContent).toContain(
      "that isn't your current password",
    );
  });

  it('logs out', async () => {
    api.me.set(SAM);
    const fixture = await render();
    fixture.nativeElement.querySelector('header button').click();
    expect(api.calls).toEqual([['logOut']]);
  });
});
