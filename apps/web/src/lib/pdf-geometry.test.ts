import { expect, it } from 'vitest';
import { pdfBoxToViewport } from './pdf-geometry';

it.each([
  [[0, 2, 2, 0, -40, -20], { left: 0, top: 0, width: 40, height: 40 }],
  [[-2, 0, 0, 2, 200, -40], { left: 140, top: 0, width: 40, height: 40 }],
  [[0, -2, -2, 0, 120, 80], { left: 40, top: 20, width: 40, height: 40 }],
])('transforms every corner for rotated viewport %j', (transform, expected) => {
  expect(pdfBoxToViewport([10, 20, 30, 40], transform as number[])).toEqual(expected);
});

it('preserves negative original origin under zoom and PDF y-axis inversion', () => {
  expect(pdfBoxToViewport([-10, -20, 10, 0], [3, 0, 0, -3, 30, 60]))
    .toEqual({ left: 0, top: 60, width: 60, height: 60 });
});

it.each([
  [10, 20, 9, 40], [10, 20, 30, 20], [10, Number.NaN, 30, 40],
])('rejects invalid PDF rectangle %j', (...box) => {
  expect(() => pdfBoxToViewport(box as [number, number, number, number], [1, 0, 0, -1, 0, 100]))
    .toThrow(RangeError);
});

it.each([[1, 0], [1, 0, 0, 0, 0, 0], [1, 0, 0, -1, Infinity, 100]])
  ('rejects invalid viewport matrix %j', (...transform) => {
    expect(() => pdfBoxToViewport([10, 20, 30, 40], transform)).toThrow(RangeError);
  });
