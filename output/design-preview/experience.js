/* Native menu refinement only; forms and product actions keep their owners. */
(() => {
  'use strict';
  const menus = 'details.lang-menu,details.more-nav,details.more-menu,details.experience-menu';
  document.addEventListener('toggle', event => {
    const current=event.target;
    if(!(current instanceof HTMLDetailsElement)||!current.matches(menus)||!current.open)return;
    document.querySelectorAll(menus).forEach(menu=>{if(menu!==current&&!menu.contains(current))menu.open=false;});
  },true);
  document.addEventListener('click',event=>{
    document.querySelectorAll(menus).forEach(menu=>{if(menu.open&&!menu.contains(event.target))menu.open=false;});
  });
  document.addEventListener('keydown',event=>{
    if(event.key!=='Escape'||document.querySelector('dialog[open]'))return;
    const open=[...document.querySelectorAll(menus)].filter(menu=>menu.open);
    if(!open.length)return;
    const focused=open.find(menu=>menu.contains(document.activeElement))||open.at(-1);
    open.forEach(menu=>{menu.open=false;});
    focused.querySelector('summary')?.focus({preventScroll:true});
  });
})();
