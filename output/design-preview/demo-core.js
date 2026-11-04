/* Pure rules shared by the browser-only demo and its focused tests. */
(function(root){
  'use strict';
  function canSeeContacts(messages){
    const valid=messages.filter(m=>m && (m.sender==='me'||m.sender==='peer') && typeof m.text==='string' && m.text.trim());
    return valid.length>=4 && valid.some(m=>m.sender==='me') && valid.some(m=>m.sender==='peer');
  }
  function defaults(now=new Date()){
    const p=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Hong_Kong',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now).map(v=>[v.type,v.value]));
    const date=`${p.year}-${p.month}-${p.day}`, time=`${p.hour}:${p.minute}`;
    const until=new Date(Date.UTC(+p.year,+p.month-1,+p.day+7)).toISOString().slice(0,10);
    return {start:date+'T'+time,end:until+'T'+time,deposit:0,location:'CityUHK campus',maxDays:7};
  }
  function deriveTitle(description){return String(description||'').trim().split(/[\n。！？.!?]/)[0].trim().slice(0,100)||String(description||'').trim().slice(0,100);}
  function rentalQuote(start,end,price,deposit=0){
    const from=Date.parse(start+'+08:00'),to=Date.parse(end+'+08:00');
    if(!Number.isFinite(from)||!Number.isFinite(to)||to<=from||!Number.isFinite(+price)||+price<0||!Number.isFinite(+deposit)||+deposit<0)return null;
    const days=Math.ceil((to-from)/86400000);return {days,rent:Math.round(days*Number(price)*100)/100,deposit:Number(deposit)};
  }
  function readPayload(hash){
    try{const params=new URLSearchParams(hash.replace(/^#/,''));const raw=params.get('listing');if(!raw||raw.length>12000)return null;const d=JSON.parse(raw);
      if(!d||!['rent','sale','borrow','buy'].includes(d.intent)||typeof d.description!=='string'||!d.description.trim()||d.description.length>2000||!Number.isFinite(Number(d.amount))||Number(d.amount)<0)return null;
      return {id:String(d.id||'shared').slice(0,80),ownerKey:String(d.ownerKey||'shared').slice(0,80),peer:String(d.peer||'Demo publisher').slice(0,40),intent:d.intent,title:(String(d.title||'').trim()||deriveTitle(d.description)).slice(0,100),description:d.description,condition:String(d.condition||'').slice(0,200),amount:Number(d.amount),category:['tech','study','outdoor','home','creative','other'].includes(d.category)?d.category:'other',location:String(d.location||'CityUHK campus').slice(0,160),start:String(d.start||''),end:String(d.end||''),deposit:Math.max(0,Number(d.deposit)||0),maxDays:Math.max(1,Number(d.maxDays)||7)};
    }catch{return null;}
  }
  const api={canSeeContacts,defaults,deriveTitle,rentalQuote,readPayload};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.BoxDemoCore=api;
})(typeof window==='undefined'?{}:window);
