import {mkdtempSync, rmSync, realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, dirname, basename} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const temp = mkdtempSync(join(tmpdir(), 'dsh-singing-test-'));
try {
  for (const file of ['adapter.mjs', 'position-adapter.mjs']) {
    const result = spawnSync(process.execPath, [join(root, 'tests', file)], {
      cwd: root, stdio: 'inherit', windowsHide: true,
      env: {...process.env, DSH_SINGING_ROOT: temp, DSH_HOME: temp, DSH_QQ_WORKSPACE: 'C:/dsh-test-workspace'},
    });
    if (result.error) throw result.error;
    if (result.status !== 0) process.exitCode = result.status || 1;
  }
} finally {
  const resolved = realpathSync(temp);
  if (dirname(resolved).toLowerCase() !== realpathSync(tmpdir()).toLowerCase() || !basename(resolved).startsWith('dsh-singing-test-')) {
    throw new Error('Temporary cleanup target is outside the expected directory');
  }
  rmSync(temp, {recursive: true, force: true});
}
