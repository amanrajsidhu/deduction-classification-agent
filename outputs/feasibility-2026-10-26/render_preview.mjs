import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const require = createRequire(path.join(process.argv[2], '_anchor.cjs'));
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const root = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1'));
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(root, 'baseline/deduction_resolution_workbench_v2.xlsx')));
await fs.mkdir(path.join(root, 'previews'), { recursive: true });
for (const [sheetName, range] of [
  ['Start_Here', 'A1:H44'], ['Priority_Worklist', 'A1:F12'], ['Auto_Matched', 'A1:H9'],
  ['Classified_Evidence', 'A1:H9'], ['Needs_Review', 'A1:C5'], ['Unresolvable', 'A1:H9'],
  ['Data_Quality', 'A1:C5'], ['Evaluation', 'A1:D38'],
]) {
  const png = await workbook.render({ sheetName, range, scale: 1, format: 'png' });
  await fs.writeFile(path.join(root, 'previews', `${sheetName}.png`), new Uint8Array(await png.arrayBuffer()));
  console.log(`Rendered ${sheetName}`);
}
