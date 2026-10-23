import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { Api } from './api';
import { Runner } from './runner';
import { FakeApi } from '../testing/fakes';

describe('Runner', () => {
  let api: FakeApi;
  let runner: Runner;
  let done: number;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [Runner, { provide: Api, useValue: api }] });
    runner = TestBed.inject(Runner);
    done = 0;
    runner.onDone = () => done++;
  });

  it('keeps the reply and says something changed', () => {
    runner.run('whois', 'a1');
    expect(api.ran).toEqual([['whois', 'a1']]);
    expect(runner.last()?.answer?.messages).toEqual(['whois: done']);
    expect(runner.busy()).toBe(false);
    expect(done).toBe(1);
  });

  it('waits for confirm when the command asks, then sends the same again', () => {
    api.answer = (command) => of({ command, messages: ['remove: this removes Bob…'], asks: true });
    runner.run('remove', 'b0');
    expect(done).toBe(0);
    api.answer = (command) => of({ command, messages: ['remove: Bob removed'], asks: false });
    runner.confirm();
    expect(api.ran).toEqual([
      ['remove', 'b0'],
      ['remove', 'b0'],
    ]);
    expect(runner.last()?.answer?.messages).toEqual(['remove: Bob removed']);
    expect(done).toBe(1);
  });

  it('confirms nothing that did not ask', () => {
    runner.run('whois', 'a1');
    runner.confirm();
    expect(api.ran.length).toBe(1);
  });

  it("shows the bot's reason when it refuses", () => {
    api.answer = () =>
      throwError(
        () =>
          new HttpErrorResponse({
            status: 429,
            error: { error: 'remove: limit reached, try again in 5m' },
          }),
      );
    runner.run('remove', 'b0');
    expect(runner.last()?.error).toBe('remove: limit reached, try again in 5m');
    expect(done).toBe(0);
  });

  it("says when the bot can't be reached", () => {
    api.answer = () => throwError(() => new HttpErrorResponse({ status: 0 }));
    runner.run('health');
    expect(runner.last()?.error).toBe("can't reach the bot");
  });
});
