// One shared queue across the drawing and singing modules in this DSH host.
const KEY=Symbol.for('dsh.localGpuQueue.v1');
export function withLocalGpu(run,signal){
  const queue=globalThis[KEY]??=( {tail:Promise.resolve()} );
  const task=queue.tail.then(()=>{signal?.throwIfAborted();return run();});
  queue.tail=task.catch(()=>{});
  return task;
}
