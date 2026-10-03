export function pdfBoxToViewport(
  box: readonly [number, number, number, number],
  transform: readonly number[],
): { left: number; top: number; width: number; height: number } {
  if (box.length !== 4 || box.some(value => !Number.isFinite(value)) ||
      box[0] >= box[2] || box[1] >= box[3] || transform.length !== 6 ||
      transform.some(value => !Number.isFinite(value))) {
    throw new RangeError('Invalid PDF geometry.');
  }
  const [a, b, c, d, e, f] = transform;
  if (a*d - b*c === 0) throw new RangeError('Invalid PDF viewport.');
  const corners = [
    [box[0], box[1]], [box[0], box[3]], [box[2], box[1]], [box[2], box[3]],
  ].map(([x, y]) => [a*x + c*y + e, b*x + d*y + f]);
  const left = Math.min(...corners.map(point => point[0]));
  const top = Math.min(...corners.map(point => point[1]));
  return {
    left, top,
    width: Math.max(...corners.map(point => point[0])) - left,
    height: Math.max(...corners.map(point => point[1])) - top,
  };
}
