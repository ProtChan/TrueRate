# TrueRate

TrueRate is a static FX total-return dashboard that separates common market movement from each broker's actual swap cashflow.

Supported brokers:

- **みんなのFX**
- **外為どっとコム（外貨ネクストネオ）**
- **GMO外貨**
- **GMOクリック証券（FXネオ）**
- **トライオートFX**

## Core rule: swap is effective on the following JST day

Broker calendars publish swap against a Japanese transaction/calendar date. TrueRate preserves that source date as `trade_date`, but the return series uses:

~~~text
effective_date = trade_date + 1 calendar day
~~~

This is deliberate. Rollover happens around the New York close, which is the following morning in Japan. A swap shown for 2026-09-09 therefore enters the TrueRate daily index on 2026-09-10.

A populated amount is only marked `confirmed` once its `effective_date` has arrived in JST. Future populated values remain `scheduled`.

## Return model

For a fixed 10,000-base-currency position:

~~~text
Long total PnL JPY
  = Base units × (current spot - start spot) × current quote/JPY
  + confirmed long swap cashflow since the selected start

Short total PnL JPY
  = -Base units × (current spot - start spot) × current quote/JPY
  + confirmed short swap cashflow since the selected start

Total Return Index
  = 100 + Total PnL JPY / initial base-currency notional in JPY × 100
~~~

The browser rebases broker-to-broker comparisons to a shared visible start date. Spot-only is generated independently from the selected broker with the longest available history, so MAX can retain the longest market-only comparison even when other brokers have shorter histories.

## Data sources

- みんなのFX: official public rolling one-month swap calendar
- 外為どっとコム: official monthly FX swap CSV
- GMO外貨: official swap calendar
- GMOクリック証券 FXネオ: official historical swap calendar
- トライオートFX: official monthly swap-calendar backend and settlement-day backend
- Common FX reference rate: Frankfurter v2 blended official-source rates
- Broker-specific Bid/Ask and spread are intentionally excluded from the spot component

Triauto's public calendar reports swap values per 10,000 currency units. Its backend returns each monthly swap row as sell/buy cashflow plus a separate official swap-day count. Internal `*_AP` rows and non-public/legacy pairs are excluded.

## Repository layout

~~~text
.github/workflows/
  ci.yml                 unit tests
  update-data.yml        daily collection + Pages deployment
  pages.yml              manual/source-change Pages deployment

scripts/
  update_data.py         incremental collection/build pipeline

src/truerate/
  brokers/minfx.py       みんなのFX rolling-calendar collector
  brokers/gaitame_com.py 外為どっとコム collector
  brokers/gmo_gaika.py   GMO外貨 collector
  brokers/gmo_click.py   GMOクリック証券 collector
  brokers/triauto.py     トライオートFX collector
  rates/frankfurter.py   common daily FX reference rates
  series.py              normalized site-data builder
  models.py              normalized swap record

data/
  swaps/                 normalized broker histories
  rates/                 cached reference-rate history

site/
  index.html
  app.js
  styles.css
  data/site-data.json    generated dashboard payload
~~~

## Automatic refresh

The data workflow runs every day at **09:15 JST**.

On a new data set:

- みんなのFX imports the public rolling calendar (officially limited to the most recent month) and then accumulates history daily in TrueRate
- 外為どっとコム backfills from `2022-01`
- GMO外貨 backfills from `2022-01`
- GMOクリック証券 backfills from `2024-01`
- トライオートFX backfills from `2024-01`

After the initial backfill, monthly-history brokers refresh their recent months. みんなのFX refreshes its official rolling one-month calendar and merges those rows into TrueRate's retained history. Historical confirmed values are preserved, reference rates are updated, the site payload is rebuilt, and GitHub Pages is deployed in the same workflow.

Historical starts can be changed with:

~~~text
TRUERATE_GAITAME_START_MONTH=YYYY-MM
TRUERATE_START_MONTH=YYYY-MM
TRUERATE_GMO_CLICK_START_MONTH=YYYY-MM
TRUERATE_TRIAUTO_START_MONTH=YYYY-MM
~~~

## Run locally

~~~bash
pip install -r requirements.txt
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/update_data.py
python -m http.server 8000 --directory site
~~~

Then open `http://localhost:8000`.

To force a full refresh:

~~~bash
python scripts/update_data.py --full --gaitame-start 2022-01 --start 2022-01 --gmo-click-start 2024-01 --triauto-start 2024-01
~~~

## Adding another broker

Add a collector that produces the normalized fields:

~~~text
broker
pair
trade_date
effective_date
sp_days
long_swap_jpy
short_swap_jpy
unit
status
source
fetched_at
~~~

The site-data schema is broker-keyed by currency pair, so additional brokers automatically fit the comparison chart.
