export function formatCatalog(catalog,{failure=false}={}){
  const items=catalog?.items||[];
  if(!items.length){
    if(catalog?.total>0)return '这一页没有歌曲了，可以从歌单第一页重新选。';
    return failure?'这首现在没唱成，暂时也没有可播放的缓存歌曲。':'暂时没有可播放的缓存歌曲。';
  }
  const rows=items.map(x=>`${x.number}. 《${String(x.song).replace(/[\r\n]/g,' ').slice(0,64)}》— ${String(x.artist).replace(/[\r\n]/g,' ').slice(0,32)}（${x.segment}，${Math.round(x.seconds)}秒${x.voice==='当前音色'?'':'，以前保存的音色'}）`);
  return [failure?'这首现在没唱成，可以先选这些已经唱好的：':'这些已经唱好，可以直接播放：',...rows,`回复“播放第几首”或歌名就行${catalog.nextOffset!==null?'；回复“更多缓存歌曲”看下一页':''}。`].join('\n');
}
export function catalogSegments(text){
  const chunks=[];let current='';
  for(const line of text.split('\n')){if(current.length+line.length+1>480){chunks.push(current);current=''}current+=(current?'\n':'')+line}
  if(current)chunks.push(current);if(chunks.length>9)throw Error('歌单过长，请分页查看');return chunks;
}
