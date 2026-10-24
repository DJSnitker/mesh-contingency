// The replies in tests/fixtures/app_replies.json, which the bot's own tests
// check it really sends (tests/test_app_replies.py).
import fixtures from '../../../../tests/fixtures/app_replies.json';
import { parseJoin, parseNotice, parseWhoami, reassemble } from './replies';

interface Case {
  name: string;
  send?: string;
  to?: string;
  split?: boolean;
  text?: string;
  reply: string[];
  parsed?: Record<string, unknown>;
}

describe('replies', () => {
  for (const c of fixtures.cases as Case[]) {
    it(`reads ${c.name}`, () => {
      if (c.split) {
        expect(reassemble(c.reply)).toEqual({ text: c.text, numbered: true, complete: true });
        expect(reassemble([...c.reply].reverse()).text).toBe(c.text);
        return;
      }
      const text = c.reply.join('\n');
      const parsed = c.to
        ? parseNotice(text)
        : c.send!.split(' ')[0] === 'whoami'
          ? parseWhoami(text)
          : parseJoin(text);
      expect(parsed).toEqual(c.parsed);
    });
  }

  it("says a numbered reply isn't complete until every part is in", () => {
    expect(reassemble(['(2/3) b', '(1/3) a'])).toEqual({
      text: 'a b',
      numbered: true,
      complete: false,
    });
    expect(reassemble(['(2/3) b', '(1/3) a', '(3/3) c']).complete).toBe(true);
  });

  it('keeps other messages in the order they came', () => {
    expect(reassemble(['one', 'two'])).toEqual({
      text: 'one\ntwo',
      numbered: false,
      complete: true,
    });
  });

  it("reads what it doesn't know as nothing, so its text is shown", () => {
    expect(parseWhoami('whoami: something new')).toBeNull();
    expect(parseJoin('hello')).toBeNull();
    expect(parseNotice('join: request sent to the admins as Bob')).toBeNull();
  });
});
