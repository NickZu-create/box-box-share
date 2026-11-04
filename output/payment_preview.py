"""Synthetic payment parity over existing showcase orders; never reads private codes."""
import json
import shutil
from copy import deepcopy
from html import escape as E
from pathlib import Path

from bs4 import BeautifulSoup as B


CHANNELS = [('wechat', '微信支付', 'WeChat Pay', 'wechat.svg'),
            ('alipay_cn', '支付宝（内地）', 'Alipay (Mainland)', 'alipay-cn.svg'),
            ('alipay_hk', 'Alipay HK（支付宝香港）', 'Alipay HK', 'alipay-hk.png'),
            ('fps', 'FPS 转数快', 'FPS', 'fps.png')]
COPY = {
    'login': ('演示登录后继续', 'Sign in to the demo to continue'),
    'private': ('收款设置与订单演示需要先登录。不会连接真实账号或支付服务。', 'Sign in to view this sample order or settings. No real account or payment service is connected.'),
    'close': ('关闭', 'Close'),
    'placeholder': ('没有真实收款码，无法付款', 'No real code. No payment is possible.'),
    'sampleCode': ('演示占位 · 不是收款二维码', 'Demo placeholder · Not a payment QR code'),
    'add': ('添加示例渠道', 'Add sample channel'),
    'remove': ('移除示例渠道', 'Remove sample channel'),
    'enabled': ('已设置 · 示例', 'Set up · Sample'),
    'disabled': ('未设置', 'Not set up'),
    'saved': ('示例渠道已更新，仅保存在当前标签页。', 'Sample channel updated in this tab only.'),
    'storage': ('未能保存示例设置，请检查浏览器存储设置。', 'Could not save the sample settings. Check your browser storage settings.'),
    'rate': ('固定示例：1 HKD = 0.85 CNY，非实时汇率。', 'Fixed sample: 1 HKD = 0.85 CNY. This is not a current exchange rate.'),
}


def fragment(markup):
    return B(markup, 'html.parser')


def finalize_payments(out, tr, version):
    """Call after groups, before experience. Adds two routes per language."""
    assets = out / 'preview-assets' / 'pay'
    assets.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent.parent / 'market' / 'static' / 'market' / 'pay'
    for _, _, _, filename in CHANNELS:
        shutil.copy2(source / filename, assets / filename)
    shutil.copy2(source / 'alipay.svg', assets / 'alipay.svg')

    for lang in ('hans', 'zh', 'en'):
        t = lambda z, e: tr(lang, z, e)
        root = '/' + lang + '/'

        def load(route):
            return B((out / lang / route / 'index.html').read_text(encoding='utf-8'), 'html.parser')

        def write(s, route):
            for old in s.select('[data-payment-asset], #payment-copy'):
                old.decompose()
            s.head.append(fragment(f'<link data-payment-asset rel="stylesheet" href="/payment-demo.css?v={version}"><script data-payment-asset defer src="/payment-demo.js?v={version}"></script>'))
            strings = {k: t(*v) for k, v in COPY.items()}
            s.body.append(fragment('<script type="application/json" id="payment-copy">' + json.dumps(strings, ensure_ascii=False).replace('<', '\\u003c') + '</script>'))
            p = out / lang / route / 'index.html'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(s), encoding='utf-8')

        def page(s, route, title, content):
            s = deepcopy(s)
            s.body['data-demo-route'] = route + '/'
            s.body['data-route'] = '/' + route + '/'
            s.body['class'] = list(dict.fromkeys(s.body.get('class', []) + ['payment-preview']))
            for key in ('data-market-screen', 'data-conversation', 'data-peer'):
                s.body.attrs.pop(key, None)
            s.title.string = title + ' · Box Box Share'
            s.main.clear()
            s.main.append(fragment('<section class="page narrow payment-demo-page"><div data-payment-lock></div><div data-payment-content hidden>' + content + '</div></section>'))
            return s

        # Existing #3 is the paid borrower example: Jamie's lantern, On loan, 8 + 100 HKD.
        # Leave pending #1, free #2, and completed/lender #4 unchanged.
        order = load('orders/3')
        pay_url = root + 'orders/3/pay/'
        records = next((h.find_parent(class_='panel') for h in order.select('main h2')
                        if h.get_text(' ', strip=True) in ('Offline payment records', '线下付款记录', '線下付款紀錄', '线下付款紀錄')), None)
        if records is None:
            # The translated export may use another spelling; locate the existing rent action.
            action = order.select_one('button[value="rent"]')
            records = action.find_parent(class_='panel') if action else None
        if records is not None:
            records['id'] = 'payment-records'
            if not records.select_one('[data-payment-entry]'):
                h = records.find('h2')
                entry = fragment('<p class="payment-demo-entry"><a class="button" data-payment-entry href="' + pay_url + '">' + t('查看付款方式 · 示例', 'View payment methods · Sample') + ' →</a></p>')
                h.insert_after(entry) if h else records.insert(0, entry)
        write(order, 'orders/3')

        options = ''
        for channel, z, e, filename in CHANNELS:
            if channel in ('alipay_cn', 'alipay_hk'):
                continue
            options += '<button type="button" class="payment-channel payment-' + channel + '" data-payment-channel="' + channel + '"><img src="/preview-assets/pay/' + filename + '" alt="" width="24" height="24"><span>' + E(t(z, e)) + '</span></button>'
        alipay = '<details class="payment-alipay-menu"><summary class="payment-channel payment-alipay"><img src="/preview-assets/pay/alipay.svg" alt="" width="24" height="24"><span>Alipay</span><span class="payment-chevron" aria-hidden="true"></span></summary><div class="payment-alipay-options">'
        for channel, z, e, filename in CHANNELS[1:3]:
            alipay += '<button type="button" data-payment-channel="' + channel + '"><img src="/preview-assets/pay/' + filename + '" alt="" width="24" height="24"><span>' + E(t(z, e)) + '</span></button>'
        alipay += '</div></details>'
        # Keep the three-channel grouping from the real payment page.
        options = options.replace('<button type="button" class="payment-channel payment-fps"', alipay + '<button type="button" class="payment-channel payment-fps"')
        back = root + 'orders/3/'
        content = '<a class="breadcrumb" href="' + back + '">← ' + t('借用订单', 'Borrowing order') + ' #3</a><div class="payment-title"><div><span class="eyebrow">BOX BOX SHARE / DEMO</span><h1>' + t('付款方式', 'Payment methods') + '</h1></div><span class="pill">' + t('借用中 · 示例', 'On loan · Sample') + '</span></div><p class="hint">' + t('露营灯 · 物主 Jamie', 'Camping lantern · Lender Jamie') + '</p>'
        content += '<section class="panel payment-summary"><small>' + t('订单费用总额（非待付余额）', 'Order charges (not an outstanding balance)') + '</small><strong class="payment-total">HK$ 108.00</strong><dl><dt>' + t('租金', 'Rent') + '</dt><dd>HK$ 8.00</dd><dt>' + t('押金', 'Deposit') + '</dt><dd>HK$ 100.00</dd></dl><p class="hint">' + t('此处展示订单租金加押金，不会核实已付款项。请先与物主核对双方付款记录，避免重复付款。', 'This is the rent plus deposit, without verification of payments already made. Check both parties’ payment records with the lender before paying again.') + '</p><div class="payment-converter"><label for="payment-currency">' + t('示例金额换算', 'Sample amount conversion') + '</label><select id="payment-currency" data-payment-currency><option value="HKD">HKD</option><option value="CNY">CNY</option></select><output data-payment-converted for="payment-currency" aria-live="polite">HK$ 108.00</output><p class="hint" data-payment-rate>' + t(*COPY['rate']) + '</p></div></section>'
        content += '<section class="panel payment-options"><h2>' + t('选择付款方式', 'Choose a payment method') + '</h2><div class="payment-channels">' + options + '</div><p class="hint">' + t('所有渠道均为示例，没有真实收款码。正式功能由借用人直接付给物主，平台不收款、不托管，也不会核实付款。', 'All channels are examples without real codes. In the real feature, borrowers pay lenders directly. The platform does not collect, hold or verify payments.') + '</p><a class="text-link" href="' + back + '#payment-records">' + t('返回订单核对双方付款记录', 'Back to check both parties’ payment records') + ' →</a></section>'
        content += '<dialog class="payment-demo-dialog" aria-labelledby="payment-dialog-title"><button type="button" class="payment-close" data-payment-close aria-label="' + t(*COPY['close']) + '">×</button><h2 id="payment-dialog-title"></h2><p class="payment-dialog-amount">HK$ 108.00</p><div class="payment-placeholder"><span aria-hidden="true">DEMO</span><strong>' + t(*COPY['sampleCode']) + '</strong></div><p class="notice">' + t(*COPY['placeholder']) + '</p><p class="hint">' + t('此演示不会跳转支付 App，不提供扫码、保存收款码或标记已付款操作。', 'This demo cannot open a payment app, provide a payment code or mark the order paid.') + '</p><button type="button" class="button secondary" data-payment-close>' + t(*COPY['close']) + '</button></dialog>'
        pay = page(order, 'orders/3/pay', t('付款方式 · 示例', 'Payment methods · Sample'), content)
        write(pay, 'orders/3/pay')

        profile = load('profile')
        summary = profile.select_one('.experience-account-summary') or profile.select_one('main .panel')
        if summary and not summary.select_one('[data-payment-entry]'):
            summary.append(fragment('<a class="text-link payment-profile-link" data-payment-entry href="' + root + 'profile/payment/">' + t('管理收款方式 · 示例', 'Manage payment methods · Sample') + ' →</a>'))
        write(profile, 'profile')
        content = '<a class="breadcrumb" href="' + root + 'profile/">← ' + t('个人资料', 'Your profile') + '</a><span class="eyebrow">BOX BOX SHARE / DEMO</span><h1>' + t('收款方式', 'Receiving methods') + '</h1><p class="hint">' + t('这里只演示添加与移除渠道，不上传任何图片或真实收款信息。设置属于 Demo，不会改变 Jamie 的示例付款方式。', 'Try adding and removing sample channels. No images or real receiving details are uploaded. These settings belong to Demo and do not change Jamie’s sample methods.') + '</p><div class="payment-settings-grid">'
        for channel, z, e, filename in CHANNELS:
            content += '<section class="panel payment-setting" data-payment-setting="' + channel + '"><h2><span class="payment-setting-icon payment-' + channel + '"><img src="/preview-assets/pay/' + filename + '" alt="" width="24" height="24"></span>' + E(t(z, e)) + '</h2><p class="hint" data-payment-setting-status></p><div class="payment-setting-placeholder" hidden>' + t(*COPY['sampleCode']) + '</div><button type="button" class="button secondary" data-payment-setting-toggle></button></section>'
        content += '</div><p class="payment-settings-status" role="status" aria-live="polite" data-payment-settings-status></p><p class="notice">' + t('正式功能会在物主接受订单后，向符合权限的借用人展示物主已上传的渠道；这里只保存在当前标签页，重置演示后清空。', 'The real feature shows the lender’s configured channels only to eligible borrowers after acceptance. This sample stays in this tab and resets with the demo.') + '</p>'
        settings = page(profile, 'profile/payment', t('收款方式 · 示例', 'Receiving methods · Sample'), content)
        write(settings, 'profile/payment')
