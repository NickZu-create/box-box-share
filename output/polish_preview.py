"""Add presentation and local-only controls to the existing sanitized export."""
from bs4 import BeautifulSoup

def polish(s, lang, route, tr, ico):
    t=lambda z,e:tr(lang,z,e)
    f=lambda html:BeautifulSoup(html,'html.parser')
    s.body['class']=s.body.get('class',[])+['polished']
    for form in s.select('.filter-form[data-filter]'):
        form.insert_after(f('<div class="applied-filters" aria-label="'+t('已选筛选条件','Applied filters')+'" hidden></div>'))
        if form.get('data-filter')=='buddy':
            for cls,z,e in [('filter-kind','招募类型','Post type'),('filter-when','活动时间','When'),('filter-state','招募状态','Status')]:
                label=form.select_one('.'+cls+' > .sr-only')
                if label:label['class']=['filter-label'];label.string=t(z,e)
    sidebar=s.select_one('.conversation-sidebar')
    if sidebar:
        sidebar.select_one('.thread-list').insert_before(f('<label class="conversation-search">'+ico('search')+'<span class="sr-only">'+t('搜索对话','Search conversations')+'</span><input type="search" data-thread-search placeholder="'+t('搜索联系人、物品或消息…','Search people, topics or messages…')+'"></label><p class="thread-search-status" role="status" hidden></p>'))
    for button in s.select('.chat-composer button'):
        button['aria-label']=t('发送消息','Send message')
    if route=='my/':
        panel=s.select_one('.page > .panel')
        if panel:
            panel['class']=panel.get('class',[])+['order-panel']
            buttons=[('all',t('全部','All')),('pending',t('待确认','Pending')),('accepted',t('已接受','Accepted')),('active',t('借用中','Active')),('completed',t('已完成','Completed'))]
            panel.h2.insert_after(f('<div class="order-filters" role="group" aria-label="'+t('按订单状态筛选','Filter orders by status')+'">'+''.join('<button type="button" data-order-state="'+key+'" aria-pressed="'+('true' if key=='all' else 'false')+'">'+label+'</button>' for key,label in buttons)+'</div><p class="order-filter-status" role="status" hidden>'+t('此状态下没有示例订单。','No sample orders with this status.')+'</p>'))
            for row in panel.select('a.list-row'):
                badge=row.select_one('.status')
                row['data-order-status']=next((x for x in ['pending','accepted','active','completed'] if x in (badge.get('class',[]) if badge else [])),'other')
    if route.startswith('lost-found/') or route=='my/':
        for heading in s.select('.lf-card h3,.list-row h3'):
            # Localize only the existing bilingual name, retaining order labels.
            if heading.contents and isinstance(heading.contents[0],str) and ' / ' in heading.contents[0]:
                value=str(heading.contents[0]);heading['title']=value.strip()
                heading.contents[0].replace_with(value.split(' / ')[0 if lang=='en' else -1].strip())
    for index,symbol in enumerate(s.select('.lf-section-symbol')):
        symbol.clear();symbol.append(f(ico('package' if index==0 else 'search')))
    for summary in s.select('.lf-more > summary'):
        summary.append(f(ico('chevron-down')))
    publish=s.select_one('.site-header .header-actions > .button')
    if publish and route.startswith('buddy'):
        publish['href']=f'/{lang}/buddy/new/';publish['aria-label']=t('发布招募','Create a post')
        publish.select_one('.publish-label').string=t('发布招募','Create a post')
    if publish and route.startswith('lost-found/'):
        publish['href']=f'/{lang}/lost-found/new/';publish['aria-label']=t('发布失物招领','Post lost or found')
        publish.select_one('.publish-label').string=t('发布信息','Post an update')
    s.body.insert(0,f('<a class="skip-link" href="#main-content">'+t('跳到主要内容','Skip to content')+'</a>'))
    s.main['id']='main-content';s.main['tabindex']='-1'
    for a in s.select('.desktop-nav a.selected'):a['aria-current']='page'
