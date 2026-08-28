import { describe, expect, test } from 'vitest';
import { edgarJump, isKeyboardTarget, textFragmentPhrase, type CorpusParagraph } from './corpus';

const paragraph = (index: number, text: string): CorpusParagraph => ({
  index,
  start: 0,
  end: text.length,
  text,
  is_furniture: false,
});

describe('corpus reader helpers', () => {
  test('builds a safe six-to-twelve word EDGAR text fragment', () => {
    expect(textFragmentPhrase('These are six safe words from this sentence.')).toBe(
      'These are six safe words from this sentence.',
    );
    expect(textFragmentPhrase('too short')).toBeNull();
  });

  test('unwraps inline XBRL and prefers a following paragraph for an approximate jump', () => {
    const result = edgarJump(
      'https://www.sec.gov/ix?doc=/Archives/example.htm',
      [
        paragraph(1, 'short'),
        paragraph(2, 'Following paragraph has enough ordinary words for a safe exact match.'),
        paragraph(3, 'Previous paragraph also has enough ordinary words for matching safely.'),
      ],
      1,
    );
    expect(result.approximate).toBe(true);
    expect(result.url).toMatch(/^https:\/\/www\.sec\.gov\/Archives\/example\.htm#:~:text=/);
    expect(decodeURIComponent(result.url)).toContain('Following paragraph has enough ordinary');
  });

  test('guards interactive and editable keyboard targets', () => {
    const input = document.createElement('input');
    const button = document.createElement('button');
    const text = document.createElement('p');
    expect(isKeyboardTarget(input)).toBe(true);
    expect(isKeyboardTarget(button)).toBe(true);
    expect(isKeyboardTarget(text)).toBe(false);
  });
});
