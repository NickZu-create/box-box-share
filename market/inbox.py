"""What a member has not read yet, the feeds of the Messages page, and the item card at the top of a chat.

Private and group messages carry a per-person read marker; notifications carry their own flag. The browser
asks poll() every few seconds, so what it returns is limited to this reader's own threads and active groups.
"""
from django.db.models import Count, F, Max, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.template.defaultfilters import truncatechars
from django.utils import timezone
from . import groups, i18n, social
from .models import BuddyGroupMessage, Message, Notification, Order, Thread, ThreadRead, UserBlock
from .services import ORDER_ACTIONS

KINDS = ('system','item','friend','request')
LABELS = {'system':('系統更新','System'),'item':('物品通知','Items'),'friend':('好友與 Buddy','Friends & Buddy'),'request':('借用申請','Borrowing')}
FILTERS = {'all':('全部','All'),'friend':('好友','Friends'),'item':('物品','Items'),'request':('借用','Borrow')}
POPUPS = 3
PREVIEW = 80
FEED_NOTES = 100
REQUESTS = 10


def thread_kind(thread):
    if thread.order_id: return 'request' if thread.order.kind=='rental' else 'item'
    if thread.item_id or thread.wanted_id or thread.lostfound_id: return 'item'
    return 'friend'


def hidden_people(me):
    rows=UserBlock.objects.filter(Q(blocker=me)|Q(blocked=me)).values_list('blocker_id','blocked_id')
    return {blocked if blocker==me.pk else blocker for blocker,blocked in rows}


def my_threads(me): return Thread.objects.filter(Q(first=me)|Q(second=me))


def thread_unread(me,hidden=None):
    # thread pk -> (unread count, kind). Someone blocked in either direction raises no alert.
    hidden=hidden_people(me) if hidden is None else hidden
    marker=ThreadRead.objects.filter(thread=OuterRef('pk'),user=me).values('last_read')[:1]
    rows=my_threads(me).exclude(first_id__in=hidden).exclude(second_id__in=hidden).select_related('order').annotate(read_upto=Coalesce(Subquery(marker),0)).annotate(fresh=Count('messages',filter=Q(messages__pk__gt=F('read_upto'),messages__recalled=False)&~Q(messages__sender=me))).filter(fresh__gt=0)
    return {thread.pk:(thread.fresh,thread_kind(thread)) for thread in rows}


def group_unread(me,rows=None):
    # (membership, unread messages) for each group this member can still read.
    rows=groups.active_memberships(me) if rows is None else rows
    return [(row,groups.visible_messages(row.group,me,row).filter(pk__gt=row.last_read,recalled=False).exclude(sender=me).count()) for row in rows]


def counts(me,threads=None,in_groups=None):
    threads=thread_unread(me) if threads is None else threads
    in_groups=group_unread(me) if in_groups is None else in_groups
    result=dict.fromkeys(KINDS,0)
    for kind,number in Notification.objects.filter(user=me,read=False).values_list('kind').annotate(Count('pk')).order_by(): result[kind]=result.get(kind,0)+number
    result['notes']=sum(result[kind] for kind in KINDS)
    chats=dict.fromkeys(FILTERS,0)
    for fresh,kind in threads.values():
        result[kind]+=fresh
        chats[kind]+=fresh
    in_group=sum(fresh for _,fresh in in_groups)
    result['friend']+=in_group
    chats['friend']+=in_group
    chats['all']=chats['friend']+chats['item']+chats['request']
    result.update({f'chat_{kind}':number for kind,number in chats.items()})
    result['total']=sum(result[kind] for kind in KINDS)
    return result


def mark_thread_read(thread,me):
    last=thread.messages.aggregate(last=Max('pk'))['last']
    if last is None: return
    row,_=ThreadRead.objects.get_or_create(thread=thread,user=me,defaults={'last_read':last})
    if row.last_read<last: ThreadRead.objects.filter(pk=row.pk,last_read__lt=last).update(last_read=last)


def mark_group_read(group,me,row):
    last=groups.visible_messages(group,me,row).aggregate(last=Max('pk'))['last']
    if last and row.last_read<last:
        row.last_read=last
        row.save(update_fields=['last_read'])


def mark_conversation_read(threads,me):
    for thread in threads: mark_thread_read(thread,me)


def line_preview(text,recalled,image,lang):
    if recalled: return i18n.tr('訊息已撤回','Message recalled',lang)
    return text or (i18n.tr('[圖片]','[Photo]',lang) if image else '')


def message_rows(me,lang=None):
    # Threads, most recently active first.
    latest=Message.objects.filter(thread=OuterRef('pk')).order_by('-created','-pk')
    threads=my_threads(me).select_related('item','order__item','buddy','lostfound','wanted','first__profile','second__profile').annotate(last_text=Subquery(latest.values('text')[:1]),last_at=Subquery(latest.values('created')[:1]),last_sender=Subquery(latest.values('sender_id')[:1]),last_recalled=Subquery(latest.values('recalled')[:1]),last_image=Subquery(latest.values('image')[:1]),last_id=Subquery(latest.values('pk')[:1])).order_by(F('last_at').desc(nulls_last=True),'-pk')
    return [{'thread':t,'other':t.second if t.first_id==me.pk else t.first,'preview':line_preview(t.last_text,t.last_recalled,t.last_image,lang) if t.last_at else '','stamp':t.last_at,'mine':t.last_sender==me.pk,'last_line':f'message:{t.last_id}' if t.last_id else ''} for t in threads]


def order_preview(order,me,lang):
    title=order.snapshot.get('title') or order.item.title
    if order.is_purchase: return i18n.tr('購買了','Bought',lang)+f' {title}'
    return i18n.tr('申請借用','Borrow request:',lang)+f' {title}'


def feed_rows(me,lang=None):
    """One row per person, newest first. Unread counts and filters cover all of that pair's threads."""
    hidden=hidden_people(me)
    fresh=thread_unread(me,hidden)
    people={}
    for row in message_rows(me,lang):
        thread=row['thread']
        kind=thread_kind(thread)
        entry=people.setdefault(row['other'].pk,{**row,'type':'thread','unread':0,'threads':[],'first_of_kind':{},'unread_of_kind':{}})
        entry['threads'].append(thread)
        entry['first_of_kind'].setdefault(kind,thread)
        count=fresh.get(thread.pk,(0,))[0]
        entry['unread']+=count
        entry['unread_of_kind'][kind]=entry['unread_of_kind'].get(kind,0)+count
        # A request is a message in the conversation, so it can be the latest thing said.
        if thread.order_id and (not entry['stamp'] or thread.order.created>entry['stamp']):
            entry.update(thread=thread,preview=order_preview(thread.order,me,lang),stamp=thread.order.created,mine=thread.order.borrower_id==me.pk,last_line='')
    rows=list(people.values())
    for membership,unread in group_unread(me):
        last=groups.visible_messages(membership.group,me,membership).order_by('-pk').first()
        rows.append({'type':'group','first_of_kind':{'friend':None},'unread_of_kind':{'friend':unread},'membership':membership,'unread':unread,'preview':line_preview(last.text,last.recalled,last.image,lang) if last else '','last_line':f'group:{last.pk}' if last else '','stamp':last.created if last else membership.joined_at})
    undated=[row for row in rows if not row['stamp']]
    return sorted((row for row in rows if row['stamp']),key=lambda row:row['stamp'],reverse=True)+undated


def forward_targets(me):
    targets=[]
    for row in feed_rows(me):
        if row['type']=='group': targets.append({'name':row['membership'].group.post.title,'value':f"group:{row['membership'].group_id}"})
        else:
            thread=next((t for t in row['threads'] if social.can_message(t,me)),None)
            if thread: targets.append({'name':row['other'].profile.nickname,'value':f'thread:{thread.pk}'})
    return targets


def tab_rows(rows,tab):
    if tab=='all': return rows
    # In a filter, the row opens and counts what the filter is about.
    return [{**row,'thread':row['first_of_kind'][tab] or row.get('thread'),'unread':row['unread_of_kind'].get(tab,0)} for row in rows if tab in row['first_of_kind']]


def tabs(lang,numbers,current):
    return [{'kind':kind,'label':i18n.tr(*names,lang),'count':numbers[f'chat_{kind}'],'current':kind==current} for kind,names in FILTERS.items()]


def notes_row(me,numbers):
    # All notifications share one row at the top of the list, opening their own page.
    note=Notification.objects.filter(user=me).order_by('-created','-pk').first()
    return {'text':note.text,'detail':note.detail,'stamp':note.created,'unread':numbers['notes']} if note else None


def note_kinds(me,lang,current):
    unread=dict(Notification.objects.filter(user=me,read=False).values_list('kind').annotate(Count('pk')).order_by())
    rows=[{'kind':'','label':i18n.tr('全部','All',lang),'count':sum(unread.values()),'current':not current}]
    return rows+[{'kind':kind,'label':i18n.tr(*LABELS[kind],lang),'count':unread.get(kind,0),'current':kind==current} for kind in KINDS]


def _number(value):
    try: return max(int(value),0)
    except (TypeError,ValueError): return None


def _message_alerts(me,after,hidden,fresh,lang):
    # The newest message from each person, so a burst from one person is one pop-up.
    seen={}
    rows=Message.objects.filter(thread__in=list(fresh),pk__gt=after,recalled=False).exclude(sender=me).select_related('sender__profile').order_by('-pk')[:20]
    for message in rows:
        if message.sender_id in seen or message.sender_id in hidden: continue
        seen[message.sender_id]={'key':f'm{message.pk}','person':message.sender_id,'title':message.sender.profile.nickname,'text':truncatechars(line_preview(message.text,False,message.image,lang),PREVIEW),'url':f'/messages/{message.thread_id}/','kind':fresh[message.thread_id][1],'order':message.created.timestamp()}
    return list(seen.values())


def _group_alerts(me,after,in_groups,lang):
    alerts=[]
    for row,unread in in_groups:
        if not unread: continue
        message=groups.visible_messages(row.group,me,row).filter(pk__gt=max(after,row.last_read),recalled=False).exclude(sender=me).order_by('-pk').first()
        if message: alerts.append({'key':f'g{message.pk}','title':message.sender.profile.nickname,'text':truncatechars(line_preview(message.text,False,message.image,lang),PREVIEW),'url':f'/messages/groups/{row.group_id}/','kind':'friend','order':message.created.timestamp()})
    return alerts


def _note_alerts(me,after,lang):
    alerts=[]
    for note in Notification.objects.filter(user=me,read=False,pk__gt=after).order_by('-pk')[:POPUPS]:
        alerts.append({'key':f'n{note.pk}','title':i18n.tr(*LABELS.get(note.kind,LABELS['system']),lang),'text':i18n.loc(ORDER_ACTIONS.get(note.text,note.text))+(f' · {note.detail}' if note.detail else ''),'url':f'/notifications/{note.pk}/open/','kind':note.kind,'order':note.created.timestamp()})
    return alerts


def _stamp(moment): return timezone.localtime(moment).strftime('%m/%d %H:%M')


def pending_requests(me,hidden=None):
    """Borrow requests waiting for this owner, oldest first. Cancelled or expired ones simply drop out."""
    hidden=hidden_people(me) if hidden is None else hidden
    rows=Order.objects.filter(item__owner=me,kind='rental',status='pending',start__gt=timezone.now()).exclude(borrower_id__in=hidden).select_related('item','borrower__profile','thread').prefetch_related('item__photos').order_by('created','pk')[:REQUESTS]
    result=[]
    for order in rows:
        photos=list(order.item.photos.all())
        result.append({'id':order.pk,'person':order.borrower_id,'title':order.snapshot.get('title') or order.item.title,'photo':f'/media/item/{photos[0].pk}/' if photos else '','applicant':order.borrower.profile.nickname,'applicant_detail':' · '.join(part for part in (order.borrower.profile.major,order.borrower.profile.academic_year) if part),'applicant_url':f'/people/{order.borrower_id}/','start':_stamp(order.start),'end':_stamp(order.end),'days':order.snapshot.get('days',0),'rent':str(order.rent),'deposit':str(order.deposit),'total':str(order.total),'location':order.snapshot.get('location',''),'order_url':f'/orders/{order.pk}/','chat_url':f'/messages/{order.thread.pk}/'})
    return result


def poll(me,params,lang):
    """Badges, a signature that changes when the page should refresh, and anything new since the reader's cursors.

    With no cursors yet (first visit in this browser) nothing pops up: old messages are not news.
    """
    hidden=hidden_people(me)
    fresh=thread_unread(me,hidden)
    memberships=groups.active_memberships(me)
    in_groups=group_unread(me,memberships)
    numbers=counts(me,fresh,in_groups)
    message_cursor=Message.objects.filter(thread__in=my_threads(me)).exclude(sender=me).aggregate(last=Max('pk'))['last'] or 0
    group_cursor=max((groups.visible_messages(row.group,me,row).exclude(sender=me).aggregate(last=Max('pk'))['last'] or 0 for row in memberships),default=0)
    note_cursor=Notification.objects.filter(user=me).aggregate(last=Max('pk'))['last'] or 0
    recalled=Message.objects.filter(thread__in=my_threads(me),recalled=True).count()+BuddyGroupMessage.objects.filter(group_id__in=[row.group_id for row in memberships],recalled=True).count()
    after=[_number(params.get(name)) for name in ('m','g','n')]
    alerts=[]
    if None not in after:
        alerts=_message_alerts(me,after[0],hidden,fresh,lang)+_group_alerts(me,after[1],in_groups,lang)+_note_alerts(me,after[2],lang)
        alerts=sorted(alerts,key=lambda alert:alert['order'],reverse=True)[:POPUPS]
        for alert in alerts: del alert['order']
    return {'unread':numbers,'cursors':{'m':message_cursor,'g':group_cursor,'n':note_cursor},'signature':f"{message_cursor}.{group_cursor}.{note_cursor}.{numbers['total']}.{recalled}",'alerts':alerts,'requests':pending_requests(me,hidden)}


def _order_action(order,owner):
    # The one thing to do next, following the order's state. Only accepting happens right here.
    url=f'/orders/{order.pk}/'
    if order.status=='pending':
        if owner: return {'label':('接受申請','Accept request'),'post':'accept','url':url}
        return {'label':('查看申請','View request'),'url':url}
    if order.status=='accepted':
        if not owner and order.total>0 and not order.rent_borrower: return {'label':('去付款','Pay now'),'url':f'/orders/{order.pk}/pay/'}
        return {'label':('確認交接','Confirm handover'),'url':url}
    if order.status in ('active','return_pending') and not order.is_purchase: return {'label':('確認歸還','Confirm return'),'url':url}
    if order.status=='disputed': return {'label':('查看糾紛','View dispute'),'url':url}
    return {'label':('查看訂單','View order'),'url':url}


def chat_card(thread,me,lang):
    """The item a conversation is about. An order shows the terms agreed when it was made, not today's listing."""
    order=thread.order
    item=order.item if order else thread.item
    if item is None: return None
    photo=item.photos.first()
    card={'photo':f'/media/item/{photo.pk}/' if photo else '','href':f'/items/{item.pk}/','status':''}
    if order:
        card['title']=order.snapshot.get('title') or item.title
        card['status']=i18n.loc(order.status_label)
        if order.is_purchase: card['price']=f'HK$ {order.rent}'
        else:
            per_day=i18n.tr('日','day',lang)
            card['price']=f"HK$ {order.snapshot.get('daily',order.rent)} / {per_day}"
            card['extra']=i18n.tr('押金','Deposit',lang)+f' HK$ {order.deposit} · '+i18n.tr('合共','Total',lang)+f' HK$ {order.total}'
        action=_order_action(order,me.pk==item.owner_id)
    else:
        card['title']=item.title
        if item.is_sale: card['price']=f'HK$ {item.daily}'
        else: card['price']=f"HK$ {item.daily} / {i18n.tr('日','day',lang)}"
        if item.status!='listed': card['status']=i18n.loc(item.get_status_display())
        if me.pk==item.owner_id or item.status!='listed': action={'label':('查看物品','View item'),'url':card['href']}
        elif item.is_sale: action={'label':('查看並購買','View and buy'),'url':card['href']}
        else: action={'label':('申請借用','Request to borrow'),'url':card['href']}
    card['action']={**action,'label':i18n.tr(*action['label'],lang)}
    return card
