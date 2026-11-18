(function(root){
  const radians = n => n * Math.PI / 180;
  function haversine(a,b){const dlat=radians(b.lat-a.lat),dlon=radians(b.lon-a.lon);const h=Math.sin(dlat/2)**2+Math.cos(radians(a.lat))*Math.cos(radians(b.lat))*Math.sin(dlon/2)**2;return 6371.0088*2*Math.asin(Math.sqrt(Math.min(1,Math.max(0,h))));}
  function sports(row){return row.sport ? row.sport.split(';').map(s=>s.trim()).filter(Boolean) : [''];}
  function nearest(rows,point,limit=10){return rows.map(r=>({...r,distance:haversine(point,r)})).sort((a,b)=>a.distance-b.distance||a.id.localeCompare(b.id)).slice(0,limit);}
  function fold(s){return s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();}
  function filter(rows,f){return rows.filter(r=>['state','municipality','city','type'].every(k=>!f[k]||(f[k]==='__missing'?!r[k]:r[k]===f[k]))&&(!f.sport||(f.sport==='__missing'?!r.sport:sports(r).includes(f.sport)))&&(!f.name||fold(r.name).includes(fold(f.name))));}
  const api={haversine,sports,nearest,fold,filter};if(typeof module!=='undefined')module.exports=api;else root.Atlas=api;
})(globalThis);
