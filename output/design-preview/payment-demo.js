/* Synthetic UI only: no QR payload, payment provider, FX fetch or payment mutation. */
(() => {
  'use strict';
  const copyNode=document.getElementById('payment-copy');
  if(!copyNode)return;
  const copy=JSON.parse(copyNode.textContent),content=document.querySelector('[data-payment-content]');
  const signed=()=>Boolean(window.BoxDemoAccess?.isSignedIn());
  const authorize=action=>window.BoxDemoAccess?.requireLogin(action);
  const storageKey=()=>{
    try{return 'boxbox-payment-demo-v1:'+JSON.parse(sessionStorage.getItem('boxbox-market-demo-v1')).tabKey;}catch{return null;}
  };
  const readChannels=()=>{
    try{const value=JSON.parse(sessionStorage.getItem(storageKey()));return Array.isArray(value)?value.filter(x=>['wechat','alipay_cn','alipay_hk','fps'].includes(x)):[];}catch{return [];}
  };
  function settings(){
    const enabled=readChannels();
    document.querySelectorAll('[data-payment-setting]').forEach(card=>{
      const active=enabled.includes(card.dataset.paymentSetting),button=card.querySelector('[data-payment-setting-toggle]');
      card.querySelector('[data-payment-setting-status]').textContent=copy[active?'enabled':'disabled'];
      card.querySelector('.payment-setting-placeholder').hidden=!active;
      button.textContent=copy[active?'remove':'add'];
      button.setAttribute('aria-pressed',String(active));
    });
  }
  function render(){
    if(!content)return;
    const lock=document.querySelector('[data-payment-lock]');
    content.hidden=!signed();lock.replaceChildren();
    if(!signed()){
      const title=document.createElement('h1'),note=document.createElement('p'),button=document.createElement('button');
      title.textContent=copy.login;note.textContent=copy.private;note.className='hint';
      button.type='button';button.className='button';button.textContent=copy.login;
      button.addEventListener('click',()=>authorize(render));lock.append(title,note,button);
      document.querySelector('.payment-demo-dialog[open]')?.close();
    }else settings();
  }
  document.addEventListener('click',event=>{
    const entry=event.target.closest('[data-payment-entry]');
    if(entry){event.preventDefault();authorize(()=>{location.href=entry.href;});return;}
    const toggle=event.target.closest('[data-payment-setting-toggle]');
    if(!toggle)return;
    authorize(()=>{
      const channel=toggle.closest('[data-payment-setting]').dataset.paymentSetting,enabled=readChannels();
      const next=enabled.includes(channel)?enabled.filter(x=>x!==channel):[...enabled,channel];
      const status=document.querySelector('[data-payment-settings-status]');
      try{const key=storageKey();if(!key)throw new Error('No demo identity');sessionStorage.setItem(key,JSON.stringify(next));settings();status.textContent=copy.saved;}
      catch{status.textContent=copy.storage;}
    });
  },true);
  const currency=document.querySelector('[data-payment-currency]');
  currency?.addEventListener('change',()=>{
    document.querySelector('[data-payment-converted]').textContent=currency.value==='CNY'?'CNY 91.80':'HK$ 108.00';
  });
  const dialog=document.querySelector('.payment-demo-dialog');
  if(dialog){
    let opener;
    const menus=[...document.querySelectorAll('.payment-alipay-menu')];
    document.addEventListener('click',event=>{
      for(const menu of menus)if(!menu.contains(event.target))menu.open=false;
      const channel=event.target.closest('[data-payment-channel]');
      if(!channel)return;
      authorize(()=>{
        opener=channel.closest('details')?.querySelector('summary')||channel;
        for(const menu of menus)menu.open=false;
        dialog.querySelector('h2').textContent=channel.textContent.trim();dialog.showModal();
        dialog.querySelector('[data-payment-close]').focus({preventScroll:true});
      });
    });
    dialog.addEventListener('click',event=>{
      if(event.target.closest('[data-payment-close]'))dialog.close();
      else if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}
    });
    dialog.addEventListener('close',()=>opener?.focus({preventScroll:true}));
    document.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&!dialog.open)for(const menu of menus)if(menu.open){menu.open=false;menu.querySelector('summary').focus();}
    });
  }
  document.addEventListener('DOMContentLoaded',render);
  document.addEventListener('market:identity',render);
})();
