// Fictional candidate colors stay tied to identity when vote rankings change.
export function candidateColor(candidate,index=0){
 const colors={'서지도':'#4169E1','한반도':'#DC143C','박리본':'#009B77'};
 return candidate.is_demo&&colors[candidate.candidate_name]||['#087e8b','#3f73ae','#967d43','#79659b'][index%4];
}
