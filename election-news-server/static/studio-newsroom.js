import * as THREE from 'three';
// Static anchor portrait and geometric newsroom props; no lip-sync or avatar animation.
export function addNewsroom(scene){
 const metal=new THREE.MeshStandardMaterial({color:'#c6d4e1',metalness:.7,roughness:.25});
 const navy=new THREE.MeshStandardMaterial({color:'#112b42',metalness:.35,roughness:.4});
 const basic=c=>new THREE.MeshBasicMaterial({color:c});
 const add=(geometry,material,x,y,z)=>{const m=new THREE.Mesh(geometry,material);m.position.set(x,y,z);scene.add(m);return m};
 const cube=(w,h,d,x,y,z,mat)=>add(new THREE.BoxGeometry(w,h,d),mat,x,y,z);
 const glass=new THREE.MeshPhysicalMaterial({color:'#b9e1ed',metalness:.1,roughness:.12,transparent:true,opacity:.38,depthWrite:false,side:THREE.DoubleSide});
 const desktop=add(new THREE.CylinderGeometry(1,1,.12,96),glass,-2.6,1.65,3.1);desktop.scale.set(2.8,1,1.3);
 const rim=add(new THREE.TorusGeometry(1,.018,8,96),metal,-2.6,1.65,3.1);rim.rotation.x=Math.PI/2;rim.scale.set(2.8,1.3,1);
 const base=add(new THREE.CylinderGeometry(.75,1,.95,48),navy,-2.6,.9,3.1);base.scale.x=2.1;
 cube(3.9,.06,.06,-2.6,1.32,4.2,basic('#56c4d6'));
 // Paper and tablet are separate physical desk props.
 cube(.9,.015,.6,-3.2,1.73,3.25,basic('#d9e5ec'));
 const tablet=cube(.75,.035,.55,-2.05,1.74,3.2,metal);cube(.68,.012,.48,-2.05,1.765,3.2,basic('#142a42'));
 // Workstations and blue monitor walls evoke an operating newsroom.
 for(const x of [-9,-7])for(const z of [-4,-1]){cube(1.6,.12,.85,x,1.1,z,navy);cube(.12,.9,.12,x,.55,z,metal);cube(1.15,.7,.07,x,1.6,z-.25,navy);cube(1.02,.55,.02,x,1.6,z-.20,basic('#226b94'));cube(.08,.25,.08,x,1.15,z-.25,metal);}
 for(let i=0;i<4;i++){const x=-9.3+i*.9;cube(.8,.52,.08,x,4.8,-6.5,navy);cube(.71,.42,.02,x,4.8,-6.44,basic(i%2?'#175379':'#3c839e'));}
 for(const y of [8.9,9.2])cube(21,.1,.15,0,y,-6.4,basic(y===8.9?'#c5e8fa':'#276a99'));
 const portrait=new THREE.Mesh(new THREE.PlaneGeometry(3.35,4.6),new THREE.MeshBasicMaterial({transparent:true,alphaTest:.03,side:THREE.DoubleSide}));
 portrait.position.set(-2.6,3.92,2.4);portrait.visible=false;scene.add(portrait);
 new THREE.TextureLoader().load('/static/assets/anchor-newsroom.png',texture=>{texture.colorSpace=THREE.SRGBColorSpace;portrait.material.map=texture;portrait.material.needsUpdate=true;portrait.visible=document.getElementById('anchorVisible').checked;},undefined,()=>{document.getElementById('anchorStatus').textContent='앵커 이미지를 불러오지 못했습니다. 다시 새로고침해 주세요.';});
 return portrait;
}
