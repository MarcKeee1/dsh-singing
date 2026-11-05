// Reuse the established local GPU queue when another DSH plugin shares it.
const KEY=Symbol.for('dsh.localGpuQueue.v1');
export function withLocalGpu(run,signal){
  const queue=globalThis[KEY]??={tail:Promise.resolve()};
  const task=queue.tail.then(()=>{signal?.throwIfAborted();return run()});
  queue.tail=task.catch(()=>{});
  if(!signal)return task;
  return new Promise((resolve,reject)=>{
    const abort=()=>reject(signal.reason||Error('唱歌已取消'));
    signal.addEventListener('abort',abort,{once:true});
    if(signal.aborted)abort();
    task.then(resolve,reject).finally(()=>signal.removeEventListener('abort',abort));
  });
}
