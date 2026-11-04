/* Progressive enhancements; native POST, CSRF and submitter values stay intact. */
(() => {
  'use strict';
  const menuSelector='.experience-menu,.experience-roster,.experience-mobile-more';
  document.addEventListener('click',event=>{
    for(const menu of document.querySelectorAll('.experience-menu[open],.experience-roster[open],.experience-mobile-more[open]'))if(!menu.contains(event.target))menu.open=false;
    if(event.target.closest('[data-focus-composer]'))document.querySelector('[data-experience-chat] textarea')?.focus();
  });
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape')for(const menu of document.querySelectorAll('.experience-menu[open],.experience-roster[open],.experience-mobile-more[open]')){menu.open=false;menu.querySelector('summary')?.focus();}
  });
  document.addEventListener('toggle',event=>{
    if(!event.target.matches(menuSelector)||!event.target.open)return;
    for(const menu of document.querySelectorAll('.experience-menu[open],.experience-roster[open],.experience-mobile-more[open]'))if(menu!==event.target)menu.open=false;
  },true);
  for(const form of document.querySelectorAll('[data-experience-chat]')){
    const input=form.elements.namedItem('text'),count=document.querySelector('[data-message-count]');
    const update=()=>{if(count)count.textContent=`${input.value.length} / 2000`;input.setCustomValidity('');};
    input.addEventListener('input',update);update();
    input.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'&&!event.isComposing){event.preventDefault();form.requestSubmit(form.querySelector('button[name=action][value=send]'));}});
  }
  document.addEventListener('submit',event=>{
    const form=event.target;
    if(!form.matches('[data-experience-chat],[data-experience-profile],.experience-leave-confirm form,.experience-group-entry form')||event.defaultPrevented)return;
    if(form.classList.contains('is-submitting')){event.preventDefault();return;}
    if(form.matches('[data-experience-chat]')){const input=form.elements.namedItem('text');if(!input.value.trim()){event.preventDefault();input.setCustomValidity(form.dataset.emptyMessage);input.reportValidity();return;}}
    // Disabling the submitter would omit action=send/leave/join/create from native POST.
    form.classList.add('is-submitting');
    if(event.submitter){event.submitter.setAttribute('aria-busy','true');event.submitter.setAttribute('aria-disabled','true');}
  });
  window.addEventListener('pageshow',()=>{
    for(const form of document.querySelectorAll('form.is-submitting'))form.classList.remove('is-submitting');
    for(const button of document.querySelectorAll('[aria-busy=true]')){button.removeAttribute('aria-busy');button.removeAttribute('aria-disabled');}
  });
  const messages=document.querySelector('.experience-group-messages');if(messages&&messages.querySelector('.bubble'))messages.scrollTop=messages.scrollHeight;
})();
