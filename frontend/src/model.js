export const articleStatuses={DRAFT:'초안',PENDING_HUMAN:'승인 대기',REVIEW_REQUIRED:'검토 필요',APPROVED:'승인 완료'};
export const number=value=>value===null||value===undefined?'미제공':Number(value).toLocaleString('ko-KR');
export const percent=value=>value===null||value===undefined?'미제공':Number(value).toFixed(2)+'%';
export function commonValue(rows,key){const values=rows.map(row=>row[key]);return values.length&&values.every(value=>value!==null&&value!==undefined&&value===values[0])?values[0]:null}
export function regionSummary(snapshot,region){const rows=(snapshot?.rows||[]).filter(row=>row.region_name===region);return {rows:[...rows].sort((a,b)=>(b.votes??-1)-(a.votes??-1)),votes:rows.length&&rows.every(r=>r.votes!==null&&r.votes!==undefined)?rows.reduce((total,row)=>total+row.votes,0):null,countRate:commonValue(rows,'count_rate'),turnout:commonValue(rows,'turnout'),baseline:commonValue(rows,'baseline_at')}}
export function sourceLink(value){try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)?url.href:null}catch{return null}}
export function timeText(value){if(!value)return '미제공';const time=new Date(value);return Number.isNaN(time.valueOf())?'미제공':time.toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false})}

export function replayPoint(rows,elapsedSeconds){
 if(!rows.length||rows.some(row=>!Number.isSafeInteger(row.votes)||row.votes<0))return null;
 const seconds=Math.max(0,Math.min(3600,Number.isFinite(elapsedSeconds)?elapsedSeconds:0));
 const candidates=rows.map(row=>({candidate_id:row.candidate_id,candidate_name:row.candidate_name,votes:Math.floor(row.votes*seconds/3600)}));
 return {seconds,minute:seconds/60,countRate:seconds/3600*100,total:candidates.reduce((sum,row)=>sum+row.votes,0),candidates};
}
export function oneHourSeries(rows){return Array.from({length:61},(_,minute)=>replayPoint(rows,minute*60)).filter(Boolean)}
