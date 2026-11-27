import * as THREE from 'three';
// Architectural set dressing is procedural; editorial data stays in studio.js.
export function buildStudioSet(scene){
 const gold=new THREE.MeshStandardMaterial({color:'#b59a66',metalness:.82,roughness:.27});
 const graphite=new THREE.MeshStandardMaterial({color:'#101d30',metalness:.65,roughness:.25});
 const light=c=>new THREE.MeshBasicMaterial({color:c});
 const mesh=(geometry,mat,x=0,y=0,z=0)=>{const m=new THREE.Mesh(geometry,mat);m.position.set(x,y,z);scene.add(m);return m};
 const tube=(points,r,mat)=>mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p))),120,r,8,false),mat);
 const arc=(radius,y,z=3.5)=>Array.from({length:81},(_,i)=>{const a=-1.42+i/80*2.84;return [Math.sin(a)*radius,y,-Math.cos(a)*radius+z]});
 const ring=(radius,y,color,width=.025,z=0)=>{const m=mesh(new THREE.TorusGeometry(radius,width,8,128),light(color),0,y,z);m.rotation.x=Math.PI/2;return m};
 const canvasTexture=(kind)=>{const c=document.createElement('canvas');c.width=2048;c.height=512;const g=c.getContext('2d');const bg=g.createLinearGradient(0,0,0,512);bg.addColorStop(0,'#07152e');bg.addColorStop(1,'#102e50');g.fillStyle=bg;g.fillRect(0,0,2048,512);
 if(kind==='waves'){for(let j=0;j<38;j++){g.strokeStyle=j%2?'rgba(238,76,116,.62)':'rgba(66,199,255,.65)';g.lineWidth=1.3;g.beginPath();for(let x=0;x<=2048;x+=5){const y=240+Math.sin(x/135+j*.11)*70+Math.sin(x/300+j*.17)*50+j*2.6;x?g.lineTo(x,y):g.moveTo(x,y)}g.stroke()}g.fillStyle='#6ba9c755';for(let x=0;x<2048;x+=20)for(let y=20;y<512;y+=20)g.fillRect(x,y,1.5,1.5);}
 else {for(let i=0;i<140;i++){const x=i*15,h=35+(Math.sin(i*17.7)*.5+.5)*210;g.fillStyle=i%3?'#152a44':'#1b3a57';g.fillRect(x,470-h,13,h);for(let y=480-h;y<460;y+=13){g.fillStyle=i%4?'#92bfd0':'#e7bd80';g.fillRect(x+3,y,2,3);g.fillRect(x+9,y+3,2,3)}}g.fillStyle='#4187a4';g.fillRect(0,473,2048,2);}
 const t=new THREE.CanvasTexture(c);t.colorSpace=THREE.SRGBColorSpace;return t};
 const curved=(radius,bottom,height,texture)=>{const points=[],uv=[],indices=[],steps=120;for(let i=0;i<=steps;i++){const a=-1.42+i/steps*2.84;for(let j=0;j<2;j++){points.push(Math.sin(a)*radius,bottom+j*height,-Math.cos(a)*radius+3.5);uv.push(i/steps,j)}}for(let i=0;i<steps;i++){const n=i*2;indices.push(n,n+1,n+2,n+1,n+3,n+2)}const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(points,3));geometry.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));geometry.setIndex(indices);geometry.computeVertexNormals();mesh(geometry,new THREE.MeshBasicMaterial({map:texture,side:THREE.DoubleSide}));};
 curved(15,.25,8.5,canvasTexture('waves'));curved(14.95,8.9,2.2,canvasTexture('city'));
 for(const y of [.25,8.8,11.2]){tube(arc(14.8,y),.13,gold);tube(arc(14.65,y-.19),.025,light('#bce7ff'))}
 for(const side of [-1,1])for(const offset of [0,.42])tube([[side*11,0,0],[side*9.4,.4,-2],[side*8.2,2,-5],[side*7,5,-8],[side*6,8.3,-10],[side*4.9,9.1,-10.6]].map(([x,y,z])=>[x+side*offset,y,z]),.16,gold);
 const floor=mesh(new THREE.CylinderGeometry(19,19,.22,128),graphite,0,-.34,0);floor.receiveShadow=true;
 mesh(new THREE.CylinderGeometry(6.4,6.7,.28,128),new THREE.MeshStandardMaterial({color:'#1b2b40',metalness:.7,roughness:.24}),0,-.08,-.6);
 ring(6.42,.08,'#c4b184',.035,-.6);ring(5.85,.075,'#557f9c',.015,-.6);
 for(const radius of [2.4,2.6,3,3.2])ring(radius,-.21,radius<2.8?'#51bddb':'#cf536c',.025,8);
 for(const x of [-3.6,3.6])tube([[x,-.20,13],[x,-.20,6.7],[x*1.5,-.20,4.5]],.026,light('#61b8d9'));
 for(const radius of [8.5,10,12.5]){ring(radius,11.5,'#172639',.12,-1);ring(radius-.16,11.39,'#e7dbc1',.027,-1)}
 for(let i=0;i<8;i++){const a=i/8*Math.PI*2,x=Math.sin(a)*9,z=Math.cos(a)*9-1;const housing=mesh(new THREE.BoxGeometry(.6,.25,.75),graphite,x,11.2,z);const lamp=mesh(new THREE.PlaneGeometry(.43,.5),light('#e1f3ff'),x,11.05,z);lamp.rotation.x=Math.PI/2;if(i%2===0){const spot=new THREE.SpotLight('#c6e5ff',100,30,.5,.8,1);spot.position.set(x,10.9,z);spot.target.position.set(x*.2,0,-1);scene.add(spot,spot.target)}}
 // Camera silhouettes and a crane establish the scale without covering the data wall.
 for(const side of [-1,1]){const x=side*9;mesh(new THREE.CylinderGeometry(.5,.65,.22,20),graphite,x,-.12,3);mesh(new THREE.CylinderGeometry(.09,.15,1.8,12),graphite,x,.8,3);const body=mesh(new THREE.BoxGeometry(.65,.45,1),graphite,x,1.9,3);const lens=mesh(new THREE.CylinderGeometry(.17,.2,.35,16),graphite,x,1.9,2.35);lens.rotation.x=Math.PI/2;}
 tube([[10.5,1.7,3],[10.5,4.3,3],[10,5.8,0],[9.5,6.4,-3]],.075,graphite);
 // Gold edged anchor desk.
 mesh(new THREE.BoxGeometry(5,.2,1.5),gold,1.6,1.55,.3);mesh(new THREE.BoxGeometry(4.5,1.3,1.1),graphite,1.6,.8,.3);mesh(new THREE.BoxGeometry(4.1,.035,.025),light('#6fd4e3'),1.6,1.22,.87);
}
