import { readdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const directory = new URL('../desktop/ui/icons/', import.meta.url);
const output = new URL('../desktop/ui/icons.js', import.meta.url);
const icons = {};
for (const filename of (await readdir(directory)).filter(name => name.endsWith('.svg')).sort()) {
  const svg = await readFile(new URL(filename, directory));
  icons[filename.slice(0, -4)] = `data:image/svg+xml;base64,${svg.toString('base64')}`;
}
await writeFile(output, `window.ESCORT_ICONS = ${JSON.stringify(icons)};\n`, 'utf8');
