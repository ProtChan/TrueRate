# TrueRate

TrueRate is a static FX total-return dashboard that separates common market movement from each broker's actual swap cashflow.

Supported brokers/products:

- **楽天FX**
- **DMM FX**
- **DMM FX Mini**
- **DMM FX Large**
- **くりっく365**
- **松井証券FX**
- **FXブロードネット**
- **みんなのFX**
- **みんなのFX LIGHT**
- **LIGHT FX**
- **LIGHT FX LIGHT**
- **SBI FXトレード**
- **ヒロセ通商 LION FX**
- **JFX MATRIX TRADER**
- **外為どっとコム（外貨ネクストネオ）**
- **GMO外貨**
- **GMOクリック証券（FXネオ）**
- **トライオートFX**

## Core rule: swap is effective on the following business day

Broker calendars publish swap against a Japanese transaction/calendar date. TrueRate preserves that source date as `trade_date`, but the return series uses:

~~~text
effective_date = next business day after trade_date
~~~

For the default broker rule, a weekday display date moves to the next weekday, so Friday moves to Monday. SBI FX Trade is the exception: its display date itself is used, with weekend display dates rolled to Monday.

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

- 楽天FX: official public latest swap feed; TrueRate accumulates the daily published values
- DMM FX / Mini / Large: official public swap-calendar JSON API
- くりっく365: 東京金融取引所 official historical FX CSV (swap point)
- 松井証券FX: official yearly swap-history CSV
- FXブロードネット: official monthly swap-calendar PDF
- みんなのFX / LIGHT: official public rolling swap calendar
- LIGHT FX / LIGHT: official public rolling swap calendar
- SBI FXトレード: official monthly swap-history endpoint
- ヒロセ通商 LION FX: official historical swap CSV
- JFX MATRIX TRADER: official historical swap CSV
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
  brokers/rakuten_fx.py  楽天FX public latest-swap collector
  brokers/dmm_fx.py      DMM FX / Mini / Large rolling API collector
  brokers/click365.py    くりっく365 TFX historical collector
  brokers/matsui_fx.py   松井証券FX yearly CSV collector
  brokers/fxbroadnet.py FXブロードネット monthly PDF collector
  brokers/minfx.py       みんなのFX + LIGHT rolling-calendar parser
  brokers/lightfx.py     LIGHT FX + LIGHT rolling-calendar collector
  brokers/sbi_fx.py      SBI FXトレード monthly-history collector
  brokers/hirose.py      ヒロセ通商 historical CSV collector
  brokers/jfx.py         JFX historical CSV collector
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

- 楽天FX imports the official latest-value feed and accumulates history daily in TrueRate
- DMM FX / Mini / Large import the public rolling API (roughly the latest two months) and then accumulate history daily in TrueRate
- くりっく365 backfills from `2021-01`
- 松井証券FX backfills from `2023-01`
- FXブロードネット backfills from `2023-10`
- みんなのFX / LIGHT and LIGHT FX / LIGHT import their public rolling calendars and accumulate history daily in TrueRate
- SBI FXトレード backfills from `2021-01`
- ヒロセ通商 LION FX uses official CSV history from `2021-01`
- JFX MATRIX TRADER uses official CSV history from `2021-01`
- 外為どっとコム backfills from `2022-01`
- GMO外貨 backfills from `2022-01`
- GMOクリック証券 backfills from `2024-01`
- トライオートFX backfills from `2024-01`

After the initial backfill, monthly-history brokers refresh their recent months. 楽天FX, DMM FX and みんなのFX/LIGHT系 refresh their official rolling data and merge those rows into TrueRate's retained history. Historical confirmed values are preserved, reference rates are updated, the site payload is rebuilt, and GitHub Pages is deployed in the same workflow.

Historical starts can be changed with:

~~~text
TRUERATE_CLICK365_START_MONTH=YYYY-MM
TRUERATE_MATSUI_START_MONTH=YYYY-MM
TRUERATE_FXBROADNET_START_MONTH=YYYY-MM
TRUERATE_GAITAME_START_MONTH=YYYY-MM
TRUERATE_START_MONTH=YYYY-MM
TRUERATE_GMO_CLICK_START_MONTH=YYYY-MM
TRUERATE_TRIAUTO_START_MONTH=YYYY-MM
TRUERATE_SBI_START_MONTH=YYYY-MM
TRUERATE_HIROSE_START_MONTH=YYYY-MM
TRUERATE_JFX_START_MONTH=YYYY-MM
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
swap_currency
status
source
fetched_at
~~~

The site-data schema is broker-keyed by currency pair, so additional brokers automatically fit the comparison chart.


### Non-JPY swap cashflows

Some official broker CSVs publish cross-pair swap in the pair's quote currency rather than JPY.
TrueRate stores that currency in `swap_currency` and converts the cashflow to JPY on the
effective date using the same daily reference-rate set used by the spot component.
