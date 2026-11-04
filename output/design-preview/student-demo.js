/* Synthetic preview only. Production ranking lives in market/recommendations.py. */
(() => {
  'use strict';
  const key='boxbox-market-demo-v1',signalKey='boxbox-student-demo-v1';
  const norm=s=>(s||'').normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
  const includes=(a,b)=>Boolean(norm(b))&&norm(a).includes(norm(b));
  const copy=JSON.parse(document.getElementById('student-copy').textContent);
  const read=(k,fallback)=>{try{return JSON.parse(sessionStorage.getItem(k))||fallback;}catch{return fallback;}};
  const account=()=>read(key,{});
  let signals=read(signalKey,{seen:[],dismissed:[],searches:[],joined:['study']});
  function save(){try{sessionStorage.setItem(signalKey,JSON.stringify(signals));}catch{}}
  const el=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
  window.BoxStudentDemo={
    rank(cards,form){
      const member=account(),major=member.signedIn?member.profile?.major:'',searches=member.signedIn?signals.searches:[];
      const ranked=cards.map((card,index)=>{
        let total=5,score=5;
        if(major){total+=20;if(norm(card.dataset.major)===norm(major)||includes(card.dataset.search,major))score+=20;}
        if(searches.length){total+=10;score+=10*searches.filter(s=>includes(card.dataset.search,s)).length/searches.length;}
        const interests=member.signedIn?signals.joined:[];
        if(interests.length){total+=30;if(interests.includes(card.dataset.kind))score+=30;}
        score/=total;
        if(member.signedIn&&signals.seen.includes(card.dataset.studentId))score-=.12;
        if(member.signedIn&&signals.dismissed.includes(card.dataset.studentId))score-=2;
        return {card,score,index};
      });
      if(form.elements.sort?.value==='time')ranked.sort((a,b)=>Date.parse(a.card.dataset.start)-Date.parse(b.card.dataset.start)||a.index-b.index);
      else ranked.sort((a,b)=>(a.card.dataset.state!=='open')-(b.card.dataset.state!=='open')||b.score-a.score||a.index-b.index);
      const parent=cards[0]?.parentElement;if(parent)ranked.forEach(r=>parent.append(r.card));
      const people=document.querySelector('[data-student-people]');if(!people)return;
      people.replaceChildren();const term=form.elements.major?.value||form.elements.q?.value;
      if(!member.signedIn||!term)return;
      const matches=cards.filter(c=>includes(c.dataset.major,term)&&c.dataset.person!=='Demo');
      if(!matches.length)return;people.className='panel student-people';people.append(el('h3',copy.people),el('p',copy.sample));
      for(const card of matches){const a=el('a',card.dataset.person+' · '+card.dataset.major);a.href=card.href;a.className='list-row';people.append(a);}
    },
    match:includes
  };
  document.addEventListener('DOMContentLoaded',()=>{
    const post=document.body.dataset.studentPost,member=account();
    if(post&&member.signedIn){signals.seen=[post,...signals.seen.filter(x=>x!==post)].slice(0,100);save();}
    const button=document.querySelector('[data-student-dismiss]');
    if(button){button.textContent=signals.dismissed.includes(post)?copy.restore:copy.dismiss;button.addEventListener('click',()=>{
      const status=document.querySelector('[data-student-feedback]');if(!account().signedIn){status.textContent=copy.login;return;}
      const dismissed=signals.dismissed.includes(post);signals.dismissed=dismissed?signals.dismissed.filter(x=>x!==post):[post,...signals.dismissed].slice(0,100);save();button.textContent=dismissed?copy.dismiss:copy.restore;status.textContent=dismissed?copy.restored:copy.saved;
    });}
    const form=document.querySelector('[data-filter=buddy]');if(form)form.requestSubmit();
  });
  document.addEventListener('submit',e=>{
    if(!e.target.matches('[data-filter=buddy]')||!account().signedIn)return;
    const term=e.target.elements.q.value.trim()||e.target.elements.major.value.trim();
    if(term){signals.searches=[term,...signals.searches.filter(x=>x!==term)].slice(0,10);save();}
  },true);
})();
