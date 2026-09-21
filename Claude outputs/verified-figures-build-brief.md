# Build brief: compare100 verified figures, full file

Hand this whole document to whatever builds the file. It is written to be followed
literally. Every row produced will be audited against the page it claims to come from,
and the audit rules are in section 14 so there are no surprises.

---

## 1. The job

Produce a CSV of every published, dated figure on compare100.com, one row per figure,
drawn only from the 111 rewritten pages. The file is a citation surface for journalists
and answer engines. Its single promise is that every row can be traced back to a page
that already prints it, on the date shown.

Expected size: about **1,270 rows maximum** (1,239 key facts plus 29 headline figures),
plus any additional figures taken from section prose. A file of 600 honest rows is worth
more than 1,300 with ten invented ones.

---

## 2. Source of truth and scope

- **In scope:** all 111 pages listed in `page-reference.txt`, which gives every page's
  slug, section, title and verification date. Use those four values as given. Do not
  re-derive them and do not guess a date.
- **Where figures may come from:** the page's headline figure, its key facts table, and
  its section prose. Anywhere on the page counts, provided the page actually prints it.
- **Out of scope:** anything not on a compare100 page. No provider website, no PDF, no
  other comparison site, no search result.

---

## 3. Batch plan

Build and submit **one section at a time**, largest first, in this order:

1. Travel Insurance
2. Car Insurance Deals and the other insurance sections
3. Savings, ISAs, Current Accounts, Loans, Credit Cards
4. Motoring: HPI Checks, Vehicle Inspections, Servicing, Tyres, Sell My Car
5. Travel: Airport Parking, Airport Lounge, Hotels, Hostels, Ferries, Trains, Boating
6. Telecoms, Broadband, Mobiles, Energy, Retail, everything remaining

Each batch is checked before the next is built. A fault found in a 90 row batch is a five
minute fix. The same fault repeated across 1,270 rows is a rebuild.

---

## 4. What earns a row

One row per figure, per tier, per page.

- A fact with one value is one row.
- A fact covering several tiers is **one row per tier**, with the `tier` column filled.
- A fact with no number in it still earns a row if it identifies the product or the firm:
  the underwriter, the legal entity, the governing law. Leave the numeric columns empty.
- A figure stated twice on the same page is one row, not two.

---

## 5. The nineteen columns

Header line, exactly:

```
row_id,section,page_slug,provider_or_product,source_url,metric_key,metric_label,metric_value_text,value_numeric,value_min,value_max,unit,tier,source_type,verification_date,is_headline,confidence,figure_status,notes
```

| column | rule |
|---|---|
| `row_id` | `<page_slug>__<metric_key or short label>__<tier>`, lower case, no spaces. Must be unique across the whole file. It is how week-to-week changes get diffed, so keep it stable between rebuilds. |
| `section` | Copy from `page-reference.txt`. Do not invent new section names. |
| `page_slug` | Copy from `page-reference.txt`. **Required on every row.** Without it the row cannot be audited and will be rejected. |
| `provider_or_product` | Copy the page title from `page-reference.txt`. |
| `source_url` | `https://compare100.com/<page_slug>/` and nothing else. No affiliate links, no query strings, no tracking. |
| `metric_key` | One of the 25 keys in section 6, or **empty**. An empty key is fine and honest. A wrong key is not. |
| `metric_label` | The label as the page words it. Do not tidy it. |
| `metric_value_text` | **The value exactly as published on the page**, with HTML tags stripped and entities decoded. This is the field the audit searches for. Never reword, round, summarise or translate it. If the page says "Up to £20 million", this column says "Up to £20 million". |
| `value_numeric` | The single number the value reduces to, digits only, no commas or symbols. Fill **only** when the value is one unambiguous number. `£5m` gives `5000000`. Otherwise leave empty. |
| `value_min` / `value_max` | Only for a genuine range. `£10m to unlimited` gives min `10000000` and an empty max. Two separate prices are not a range, so leave all three numeric columns empty. |
| `unit` | One of the values in section 7. |
| `tier` | The tier or product level as the page names it (Basic, Silver, Gold, Plus, Platinum). Empty where the page names none. |
| `source_type` | One of the three values in section 8. This is not optional. |
| `verification_date` | Copy from `page-reference.txt`. ISO format, `YYYY-MM-DD`. It must equal the page's own checked date. This is the column that goes wrong most often. |
| `is_headline` | `true` only on the page's headline figure, and only for the 29 pages marked `yes` in `page-reference.txt`. Everything else is `false`. |
| `confidence` | Per the rules in section 9. It must vary. A file where every row says `high` fails review. |
| `figure_status` | Per section 10. |
| `notes` | Per row, and about **that** row. Empty unless there is something specific to say. Do not repeat a provider-level sentence down every row. |

---

## 6. Controlled vocabulary for `metric_key`

```
emergency_medical      policy_excess          cancellation           baggage
personal_liability     trip_length_days       age_limit              fca_firm_reference
company_number         underwriter            cooling_off_days       admin_fee
price_from             unit_rate              standing_charge        aer_rate
price_per_day          per_visit_fee          defaqto_rating         which_score
fos_cases              fscs_cover             network_size           trading_since
complaint_window
```

Two notes:

- It is **`policy_excess`, never `medical_excess`.** The pages describe a standard policy
  excess that applies per person per section claimed. Calling it a medical excess asserts
  something the pages do not say. This was the one real accuracy error in the first file.
- If nothing fits, leave `metric_key` empty and let `metric_label` carry the meaning.
  Forcing a fact into the nearest box is worse than leaving the box empty.

---

## 7. Values for `unit`

```
GBP   GBP_per_month   GBP_per_day   percent   days   years   count   stars   identifier
```

Leave empty for a value with no unit, such as an underwriter's name. Use `identifier` for
FCA firm references, company numbers and similar, and leave `value_numeric` empty for
those: a firm reference is a name, not a quantity.

---

## 8. Values for `source_type`

| value | when |
|---|---|
| `own_review` | Compare100 read this figure in the provider's own published terms. The default. |
| `panel_listing` | The figure was read off a comparison site's panel, not the insurer's own wording. Every figure on the Quotezone and Compare Your Travel Insurance pages that describes a **third party's** product is this. |
| `third_party_rating` | A rating or score awarded by somebody else: Defaqto, Which?, Citizens Advice, the Financial Ombudsman. |

This column exists because the first file presented panel figures as verified Compare100
figures. A reporter who checks one with the insurer and finds a difference has found a
problem on compare100.com. Labelling it removes the risk entirely and costs nothing.

---

## 9. Rules for `confidence`

- `high` — a single unambiguous figure, printed plainly on the page, `source_type` is
  `own_review`.
- `medium` — the figure is on the page but qualified: an open-ended range, an "up to", a
  figure that depends on the scheme you are given, or anything with `source_type` of
  `panel_listing`.
- `needs_reverify` — the page hints at the figure without stating it, or the value is
  older than twelve months, or the tier mapping is not explicit on the page.

If a row would need `needs_reverify`, prefer to leave the row out. An absent row costs
nothing. A doubtful row costs the credibility of every row around it.

---

## 10. Rules for `figure_status`

- `current` — the verification date is within the last six months.
- `ageing` — older than six months.

Nothing is deleted for being old. It is labelled.

---

## 11. Splitting rules

**Per-tier facts.** `£5m (Basic) · £10m (Silver) · £15m (Gold and Lifetime)` becomes four
rows, one per tier. Each row's `metric_value_text` is the **exact fragment for that tier as
printed**, so `£5m (Basic)`, not a rewritten `£5,000,000 for the Basic tier`. Where one
fragment covers two tiers, write a row for each and repeat the fragment.

**Prose tables.** Where a page lists tiers in a sentence, for example `Excess per claim:
£150, £100, £75 and £50` alongside `Standard, Enhanced, Prime and Supreme`, the mapping is
explicit and may be split. Where the page gives only endpoints, for example `£1,000 on
Standard Plus rising to £6,000 on Platinum`, **only those two rows exist**. Do not fill in
the middle.

**Ranges.** Fill `value_min` and `value_max`. Leave `value_numeric` empty. If one end is
open, such as "to unlimited", leave that end empty and set `confidence` to `medium`.

**Several numbers that are not a range.** `£14.99 for one, or £29.99 for five (£6.00 each)`
leaves all three numeric columns empty. `metric_value_text` carries the whole thing.

---

## 12. Never

- Never print a figure that is not on the page. Not from the provider's site, not from
  memory, not from a plausible pattern in the surrounding tiers.
- Never calculate. No averages, no totals, no per-month from per-year, no rankings, no
  "cheapest" or "best".
- Never reword `metric_value_text`. A rewritten value is indistinguishable from an
  invented one at audit time, and both get rejected.
- Never present another company's panel listing as a Compare100 verified figure.
- Never put an affiliate or tracking URL in `source_url`.
- Never put a range, a word or a symbol in a numeric column.
- Never claim FCA authorisation, Ofcom accreditation or any ranking the site does not
  already publish with a source.
- Never fill a gap with a guess in order to finish a tier ladder. An incomplete ladder is
  a true ladder.

---

## 13. Worked examples

These eight rows are real, taken from live pages, and all eight pass the audit unchanged.
Use them as the pattern.

```csv
row_id,section,page_slug,provider_or_product,source_url,metric_key,metric_label,metric_value_text,value_numeric,value_min,value_max,unit,tier,source_type,verification_date,is_headline,confidence,figure_status,notes
loungekey-airport-lounge__per_visit_fee__monzo,Airport Lounge,loungekey-airport-lounge,LoungeKey Airport Lounge,https://compare100.com/loungekey-airport-lounge/,per_visit_fee,Typical UK card rate,£24 per person per visit (Monzo Premium and Monzo Max),24,,,GBP,,own_review,2026-09-21,false,high,current,
aa-car-check__price_from__headline,HPI Checks,aa-car-check,AA Car Check,https://compare100.com/aa-car-check/,price_from,Cheapest full check,"£14.99 for one full check, or £29.99 for five (£6.00 each)",,,,GBP,,own_review,2026-09-21,true,high,current,Three prices in one fact and not a range
aviva-travel-insurance-review__emergency_medical__basic,Travel Insurance,aviva-travel-insurance-review,Aviva Travel Insurance Review,https://compare100.com/aviva-travel-insurance-review/,emergency_medical,Emergency medical,£5m (Basic),5000000,,,GBP,Basic,own_review,2026-08-16,false,high,current,
aviva-travel-insurance-review__policy_excess__basic,Travel Insurance,aviva-travel-insurance-review,Aviva Travel Insurance Review,https://compare100.com/aviva-travel-insurance-review/,policy_excess,Standard excess,£150 (Basic),150,,,GBP,Basic,own_review,2026-08-16,false,high,current,Standard policy excess and not medical only
quotezone-travel-insurance-review__fca_firm_reference,Travel Insurance,quotezone-travel-insurance-review,Quotezone Travel Insurance Review,https://compare100.com/quotezone-travel-insurance-review/,fca_firm_reference,FCA reference,313860,,,,identifier,,own_review,2026-08-19,false,high,current,
saga-travel-insurance-review__defaqto_rating,Travel Insurance,saga-travel-insurance-review,Saga Travel Insurance Review,https://compare100.com/saga-travel-insurance-review/,defaqto_rating,Defaqto rating,5 stars,5,,,stars,,third_party_rating,2026-08-16,false,high,current,Defaqto and not our own score
quotezone-travel-insurance-review__emergency_medical__panel,Travel Insurance,quotezone-travel-insurance-review,Quotezone Travel Insurance Review,https://compare100.com/quotezone-travel-insurance-review/,emergency_medical,Emergency medical limits,£10m to unlimited across the specialist insurers listed,,10000000,,GBP,,panel_listing,2026-08-19,false,medium,current,Upper end open and read off the panel not the insurer wording
coverwise-travel-insurance__underwriter,Travel Insurance,coverwise-travel-insurance,Coverwise Travel Insurance,https://compare100.com/coverwise-travel-insurance/,underwriter,Underwritten by,"Inter Partner Assistance S.A. UK Branch (AXA Group, firm reference 202664) or AWP P&C S.A. (Allianz, firm reference 534384) depending on the scheme",,,,,,own_review,2026-09-18,false,high,current,
```

---

## 14. The audit each batch faces

Every row is checked by script against the JSON the site is built from. A row fails if:

1. `page_slug` is missing, or is not one of the 111.
2. `metric_value_text` cannot be found on that page. Entities are decoded and commas are
   folded first, so `20000000` matches `£20,000,000`, but a reworded value will not match.
3. `verification_date` is not that page's own checked date.
4. `source_url` does not contain the slug, or carries a query string.
5. `metric_key` is outside the vocabulary, or `unit`, `source_type` or `confidence` is
   outside its allowed set.
6. A numeric column holds something that is not a plain number, or a number that cannot be
   derived from `metric_value_text`. Suffixes are expanded, so `£5m` satisfies `5000000`.
7. `is_headline` is `true` on a page that has no headline figure.
8. The `row_id` repeats, or the same page, label, value and tier appear twice.

The report also lists any of the 111 pages that produced no rows at all, so gaps are
visible rather than silent.

---

## 15. Delivery

One file per batch, CSV, UTF-8, with the header line exactly as in section 5. Quote any
field containing a comma. A Google Drive link is fine.
