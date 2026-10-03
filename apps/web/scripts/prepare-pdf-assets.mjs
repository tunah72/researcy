import { cp, mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';

const require = createRequire(import.meta.url);
const source = dirname(require.resolve('pdfjs-dist/package.json'));
const { version } = JSON.parse(await readFile(join(source, 'package.json'), 'utf8'));
const target = join(process.cwd(), 'public', 'pdfjs', version);
await mkdir(target, { recursive: true });
await cp(join(source, 'build', 'pdf.worker.min.mjs'), join(target, 'pdf.worker.min.mjs'));
await cp(join(source, 'LICENSE'), join(target, 'LICENSE'));
for (const directory of ['cmaps', 'standard_fonts', 'wasm']) {
  await cp(join(source, directory), join(target, directory), { recursive: true });
}
