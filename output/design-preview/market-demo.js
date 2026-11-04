/* Sandbox interactions only. All state stays in this tab's sessionStorage.
   No authentication, messages, contacts, orders or listings are sent to a server. */
(() => {
  'use strict';
  const Core=window.BoxDemoCore,lang=document.body.dataset.language||'hans';
  const copy=JSON.parse(document.getElementById('market-copy').textContent), C=k=>copy[k]||k;
  const L=(hans,english)=>lang==='en'?english:lang==='zh'?(copy._traditional[hans]||hans):hans;
  const key='boxbox-market-demo-v1';
  const uid=()=>crypto.randomUUID();
  const fresh=()=>({version:1,tabKey:uid(),signedIn:false,drafts:{},orders:[],messages:{},threads:{},blocks:{},profile:{},photos:{}});
  let state;
  try{state=JSON.parse(sessionStorage.getItem(key));if(!state||state.version!==1)state=fresh();}catch{state=fresh();}
  state.threads||={};state.blocks||={};
  let currentItem=null,photoData='',savedState=JSON.stringify(state);
  window.BoxDemoAccess={requireLogin,isSignedIn:()=>state.signedIn};
  function save(){try{const next=JSON.stringify(state);sessionStorage.setItem(key,next);savedState=next;return true;}catch{state=JSON.parse(savedState);toast(C('storageError'));return false;}}
  const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  const button=(text,action,cls='button')=>{const n=node('button',cls,text);n.type='button';n.addEventListener('click',action);return n;};
  function link(text,href,cls='button secondary'){const a=node('a',cls,text);a.href=href;return a;}
  const money=n=>'HK$ '+Number(n).toLocaleString('en-HK',{maximumFractionDigits:2});
  const localPath=route=>'/'+lang+'/'+route;
  function toast(message){let n=document.querySelector('#market-toast');if(!n){n=node('div','market-toast');n.id='market-toast';n.setAttribute('role','status');document.body.append(n);}n.textContent=message;n.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>{n.hidden=true;},4500);}
  function dialog(title){
    const old=document.querySelector('#market-dialog');
    const opener=old?.contains(document.activeElement)?old.marketOpener:document.activeElement;
    if(old){if(old.open)old.close();old.remove();}
    const d=node('dialog','market-dialog');d.id='market-dialog';d.setAttribute('aria-labelledby','market-dialog-title');
    d.marketOpener=opener;
    const header=node('div','market-dialog-heading');const h=node('h2','',title);h.id='market-dialog-title';header.append(h,button(C('close'),()=>d.close(),'dialog-close'));
    d.append(header);document.body.append(d);
    d.addEventListener('close',()=>{
      // A replaced dialog must not steal focus from its successor or cancel a new login action.
      if(!d.isConnected)return;
      d.remove();
      if(!document.querySelector('dialog[open]')&&opener?.isConnected)opener.focus({preventScroll:true});
    },{once:true});
    d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}});
    return d;
  }
  function requireLogin(action){
    if(state.signedIn){action();return;}
    const d=dialog(C('loginTitle'));d.classList.add('login-dialog');d.append(node('p','',C('loginBody')));let pending=action;
    const actions=node('div','dialog-actions');actions.append(button(C('cancel'),()=>d.close(),'button secondary'),button(C('continue'),()=>{
      if(!pending)return;state.signedIn=true;if(!save())return;const continuation=pending;pending=null;d.close();syncIdentity();mountProfile();mountChat();continuation();
    }));d.append(actions);d.showModal();
  }
  function syncIdentity(){
    document.dispatchEvent(new Event('market:identity'));
    document.querySelectorAll('[data-demo-identity]').forEach(n=>n.textContent=C(state.signedIn?'member':'guest'));
    document.querySelectorAll('[data-market-auth]').forEach(n=>n.textContent=C(state.signedIn?'logout':'login'));
    document.querySelectorAll('.header-actions > .avatar').forEach(a=>{a.textContent=state.signedIn?'D':'↪';a.setAttribute('aria-label',C(state.signedIn?'member':'login'));});
  }
  function payloadLink(d,wanted=false){
    const share={...d};delete share.photo;
    return localPath((wanted?'wanted':'items')+'/demo/')+'#'+new URLSearchParams({listing:JSON.stringify(share)}).toString();
  }
  function sampleSale(){return {id:'sale-example',ownerKey:'member-2',intent:'sale',title:C('saleTitle'),description:C('saleDescription'),amount:80,category:'study',location:'CityUHK campus',...Core.defaults()};}
  function sampleBuy(){return {id:'buy-example',ownerKey:'member-2',intent:'buy',title:C('buyTitle'),description:C('buyDescription'),amount:100,category:'study',location:'CityUHK campus',...Core.defaults()};}
  function threadURL(item){
    const context={key:'listing-'+item.id,title:item.title,href:item.href||payloadLink(item,['borrow','buy'].includes(item.intent)),type:item.intent,peer:item.peer||'Jamie'};
    return localPath('messages/demo/')+'#'+new URLSearchParams({context:JSON.stringify(context)}).toString();
  }
  function readContext(){try{const c=JSON.parse(new URLSearchParams(location.hash.slice(1)).get('context'));if(c&&typeof c.key==='string'&&/^listing-[a-zA-Z0-9_-]{1,100}$/.test(c.key)&&typeof c.title==='string'&&c.title.length<=100){const url=new URL(c.href,location.origin);if(url.origin===location.origin&&/^\/(en|zh|hans)\/(items|wanted)\//.test(url.pathname))return {...c,href:url.pathname.replace(/^\/(en|zh|hans)\//,'/'+lang+'/')+url.search+url.hash,peer:String(c.peer||'Jamie').slice(0,40)};}}catch{}return null;}
  function shareItem(href,title){
    const url=new URL(href,location.origin).href;
    const d=dialog(C('share'));d.append(node('p','',C('shareHelp')));
    const field=node('input','share-url');field.readOnly=true;field.value=url;field.setAttribute('aria-label',C('share'));d.append(field);
    const actions=node('div','share-options');
    const wa=link('WhatsApp','https://wa.me/?text='+encodeURIComponent((title||document.title)+'\n'+url));wa.target='_blank';wa.rel='noopener noreferrer';
    actions.append(wa,button(C('systemShare'),async()=>{if(!navigator.share){toast(C('shareFallback'));return;}try{await navigator.share({title:title||document.title,url});}catch(e){if(e.name!=='AbortError')toast(C('shareFallback'));}},'button secondary'),button(C('copy'),async()=>{try{await navigator.clipboard.writeText(url);toast(C('copied'));}catch{field.focus();field.select();toast(C('copyManual'));}},'button secondary'));
    d.append(actions,node('p','hint',C('shareNote')));const shared=Core.readPayload(new URL(url).hash);if(shared&&state.photos[shared.id])d.append(node('p','hint',L('本地照片不会随演示链接上传，其他人可查看文字和价格。','Local photos are not uploaded with demo links. Other viewers can see the text and price.')));d.showModal();
  }
  function makeShare(href,title){const b=button('',()=>shareItem(href,title),'item-share');b.setAttribute('aria-label',C('share'));const img=node('img','ui-icon');img.src='/preview-assets/icons/share-2.svg';img.alt='';b.append(img);return b;}
  function intentTabs(){
    const form=document.querySelector('.filter-form[data-filter]');if(!form)return;
    const selected=form.elements.namedItem('intent')?.value||'';
    document.querySelectorAll('[data-market-filter]').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.marketFilter===selected)));
    if(form.dataset.filter==='items'){
      const label=form.querySelector('.filter-price .filter-label');if(label)label.textContent=selected==='rent'?C('daily'):C('amountLimit');
      const price=form.elements.namedItem('price');if(price)price.setAttribute('aria-label',selected==='rent'?C('daily'):C('amountLimit'));
      let help=document.querySelector('.market-price-help');if(!help){help=node('p','market-price-help hint');form.after(help);}help.textContent=C('mixedPrice');
    }
  }
  function mountDraftCards(){
    const grid=document.querySelector('.item-grid'),wanted=document.querySelector('.wanted-list');
    document.querySelectorAll('[data-local-draft]').forEach(n=>n.remove());
    Object.values(state.drafts).forEach(d=>{
      const isWanted=['borrow','buy'].includes(d.intent),parent=isWanted?wanted:grid;if(!parent)return;
      const card=node(isWanted?'a':'article',isWanted?'wanted-tile':'item-tile no-photo shareable-item');
      card.dataset.localDraft=d.id;card.dataset.intent=d.intent;card.dataset.price=d.amount;card.dataset.category=d.category;card.dataset.search=d.title+' '+d.description;card.dataset.start=d.start+'+08:00';card.dataset.end=d.end+'+08:00';card.dataset.maxDays=d.maxDays;
      const href=payloadLink(d,isWanted);
      if(isWanted){card.href=href;const content=node('div','request-content');content.append(node('span','pill',C(d.intent==='buy'?'wantedBuy':'borrow')),node('h3','',d.title),node('p','request-description',d.description),node('p','request-facts',d.location));const budget=node('div','request-budget');budget.append(node('span','',C('budget')),node('strong','',money(d.amount)));card.append(content,budget);}
      else{const a=link('',href,'tile-link');const media=node('div','tile-media no-photo');if(state.photos[d.id]){const img=node('img');img.src=state.photos[d.id];img.alt=d.title;media.append(img);card.className='item-tile has-photo shareable-item';media.className='tile-media';}else media.append(node('span','',L('暂无照片','No photo')));const content=node('div','tile-content');content.append(node('span','tile-category',C(d.intent)),node('h3','tile-title',d.title),node('div','tile-price',money(d.amount)+(d.intent==='rent'?' '+C('perDay'):'')),node('p','tile-meta',d.location),node('p','tile-footer','Demo · '+(L('本标签页发布预览','Your tab-only draft'))));a.append(media,content);card.append(a,makeShare(href,d.title));}
      parent.prepend(card);
    });
  }
  function setupPublish(){
    const form=document.querySelector('[data-market-publish]');if(!form)return;
    const defaults=Core.defaults();for(const name of ['start','end'])if(!form.elements[name].value)form.elements[name].value=defaults[name];
    const requested=new URLSearchParams(location.search).get('intent');if(['sale','rent','borrow','buy'].includes(requested)){const radio=form.querySelector('input[name=intent][value="'+requested+'"]');if(radio)radio.checked=true;}
    updatePublish(form);
  }
  function updatePublish(form){
    const intent=new FormData(form).get('intent'),flat=intent==='sale'||intent==='buy';
    form.querySelector('[data-amount-label]').textContent=C(intent==='sale'?'price':intent==='rent'?'daily':'budget');
    form.querySelector('[data-mode-note]').textContent=flat?(L('仅金额和描述必填，其他信息可以稍后补充。','Only amount and description are required.')):(L('默认香港当天开始，7 天后结束，所有条件均可修改。','Today to 7 days later, HK time. All defaults can be changed.'));
    form.querySelectorAll('[data-rental-only]').forEach(n=>{n.hidden=flat;for(const field of n.querySelectorAll('input'))field.disabled=flat;});
    const generated=Core.deriveTitle(form.elements.description.value);form.querySelector('[data-title-preview]').textContent=generated?(form.elements.title.value||generated)+' · '+C('generatedTitle'):'';
  }
  function publish(form){
    const data=new FormData(form),amount=data.get('amount'),description=String(data.get('description')||'').trim(),intent=data.get('intent');
    const status=form.querySelector('.market-form-status');status.textContent='';
    if(!description||amount===''||!Number.isFinite(Number(amount))||Number(amount)<0){status.textContent=C('invalid');(!description?form.elements.description:form.elements.amount).focus();return;}
    const flat=['sale','buy'].includes(intent),defaults=Core.defaults(),start=String(data.get('start')||defaults.start),end=String(data.get('end')||defaults.end);
    if(!flat&&!Core.rentalQuote(start,end,0)){status.textContent=C('invalidDates');form.querySelector('details').open=true;form.elements.end.focus();return;}
    const deposit=Number(data.get('deposit')||0),maxDays=Number(data.get('maxDays')||7);
    if(!flat&&(!Number.isFinite(deposit)||deposit<0||!Number.isInteger(maxDays)||maxDays<1)){status.textContent=C('invalid');form.querySelector('details').open=true;return;}
    requireLogin(()=>{
      const d={id:uid(),ownerKey:state.tabKey,peer:'Demo publisher',intent,title:(String(data.get('title')||'').trim()||Core.deriveTitle(description)).slice(0,100),description,condition:String(data.get('condition')||''),amount:Number(amount),category:String(data.get('category')||'other'),location:String(data.get('location')||defaults.location),start,end,deposit,maxDays};
      state.drafts[d.id]=d;if(photoData)state.photos[d.id]=photoData;
      if(save())location.href=payloadLink(d,form.dataset.marketPublish==='wanted');
    });
  }
  function currentRental(){
    const body=document.body,id=body.dataset.itemId;if(!id)return null;
    return {id:'item-'+id,peer:body.dataset.itemPeer||'Jamie',title:document.querySelector('.item-decision h1')?.textContent||document.title,intent:'rent',location:body.dataset.itemLocation,amount:Number(body.dataset.itemPrice||0),deposit:Number(body.dataset.itemDeposit||0),start:body.dataset.itemStart,end:body.dataset.itemEnd,maxDays:Number(body.dataset.itemMax||14),href:localPath('items/'+id+'/')};
  }
  function rentalData(form,item){
    const start=form.elements.start.value,end=form.elements.end.value,q=Core.rentalQuote(start,end,item.amount,item.deposit);
    const output=form.querySelector('.rental-quote');output.hidden=false;
    if(!q){output.textContent=C('invalidDates');return null;}
    if((item.start&&Date.parse(start+'+08:00')<Date.parse(item.start+'+08:00'))||(item.end&&Date.parse(end+'+08:00')>Date.parse(item.end+'+08:00'))||(item.maxDays&&q.days>item.maxDays)){output.textContent=C('outsideWindow');return null;}
    output.textContent=q.days+(L(' 日 · ',' days · '))+money(q.rent)+' + '+C('deposit')+' '+money(q.deposit)+(L(' · 示例费用，未检查真实库存。',' · Sample quotation; no live availability check.'));
    return {...q,start,end};
  }
  function createOrder(item,kind,quote){
    const existing=state.orders.find(o=>o.item.id===item.id&&o.kind===kind&&(!quote||(o.quote?.start===quote.start&&o.quote?.end===quote.end)));
    if(existing){location.href=localPath('orders/demo/')+'?id='+encodeURIComponent(existing.id);return;}
    const d=dialog(C(kind==='purchase'?'confirmBuy':'confirmRequest'));
    d.append(node('h3','',item.title),node('p','order-price',money(quote?quote.rent:item.amount)),node('p','',C(kind==='purchase'?'buyBody':'requestBody')));
    const actions=node('div','dialog-actions');actions.append(button(C('cancel'),()=>d.close(),'button secondary'),button(C(kind==='purchase'?'confirmBuy':'confirmRequest'),()=>{
      const order={id:uid(),kind,item,quote:quote||null,created:new Date().toISOString()};state.orders.push(order);if(save()){d.close();location.href=localPath('orders/demo/')+'?id='+encodeURIComponent(order.id);}
    }));d.append(actions);d.showModal();
  }
  function renderListing(host,d,wanted=false){
    currentItem={...d,href:location.pathname+location.hash};
    const wrapper=node('section','market-detail');const heading=node('div','market-detail-heading');
    heading.append(link(L('← 返回浏览','← Back to browse'),localPath(wanted?'seeking/':''),'breadcrumb'));
    if(!wanted)heading.append(makeShare(location.pathname+location.hash,d.title));
    const card=node('div','panel market-detail-panel');card.append(node('span','pill',C(d.intent==='buy'?'wantedBuy':d.intent)),node('h1','',d.title),node('div','market-detail-price',money(d.amount)+(d.intent==='rent'?' '+C('perDay'):'')),node('p','hint',wanted?C('budget'):C(d.intent==='sale'?'oneOff':'daily')));
    if(state.photos[d.id]){const img=node('img','market-detail-photo');img.src=state.photos[d.id];img.alt=d.title;card.append(img);}
    const desc=node('p','market-description',d.description);card.append(desc,node('p','hint',d.location),node('p','hint',L('合成示例 · 不代表真实上架或库存。','Synthetic example · No real listing or inventory.')));if(d.intent==='rent'&&d.condition)card.append(node('p','hint',L('物品状况','Condition')+' · '+d.condition));
    const actions=node('div','market-detail-actions');
    const own=state.drafts[d.id]&&d.ownerKey===state.tabKey;
    if(own){actions.append(node('p','hint',L('这是你自己的发布预览，可浏览其他示例体验联系或申请。','This is your own preview. Browse other examples to test contacting or requesting.')),link(wanted?(L('浏览求借／求购','Browse requests')):(L('查看其他物品示例','View another example')),localPath(wanted?'seeking/':d.intent==='sale'?'items/sale-example/':'items/2/')));}
    else if(d.intent==='sale')actions.append(button(C('buy'),()=>requireLogin(()=>createOrder(currentItem,'purchase'))),link(C('contact'),threadURL(currentItem)));
    else if(wanted)actions.append(link(C('offer'),threadURL(currentItem)));
    else{
      const form=node('form','market-rental form-stack');form.dataset.marketRental='true';
      for(const [name,label] of [['start',L('开始（香港时间）','Start (Hong Kong)')],['end',L('结束（香港时间）','End (Hong Kong)')]]){const l=node('label','',label),input=node('input');input.type='datetime-local';input.name=name;input.required=true;input.value=d[name]||Core.defaults()[name];l.append(input);form.append(l);}
      const quote=node('div','rental-quote');quote.hidden=true;quote.setAttribute('role','status');form.append(quote);const submit=node('button','button',C('submitRequest'));submit.type='submit';form.append(submit);card.append(form);actions.append(link(C('contact'),threadURL(currentItem)));
    }
    actions.querySelectorAll('a[href*="/messages/"]').forEach(a=>a.dataset.marketContact='true');card.append(actions);wrapper.append(heading,card);host.replaceChildren(wrapper);
  }
  function renderOrder(host){
    const id=new URLSearchParams(location.search).get('id'),order=state.orders.find(o=>o.id===id);
    const card=node('section','panel demo-order');card.append(node('span','eyebrow','BOX BOX SHARE / DEMO'));
    if(!state.signedIn){card.append(node('h1','',C('loginTitle')),button(C('login'),()=>requireLogin(()=>renderOrder(host))));host.replaceChildren(card);return;}
    if(!order){card.append(node('h1','',C('noOrder')),link(C('browse'),localPath('')));host.replaceChildren(card);return;}
    card.append(node('span','pill',C(order.kind==='purchase'?'pending':'pendingRent')),node('h1','',order.item.title),node('p','order-price',money(order.quote?order.quote.rent:order.item.amount)));
    if(order.quote)card.append(node('p','',order.quote.start.replace('T',' ')+' → '+order.quote.end.replace('T',' ')),node('p','',C('deposit')+' '+money(order.quote.deposit)));
    card.append(node('p','',order.item.location||'CityUHK campus'),node('p','hint',C('remaining')));
    const actions=node('div','market-detail-actions');const message=link(C('message'),threadURL(order.item));message.dataset.marketContact='true';actions.append(message,link(L('返回物品','Back to item'),order.item.href));card.append(actions,node('p','notice',L('仅示例订单，没有付款、真实库存占用或真实交易。','Sample order only. No payment, reservation or real transaction has been created.')));host.replaceChildren(card);
  }
  function renderConversation(host){
    const c=readContext();if(!c){host.replaceChildren(node('p','notice',C('emptyDraft')));return;}
    state.threads[c.key]=c;save();
    const pane=node('section','panel demo-conversation');const back=link(L('← 消息','← Messages'),localPath('messages/'),'breadcrumb');
    const header=node('div','chat-header');header.append(back,node('h1','',c.peer),link(c.title,c.href,'text-link'));const gate=node('div','contact-gate');gate.dataset.contactGate='';header.append(gate);
    const body=node('div','chat-body');body.append(node('div','messages-list'));
    const form=node('form','chat-composer');form.dataset.marketMessage='true';const input=node('textarea');input.name='text';input.required=true;input.maxLength=2000;input.setAttribute('aria-label',L('消息','Message'));input.placeholder=L('输入消息…','Write a message…');const submit=node('button','button',C('send'));submit.type='submit';form.append(input,submit);
    const menu=node('details','more-menu demo-safety-menu');menu.append(node('summary','',L('更多操作','More actions')));const menuBody=node('div','menu-content');menuBody.append(link(L('举报用户／骚扰','Report user / harassment'),localPath('report/user/2/'),'text-link'));const block=button('',()=>toggleBlock(),'text-button');block.dataset.marketBlockLabel='';menuBody.append(block);menu.append(menuBody);header.append(menu);
    const tools=node('div','demo-reply-tools'),reply=button(C('reply'),()=>simulateReply(),'text-button');reply.dataset.marketReply='';tools.append(node('span','',C('replyNote')),reply);pane.append(header,body,form,tools);host.replaceChildren(pane);
  }
  function conversationKey(){if(document.body.dataset.marketScreen==='conversation')return readContext()?.key;return document.body.dataset.conversation;}
  function allMessages(){
    const list=document.querySelector('.chat-body .messages-list');if(!list)return [];
    const original=[...list.querySelectorAll('.bubble:not([data-added-message])')].map(n=>({sender:n.classList.contains('me')||n.classList.contains('mine')?'me':'peer',text:n.querySelector('p')?.textContent||''}));
    return [...original,...(state.messages[conversationKey()]||[])];
  }
  function renderContactGate(){
    const gate=document.querySelector('[data-contact-gate]');if(!gate)return;
    const wasOpen=Boolean(gate.querySelector('.contact-details')?.open),ownWasOpen=Boolean(gate.querySelector('.own-contact-preview')?.open);
    const hadFocus=gate.contains(document.activeElement),ownHadFocus=Boolean(document.activeElement?.closest('.own-contact-preview'));
    const messages=allMessages(),blocked=isBlocked();
    gate.replaceChildren();const eligible=state.signedIn&&!blocked&&Core.canSeeContacts(messages);
    const details=node('details','contact-details');details.append(node('summary','',eligible?C('unlocked'):C('contacts')+' · '+Math.min(messages.length,4)+'/4'));
    if(eligible){details.append(node('p','hint',C('sampleContacts')));const rows=node('dl','contact-values');for(const name of ['whatsapp','phone','wechat','instagram']){rows.append(node('dt','',C(name)),node('dd','',name==='phone'||name==='whatsapp'?'+000 0000 0000':'boxbox_demo_peer'));}details.append(rows);const own=node('details','own-contact-preview');own.append(node('summary','',L('对方可见的我的联系方式','My contacts visible to this person')));const ownRows=node('dl','contact-values');for(const name of ['whatsapp','phone','wechat','instagram'])ownRows.append(node('dt','',C(name)),node('dd','',state.profile['contact_'+name]||(L('未填写','Not provided'))));own.append(ownRows);details.append(own);}
    else details.append(node('p','hint',blocked?C('blockedContacts'):!state.signedIn?C('loginContacts'):C('contactRule')+(messages.length>=4?' '+C('needPeer'):'')));
    details.open=wasOpen;const own=details.querySelector('.own-contact-preview');if(own)own.open=ownWasOpen;
    gate.append(details);
    if(hadFocus)(ownHadFocus&&own?own:details).querySelector('summary')?.focus({preventScroll:true});
  }
  function mountChat({forceBottom=false}={}){
    const list=document.querySelector('.chat-body .messages-list'),id=conversationKey();if(!list||!id)return;
    const scroller=list.closest('.chat-body'),previousTop=scroller?.scrollTop||0;
    const nearBottom=!scroller||scroller.scrollHeight-scroller.clientHeight-previousTop<72;
    const firstMount=scroller&&!scroller.dataset.messagesMounted;
    list.querySelectorAll('[data-added-message]').forEach(n=>n.remove());
    for(const m of state.messages[id]||[]){const bubble=node('div','bubble'+(m.sender==='me'?' mine me':''));bubble.dataset.addedMessage='true';bubble.append(node('small','',m.sender==='me'?'Demo · You':(document.body.dataset.peer||readContext()?.peer||'Jamie')+' · '+(L('示例回复','Simulated reply'))),node('p','',m.text));list.append(bubble);}
    renderContactGate();
    const blocked=isBlocked();document.querySelectorAll('[data-market-message] textarea,[data-market-message] button,[data-market-reply]').forEach(n=>n.disabled=blocked);
    document.querySelectorAll('[data-market-block-label]').forEach(n=>n.textContent=blocked?(L('解除拉黑','Unblock')):(L('拉黑对方','Block this person')));
    if(scroller){scroller.scrollTop=forceBottom||nearBottom||firstMount?scroller.scrollHeight:previousTop;scroller.dataset.messagesMounted='true';}
  }
  function chatFeedback(message,error=false){
    const form=document.querySelector('[data-market-message]');if(!form){toast(message);return;}
    let status=form.parentElement.querySelector('.chat-send-status');
    if(!status){status=node('p','hint chat-send-status');form.after(status);}
    status.setAttribute('role',error?'alert':'status');status.dataset.state=error?'error':'success';status.textContent=message;
  }
  function addMessage(sender,text){
    if(isBlocked())return false;
    const id=conversationKey(),value=text.trim();if(!id)return false;
    if(!value||value.length>2000){chatFeedback(L('请输入 1–2000 字的消息。','Enter a message of 1–2000 characters.'),true);return false;}
    const scroller=document.querySelector('.chat-body'),readingEarlier=scroller&&scroller.scrollHeight-scroller.clientHeight-scroller.scrollTop>=72;
    state.messages[id]||=[];state.messages[id].push({sender,text:value,stamp:new Date().toISOString()});
    if(!save()){chatFeedback(C('storageError'),true);return false;}
    mountChat({forceBottom:sender==='me'});mountThreadRows();
    chatFeedback(sender==='me'?L('示例消息已保存在当前标签页。','Sample message saved in this tab.'):readingEarlier?L('收到示例回复，向下查看新消息。','New sample reply. Scroll down to see it.'):L('已加入一条示例回复。','A sample reply was added.'));
    return true;
  }
  function isBlocked(){return document.body.dataset.blocked==='true'||Boolean(state.blocks[conversationKey()]);}
  function toggleBlock(){requireLogin(()=>{const id=conversationKey(),blocked=isBlocked();const d=dialog(blocked?L('解除拉黑？','Unblock this person?'):L('拉黑对方？','Block this person?'));d.append(node('p','',L('仅演示。拉黑后隐藏联系方式，停止此对话的模拟消息，既有记录会保留。','Demo only. Blocking hides contact details and prevents further simulated messages in this conversation. History is retained.')),button(L('确认','Confirm'),()=>{state.blocks[id]=!blocked;if(save()){d.close();mountChat();}}));d.showModal();});}
  function mountThreadRows(){
    const rail=document.querySelector('.thread-list');if(!rail)return;
    const previousScroll=rail.scrollTop,query=(document.querySelector('[data-thread-search]')?.value||'').trim().toLocaleLowerCase();
    rail.querySelectorAll('[data-local-thread]').forEach(n=>n.remove());
    const current=document.body.dataset.marketScreen==='conversation'?readContext()?.key:null;
    if(current)rail.querySelectorAll('.current').forEach(n=>{n.classList.remove('current');n.removeAttribute('aria-current');});
    for(const c of Object.values(state.threads)){
      const href=localPath('messages/demo/')+'#'+new URLSearchParams({context:JSON.stringify(c)}),a=link('',href,'thread-row'+(c.key===current?' current':''));a.dataset.localThread=c.key;if(c.key===current)a.setAttribute('aria-current','page');
      const summary=node('span','thread-summary');summary.append(node('strong','',c.peer),node('span','thread-topic',c.title));const last=state.messages[c.key]?.at(-1);summary.append(node('span','thread-preview',last?.text||(L('尚未开始对话','No messages yet'))));a.append(node('span','avatar',c.peer[0]),summary);a.hidden=Boolean(query)&&!a.textContent.toLocaleLowerCase().includes(query);rail.prepend(a);
    }
    rail.scrollTop=previousScroll;
    const status=document.querySelector('.thread-search-status');if(status&&query){const count=[...rail.querySelectorAll('.thread-row')].filter(n=>!n.hidden).length;status.hidden=false;status.textContent=count?count+L(' 个对话',' conversations'):L('没有匹配的对话。试试姓名或物品名称。','No matching conversations. Try a person or item name.');}
  }
  function simulateReply(){requireLogin(()=>addMessage('peer',C('replyBody')));}
  function mountProfile(){
    const form=document.querySelector('[data-market-profile]');if(!form)return;
    form.hidden=!state.signedIn;
    form.querySelectorAll('input,textarea,select,button').forEach(n=>{if(n.type!=='file')n.disabled=!state.signedIn;});
    for(const name of ['nickname','bio','interests','skills','languages','university','major','academic_year','faculty',...['whatsapp','phone','wechat','instagram'].map(k=>'contact_'+k)])if(state.profile[name]!==undefined&&form.elements[name])form.elements[name].value=state.profile[name];
    let prompt=document.querySelector('.profile-login');if(!prompt){prompt=node('div','profile-login notice');form.before(prompt);}prompt.replaceChildren();prompt.hidden=state.signedIn;
    if(!state.signedIn)prompt.append(node('p','',C('loginBody')),button(C('login'),()=>requireLogin(()=>mountProfile())));
  }
  function mountOrders(){
    if(document.body.dataset.demoRoute!=='my/')return;
    let list=document.querySelector('.local-demo-orders');if(list)list.remove();if(!state.orders.length)return;
    list=node('section','panel local-demo-orders');list.append(node('h2','',L('本标签页的示例订单','Your tab’s sample orders')));
    for(const order of state.orders){const a=link('',localPath('orders/demo/')+'?id='+encodeURIComponent(order.id),'list-row');a.append(node('strong','',order.item.title),node('span','pill',C(order.kind==='purchase'?'pending':'pendingRent')));list.append(a);}
    document.querySelector('main .page')?.prepend(list);
  }
  function init(){
    currentItem=null;syncIdentity();setupPublish();mountProfile();mountDraftCards();
    const host=document.querySelector('[data-market-screen-content]'),screen=document.body.dataset.marketScreen;
    if(host){if(screen==='order')renderOrder(host);else if(screen==='conversation')renderConversation(host);else{let d=screen==='sale-example'?sampleSale():screen==='buy-example'?sampleBuy():Core.readPayload(location.hash);if(d)renderListing(host,d,screen==='buy-example'||screen==='wanted-preview');else host.replaceChildren(node('p','notice',C('emptyDraft')),link(C('browse'),localPath('')));}}
    const rental=document.querySelector('[data-market-rental]');if(rental){const defaults=Core.defaults();for(const name of ['start','end'])if(!rental.elements[name].value)rental.elements[name].value=defaults[name];}
    mountChat();mountThreadRows();mountOrders();intentTabs();
    const form=document.querySelector('.filter-form[data-filter]');if(form&&form.elements.namedItem('intent'))form.requestSubmit();
  }
  document.addEventListener('DOMContentLoaded',init);document.addEventListener('collection:mounted',init);
  document.addEventListener('input',e=>{const form=e.target.closest('[data-market-publish]');if(form)updatePublish(form);});
  document.addEventListener('change',e=>{
    const form=e.target.closest('[data-market-publish]');if(!form)return;updatePublish(form);
    if(e.target.name==='photo'){
      const file=e.target.files?.[0],img=form.querySelector('[data-photo-preview]');photoData='';img.hidden=true;
      if(!file)return;if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>1024*1024){form.querySelector('.market-form-status').textContent=L('演示照片请使用 1 MB 以内的 JPEG、PNG 或 WebP。','Use a JPEG, PNG or WebP under 1 MB for this demo.');e.target.value='';return;}
      const reader=new FileReader();reader.onload=()=>{photoData=String(reader.result);img.src=photoData;img.hidden=false;};reader.readAsDataURL(file);
    }
  });
  document.addEventListener('submit',e=>{
    const form=e.target;
    if(form.matches('[data-market-publish]')){e.preventDefault();e.stopImmediatePropagation();publish(form);}
    else if(form.matches('[data-market-profile]')){e.preventDefault();e.stopImmediatePropagation();requireLogin(()=>{state.profile=Object.fromEntries([...new FormData(form)].filter(([k])=>k!=='avatar'));const status=form.querySelector('.market-profile-status'),saved=save();if(status){status.textContent=C(saved?'saved':'storageError');status.setAttribute('role',saved?'status':'alert');status.dataset.state=saved?'success':'error';}if(saved)toast(C('saved'));});}
    else if(form.matches('[data-market-message]')){e.preventDefault();e.stopImmediatePropagation();const input=form.elements.text,text=input.value;requireLogin(()=>{if(addMessage('me',text)){input.value='';input.focus({preventScroll:true});}else input.focus({preventScroll:true});});}
    else if(form.matches('[data-market-rental]')){e.preventDefault();e.stopImmediatePropagation();const item=currentItem||currentRental();if(!item)return;requireLogin(()=>{const quote=rentalData(form,item);if(quote)createOrder(item,'rental',quote);});}
    else if(form.matches('[data-market-guard]')&&!state.signedIn){e.preventDefault();e.stopImmediatePropagation();requireLogin(()=>form.requestSubmit());}
  },true);
  document.addEventListener('click',e=>{
    const auth=e.target.closest('[data-market-auth]');
    if(auth){e.preventDefault();e.stopImmediatePropagation();if(state.signedIn){const signedOut={...state,signedIn:false};state.signedIn=false;if(!save()){state=signedOut;savedState=JSON.stringify(state);try{sessionStorage.removeItem(key);}catch{}toast(L('已退出当前演示登录，浏览器无法保存其他演示状态。','Signed out of this demo. Other demo state could not be saved.'));}syncIdentity();mountProfile();renderContactGate();if(document.body.dataset.marketScreen==='order')renderOrder(document.querySelector('[data-market-screen-content]'));}else requireLogin(()=>{});return;}
    const reset=e.target.closest('[data-market-reset]');if(reset){const d=dialog(C('resetTitle'));d.append(node('p','',C('resetBody')),button(C('resetConfirm'),()=>{state=fresh();if(save()){sessionStorage.removeItem('boxbox-student-demo-v1');sessionStorage.removeItem('boxbox-group-demo-v1');location.href=localPath('');}}));d.showModal();return;}
    const share=e.target.closest('[data-share-item]');if(share){e.preventDefault();e.stopImmediatePropagation();shareItem(share.dataset.shareItem,share.closest('.item-tile')?.querySelector('h3')?.textContent);return;}
    const intent=e.target.closest('[data-market-filter]');if(intent){const form=document.querySelector('.filter-form[data-filter]');form.elements.namedItem('intent').value=intent.dataset.marketFilter;form.requestSubmit();intentTabs();return;}
    const reply=e.target.closest('[data-market-reply]');if(reply){e.preventDefault();e.stopImmediatePropagation();simulateReply();return;}
    const quote=e.target.closest('[data-market-quote]');if(quote){e.preventDefault();e.stopImmediatePropagation();rentalData(quote.closest('form'),currentRental());return;}
    const contact=e.target.closest('[data-market-contact],[data-demo-link]');
    if(contact){const item=contact.hasAttribute('data-market-contact-item')?currentRental():null;const dest=item?threadURL(item):contact.dataset.demoLink||contact.getAttribute('href');if(dest&&/\/messages\//.test(dest)){e.preventDefault();e.stopImmediatePropagation();requireLogin(()=>{location.href=dest;});return;}}
  },true);
  document.addEventListener('submit',e=>{if(e.target.matches('.filter-form[data-filter]'))intentTabs();});
  document.addEventListener('reset',e=>{if(e.target.matches('.filter-form[data-filter]'))setTimeout(intentTabs,0);});
  window.addEventListener('hashchange',()=>{if(document.body.dataset.marketScreen)init();});
})();
