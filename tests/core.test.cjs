const {test}=require('node:test');
const assert=require('node:assert/strict');
const {haversine,nearest,filter}=require('../public/core.js');
test('Haversine: identical points, one equatorial degree and antipodes',()=>{
 assert.equal(haversine({lat:20,lon:-99},{lat:20,lon:-99}),0);
 assert.ok(Math.abs(haversine({lat:0,lon:0},{lat:0,lon:1})-111.195)<0.001);
 assert.ok(Math.abs(haversine({lat:0,lon:0},{lat:0,lon:180})-20015.114)<0.01);
});
test('nearest uses entire dataset, limits to ten and preserves source order',()=>{
 const rows=Array.from({length:15},(_,i)=>({id:String(i),lat:0,lon:15-i}));
 const result=nearest(rows,{lat:0,lon:0});
 assert.equal(result.length,10); assert.equal(result[0].id,'14');assert.equal(rows[0].id,'0');
 assert.equal(nearest([],{lat:0,lon:0}).length,0);
});
test('combined filters: multi-sport, missing municipalities and accented names',()=>{
 const rows=[{id:'1',name:'Cancha Águila',state:'Jalisco',municipality:'',city:'',sport:'soccer;basketball',type:'pitch'},
 {id:'2',name:'Águila',state:'Jalisco',municipality:'Zapopan',city:'',sport:'tennis',type:'pitch'}];
 assert.deepEqual(filter(rows,{state:'Jalisco',sport:'basketball',municipality:'__missing',name:'aguila'}).map(r=>r.id),['1']);
 assert.equal(filter(rows,{sport:'swimming'}).length,0);
});
