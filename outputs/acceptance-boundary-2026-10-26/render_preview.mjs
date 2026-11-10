import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
const require = createRequire(path.join(process.argv[2], '_anchor.cjs'));
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const root = path.dirname(fileURLToPath(import.meta.url));
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(root, 'baseline_replay/workbook.xlsx')));
await fs.mkdir(path.join(root, 'previews'), { recursive: true });
for (const [sheetName, range] of [
  ['Start_Here', 'A1:H44'], ['Evaluation', 'A1:G38'],
  ['Priority_Worklist', 'A1:K8'], ['Auto_Matched', 'A1:H8'],
  ['Classified_Evidence', 'A1:H8'], ['Unresolvable', 'A1:H8'],
  ['Needs_Review', null], ['Data_Quality', null],
]) {
  const png = await workbook.render({ sheetName, ...(range ? { range } : { autoCrop: 'all' }), format: 'png' });
  await fs.writeFile(path.join(root, 'previews', `${sheetName}.png`), new Uint8Array(await png.arrayBuffer()));
  console.log(`Rendered ${sheetName}`);
}
