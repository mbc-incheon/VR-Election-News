/* Safe links carry article context; server authentication and approval checks remain authoritative. */
(function(root){
 function url(destination,{article,mode,region}={}){const params=new URLSearchParams();if(['demo','official'].includes(mode))params.set('mode',mode);if(region)params.set('region',region);if(/^[a-f0-9]{16}$/.test(article||''))params.set('article',article);if(destination==='production')params.set('production','1');return (destination==='studio'?'/studio':'/')+'?'+params+(destination==='production'?'#production':'');}
 root.NewsroomLinks={url};
})(globalThis);
