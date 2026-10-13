// Deterministic balanced logistic regression with L2; mirrors scripts/taste_model.py.
export const tasteModelVersion='duration-aware42';
const scales={genre:1,category:.5,keyword:1,director:1,language:.5,period:.5,quality:.5,reach:.5,runtime:.5};
export const marginFeatures=vector=>vector.map(([key,value,kind])=>[key,value*scales[kind],kind]);
export function fitMargin(examples,iterations=240,regularization=1){
 const support=new Map();for(const [vector] of examples)for(const [key] of vector)support.set(key,(support.get(key)||0)+1);
 const keys=[...support].filter(([,n])=>n>=3).map(([key])=>key).sort(),index=new Map(keys.map((key,i)=>[key,i]));
 const positive=examples.filter(([,label])=>label).length,negative=examples.length-positive;
 if(!positive||!negative)return {weights:new Map(),bias:0};
 // Flatten sparse vectors once. Typed CSR removes nested array iteration and
 // per-value destructuring from the hot training loop without changing loss.
 const offsets=new Int32Array(examples.length+1),labels=new Float64Array(examples.length),masses=new Float64Array(examples.length),columnList=[],valueList=[];
 let maxNorm=1;
 for(let row=0;row<examples.length;row++){
  const [vector,label]=examples[row];let norm=1;
  for(const [key,value] of vector)if(index.has(key)){columnList.push(index.get(key));valueList.push(value);norm+=value*value;}
  offsets[row+1]=columnList.length;labels[row]=Number(label);masses[row]=.5/(label?positive:negative);maxNorm=Math.max(maxNorm,norm);
 }
 const columns=Int32Array.from(columnList),values=Float64Array.from(valueList);
 const ridge=1/(regularization*examples.length),rate=1/(.25*maxNorm+ridge);
 let weights=new Float64Array(keys.length+1),look=weights.slice(),momentum=1;
 for(let step=0;step<iterations;step++){
  const gradient=new Float64Array(look.length);
  for(let i=0;i<look.length;i++)gradient[i]=ridge*look[i];
  for(let row=0;row<examples.length;row++){
   let z=look[keys.length];
   for(let k=offsets[row];k<offsets[row+1];k++)z+=look[columns[k]]*values[k];
   const error=(1/(1+Math.exp(-Math.max(-35,Math.min(35,z))))-labels[row])*masses[row];gradient[keys.length]+=error;
   for(let k=offsets[row];k<offsets[row+1];k++)gradient[columns[k]]+=error*values[k];
  }
  const updated=new Float64Array(look.length),next=(1+Math.sqrt(1+4*momentum*momentum))/2;
  for(let i=0;i<look.length;i++)updated[i]=look[i]-rate*gradient[i];
  const ahead=new Float64Array(updated.length);
  for(let i=0;i<ahead.length;i++)ahead[i]=updated[i]+(momentum-1)/next*(updated[i]-weights[i]);
  look=ahead;weights=updated;momentum=next;
 }
 return {weights:new Map(keys.map((key,i)=>[key,weights[i]])),bias:weights[keys.length]};
}
