import { ago, duration } from './time';

describe('time', () => {
  it('says how long ago, as the bot does', () => {
    expect(ago(100, 130)).toBe('just now');
    expect(ago(0, 5 * 60)).toBe('5m ago');
    expect(ago(0, 3 * 3600 + 59)).toBe('3h ago');
    expect(ago(0, 2 * 86400 + 5)).toBe('2d ago');
  });

  it('says a length of time in its two largest units', () => {
    expect(duration(59)).toBe('0m');
    expect(duration(12 * 60 + 5)).toBe('12m');
    expect(duration(3 * 3600 + 5 * 60)).toBe('3h 5m');
    expect(duration(2 * 86400 + 3 * 3600)).toBe('2d 3h');
  });
});
