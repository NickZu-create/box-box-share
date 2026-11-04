# Order payment page

After a lender accepts an order, the borrower can open `/orders/<id>/pay/` and pay the
lender directly with the QR codes the lender uploaded at `/profile/payment/`. The
platform never collects or holds money and cannot see whether a payment happened, so
the existing two-sided rent and deposit confirmations on the order page stay as they were.

The page shows full **order charges** (rent plus deposit) in HKD, a reference converter, and up to three main
buttons: WeChat Pay, Alipay (a menu with Mainland and Alipay HK) and FPS. Channels the
lender has not set up are not rendered. With no codes the page shows
「暫無可用支付方式」. Free orders show that no payment is needed.

Order charges are **not an outstanding balance**. The existing rent and deposit flags
record each party's self-reported confirmations, not the amounts paid. They are displayed
alongside the charge breakdown, including an explicit warning when both parties have
confirmed. An extension changes the full rent but does not establish what remains unpaid.
Borrowers must agree any amount still due with the lender before paying again. Opening a
QR code, downloading it, or returning to the order never marks a payment as completed.

## Access

QR images are private and served through `/media/payment/<id>/`. Only the lender,
administrators, and borrowers with an accepted, active or return-pending order from that
lender can see them. Restricted lenders' codes are hidden from borrowers.

## Exchange rates

`/fx/hkd/` proxies [ExchangeRate-API's open endpoint](https://www.exchangerate-api.com/docs/free)
because the site's Content-Security-Policy blocks browser requests to other hosts. Rates
update **once a day, so they are not real-time**. The page shows the update time, the
required attribution link and a reference-only note. Results are cached until the
provider's next update; failures are retried after 5 minutes. To use another provider,
change `fetch_rates()` in `market/payments.py` and the `FX_URL` setting.
The provider response must identify HKD as its base, contain finite positive rates,
and supply valid update timestamps. Invalid responses use the same unavailable fallback.

Currencies per channel are in `CHANNEL_CURRENCIES` in `market/payments.py`. Please confirm
them against each channel's current rules.

## Icons and colours

Files are in `market/static/market/pay/`; replacing a file needs no code change.

| File | Status |
|---|---|
| `wechat.svg`, `alipay.svg`, `alipay-cn.svg` | From [simple-icons](https://simpleicons.org) 13.21.0 (CC0 for the files; the marks remain trademarks of their owners) |
| `alipay-hk.png`, `fps.png` | Provided by the project team, resized for the buttons. Source files were small JPEGs; replace with vector or larger artwork if available |

Button colours are CSS variables at the top of `market/static/market/payment.css`.
`--pay-fps` and `--pay-alipay-hk` are sampled from the supplied artwork. Check each brand's
logo rules before public launch.

## Limits

- **Press-and-hold depends on the phone and app.** The QR is a normal image and the long-press
  menu is not blocked, but a website cannot make the app recognise it. In an ordinary browser
  long-press usually only saves the image, so the dialog also offers "Save QR code" and tells
  the borrower to scan it from their photos.
- Press-and-hold and real payments have **not been tested on real phones or with real codes**.
- The server re-encodes uploads but does not check that an image is a valid QR code or belongs
  to the chosen channel. Lenders should check their code still scans; borrowers are told to
  check the recipient before paying. Misuse goes through the existing report flow.
- Using personal receiving codes for rentals may be subject to each channel's own terms.

## Integrated synthetic preview

The latest static showcase exposes the existing paid borrower example at `/hans/orders/3/pay/` and sample receiving-method settings at `/hans/profile/payment/` (also `/en/` and `/zh/`). It reuses the payment-channel artwork and the existing campus design. Sign-in and channel settings are tab-local demonstrations. It contains no real QR payloads, file uploads, app handoffs or payment-state changes. Its fixed example conversion is explicitly not a current exchange rate. See [integration checks](output/payment-review/design-qa.md) and [collaboration setup](COLLABORATION.md).
