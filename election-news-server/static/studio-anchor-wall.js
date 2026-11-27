import * as THREE from 'three';
export function addAnchorWall(scene){
 const group=new THREE.Group();group.position.set(-9.45,4.6,-3.5);group.rotation.y=.5;scene.add(group);
 const plate=(w,h,z,material)=>{const m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),material);m.position.z=z;group.add(m);return m};
 plate(3.9,6.3,0,new THREE.MeshBasicMaterial({color:'#43718b',side:THREE.DoubleSide}));
 plate(3.68,6.08,.015,new THREE.MeshBasicMaterial({color:'#071a2e'}));
 const portrait=plate(3.35,4.42,.04,new THREE.MeshBasicMaterial({transparent:true,alphaTest:.03}));portrait.position.y=.13;portrait.visible=false;
 const caption=document.createElement('canvas');caption.width=768;caption.height=128;const ctx=caption.getContext('2d');ctx.fillStyle='#0d354a';ctx.fillRect(0,0,768,128);ctx.font='bold 42px "Malgun Gothic", sans-serif';ctx.fillStyle='#deeff8';ctx.textAlign='center';ctx.fillText('VIRTUAL ANCHOR',384,55);ctx.font='28px "Malgun Gothic", sans-serif';ctx.fillStyle='#8edbd7';ctx.fillText('AI 앵커 · 정지 이미지',384,103);const labelTexture=new THREE.CanvasTexture(caption);labelTexture.colorSpace=THREE.SRGBColorSpace;
 const label=plate(3.5,.58,.05,new THREE.MeshBasicMaterial({map:labelTexture}));label.position.y=-2.65;
 const toggle=document.getElementById('anchorWallVisible');toggle.onchange=()=>{group.visible=toggle.checked};
 new THREE.TextureLoader().load('/static/assets/anchor-newsroom.png',texture=>{texture.colorSpace=THREE.SRGBColorSpace;portrait.material.map=texture;portrait.material.needsUpdate=true;portrait.visible=true;},undefined,()=>{document.getElementById('anchorWallStatus').textContent='앵커 이미지를 불러오지 못했습니다. 새로고침해 주세요.';});
 return group;
}
