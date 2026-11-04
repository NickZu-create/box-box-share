# Sale, want-to-buy and contact details

These flows began in the static demo (`output/design-preview`) and are now real server features.
The demo's interface was moved into the Django templates; its styles live in
`market/static/market/ui/`. The demo itself is unchanged.

## Listings

`Item.intent` is `rent` or `sale`; `Wanted.intent` is `borrow` or `buy`. A sale's one-off price is
stored in `Item.daily`. The listing type is fixed after publishing, because orders were made under it.

Publishing needs only an amount and a description. The title comes from the description's first
sentence. Rentals default to today through seven days later, Hong Kong time.

## Direct purchase

`services.buy()` locks the item, so only one buyer can win. It creates an `Order` with
`kind='purchase'`, status `accepted`, the price in `rent` and no deposit, and marks the item `sold`.

- There is no seller approval, because the price is fixed.
- The buyer pays the seller directly through the payment page. The platform never handles money.
- The order completes when both sides confirm the handover. There is no return step.
- Before handover either side can cancel, and the item is listed again.
- A sold item cannot be edited. A dispute can still record the handover so an administrator can close it.
- Purchases do not count towards the impact page, and the post-borrow survey is not shown.

A guest can browse and share. Sign-in carries `next`, stored on `LoginToken`, so the emailed link
returns to the item. Only same-site targets are accepted.

## Contact details

`Profile.contact_*` holds optional WhatsApp, phone, WeChat and Instagram details. They never appear
on public pages. `social.contact_state()` decides what a conversation shows, on the server:

- at least 4 non-blank messages in that conversation, with at least one from each person;
- hidden when either person has blocked the other or the other member is restricted.

Group chats do not reveal contact details.

## Sharing

Item cards and pages offer copy link, a WhatsApp composer and the device's share sheet. Requests have
no share control. Nothing is sent by the site. WeChat is reached through the device's share sheet or
a copied link; there is no WeChat integration.

## Not verified

- PostgreSQL: migration `0010` and the purchase race have only run on SQLite here.
- Real phones and in-app browsers, including press-and-hold on QR codes.
- Messages still need a manual refresh, as before.
