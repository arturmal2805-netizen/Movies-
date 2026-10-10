// Deterministic balanced logistic regression with L2; mirrors scripts/taste_model.py.
export const tasteModelVersion='empirical-taste32';
const scales={genre:1,category:.5,keyword:1,director:1,language:.5,period:.5};
export const marginFeatures=vector=>vector.map(([key,value,kind])=>[key,value*scales[kind],kind]);
export function fitMargin(examples,iterations=240){
 const support=new Map();for(const [vector] of examples)for(const [key] of vector)support.set(key,(support.get(key)||0)+1);
 const keys=[...support].filter(([,n])=>n>=3).map(([key])=>key).sort(),index=new Map(keys.map((key,i)=>[key,i]));
 const positive=examples.filter(([,label])=>label).length,negative=examples.length-positive;
 if(!positive||!negative)return {weights:new Map(),bias:0};
 const rows=examples.map(([vector,label])=>[vector.filter(([key])=>index.has(key)).map(([key,value])=>[index.get(key),value]),label,.5/(label?positive:negative)]);
 const ridge=1/rows.length,rate=1/(.25*Math.max(...rows.map(([v])=>1+v.reduce((s,[,x])=>s+x*x,0)))+ridge);
 let weights=new Float64Array(keys.length+1),look=weights.slice(),momentum=1;
 for(let step=0;step<iterations;step++){
  const gradient=Float64Array.from(look,w=>ridge*w);
  for(const [vector,label,mass] of rows){let z=look[keys.length];for(const [i,value] of vector)z+=look[i]*value;const error=(1/(1+Math.exp(-Math.max(-35,Math.min(35,z))))-Number(label))*mass;gradient[keys.length]+=error;for(const [i,value] of vector)gradient[i]+=error*value;}
  const updated=Float64Array.from(look,(w,i)=>w-rate*gradient[i]),next=(1+Math.sqrt(1+4*momentum*momentum))/2;
  look=Float64Array.from(updated,(v,i)=>v+(momentum-1)/next*(v-weights[i]));weights=updated;momentum=next;
 }
 return {weights:new Map(keys.map((key,i)=>[key,weights[i]])),bias:weights[keys.length]};
}
