# Valuation outliers — the 50 worst misses inside the design envelope

**Generated 2026-08-07** from `valuation_backtest.py --price-filter none --property-type House
--min-price 1000000 --max-price 2000000`, n = 641 real sales. Errors are **after** per-suburb
de-biasing, so these are genuine misses, not the known systematic offset.

The worst 10% of properties carry **31% of all absolute error**. 49 of those 64 are homes we
valued **too high**. Themes flagged from the listing text; `canal/waterfront` and `golf` are the
two that appear more in this list than in the rest of the sample, and neither has a working
adjustment (`golf_course_backing` fires on 0 of 4,916 comparables; waterfront is not an attribute).

| # | address | sold for | we said | miss | land | floor | bd/ba | flags |
|---|---|---|---|---|---|---|---|---|
| 1 | [9 Laura Place, Varsity Lakes QLD 4227](https://fieldsestate.com.au/property/9-laura-place-varsity-lakes) | $1,298,000 | $2,141,873 | **+87%** | 458 m² | 163 m² | 4/2 | lake/views |
| 2 | [43 Bayswater Avenue, Varsity Lakes QLD 4227](https://fieldsestate.com.au/property/43-bayswater-avenue-varsity-lakes) | $1,250,000 | $1,742,478 | **+58%** | 350 m² | — | 4/3 | lake/views |
| 3 | [24 Brooklyn Crescent, Robina QLD 4226](https://fieldsestate.com.au/property/24-brooklyn-crescent-robina) | $1,130,000 | $1,708,593 | **+56%** | 131 m² | — | 4/2 | lake/views |
| 4 | [11 Barwon Street, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/11-barwon-street-burleigh-waters) | $1,970,000 | $999,919 | **-47%** | 607 m² | 93 m² | 3/1 | — |
| 5 | [20 Washington Court, Varsity Lakes QLD 4227](https://fieldsestate.com.au/property/20-washington-court-varsity-lakes) | $1,350,000 | $1,733,245 | **+46%** | 417 m² | 154 m² | 4/2 | canal/waterfront, lake/views |
| 6 | [82 Peninsula Drive, Robina QLD 4226](https://fieldsestate.com.au/property/82-peninsula-drive-robina) | $1,210,000 | $1,699,353 | **+45%** | — | 155 m² | 4/3 | — |
| 7 | [41 Kirralee Drive, Robina QLD 4226](https://fieldsestate.com.au/property/41-kirralee-drive-robina) | $1,835,000 | $1,034,525 | **-42%** | — | 218 m² | —/— | — |
| 8 | 6/27 BEACHCOMBER COURT BURLEIGH WATERS QLD 4220 | $1,271,500 | $1,702,228 | **+41%** | — | — | —/— | — |
| 9 | [5 Andorra Place, Varsity Lakes QLD 4227](https://fieldsestate.com.au/property/5-andorra-place-varsity-lakes) | $1,070,000 | $1,297,213 | **+38%** | 350 m² | 200 m² | 4/2 | lake/views |
| 10 | [11 Outrigger Drive, Robina QLD 4226](https://fieldsestate.com.au/property/11-outrigger-drive-robina) | $1,810,000 | $2,417,764 | **+37%** | 796 m² | 413 m² | 6/3 | dual living |
| 11 | [6 Tobago Court, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/6-tobago-court-burleigh-waters) | $1,925,000 | $2,495,249 | **+37%** | — | — | 5/3 | — |
| 12 | [26 Marks Drive, Varsity Lakes QLD 4227](https://fieldsestate.com.au/property/26-marks-drive-varsity-lakes) | $1,330,000 | $1,597,473 | **+36%** | — | 202 m² | 5/2 | lake/views |
| 13 | [22 Homebush Drive, Robina QLD 4226](https://fieldsestate.com.au/property/22-homebush-drive-robina) | $1,887,000 | $1,168,054 | **-36%** | — | 239 m² | —/— | — |
| 14 | [15 Manor Close, Robina QLD 4226](https://fieldsestate.com.au/property/15-manor-close-robina) | $1,716,000 | $2,272,331 | **+36%** | 402 m² | — | 4/2 | canal/waterfront |
| 15 | [2 Whistler Drive, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/2-whistler-drive-burleigh-waters) | $1,700,000 | $2,191,981 | **+36%** | — | 270 m² | 4/2 | — |
| 16 | [16 South Bay Drive, Varsity Lakes, QLD 4227](https://fieldsestate.com.au/property/16-south-bay-drive-varsity-lakes) | $1,250,000 | $1,485,843 | **+35%** | — | — | 3/2 | lake/views |
| 17 | [18 Sea Eagle Drive, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/18-sea-eagle-drive-burleigh-waters) | $1,890,000 | $2,412,109 | **+35%** | — | 248 m² | 5/3 | — |
| 18 | [121 Newport Drive, Robina QLD 4226](https://fieldsestate.com.au/property/121-newport-drive-robina) | $1,472,000 | $937,657 | **-34%** | 792 m² | 174 m² | 2/2 | — |
| 19 | [18 Fairlight Avenue, Robina QLD 4226](https://fieldsestate.com.au/property/18-fairlight-avenue-robina) | $1,115,000 | $1,454,990 | **+34%** | — | — | 3/2 | — |
| 20 | 1/6 BROADVIEW PLACE ROBINA QLD 4226 | $1,040,000 | $1,350,631 | **+34%** | — | — | —/— | — |
| 21 | [11 Robinia Court, Robina QLD 4226](https://fieldsestate.com.au/property/11-robinia-court-robina) | $1,600,000 | $1,031,715 | **-34%** | — | 209 m² | —/— | — |
| 22 | 24 COMORE DRIVE VARSITY LAKES QLD 4227 | $1,195,000 | $1,404,184 | **+33%** | — | — | —/— | — |
| 23 | [101 Dunlin Drive, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/101-dunlin-drive-burleigh-waters) | $1,769,000 | $2,231,818 | **+33%** | 740 m² | 193 m² | 4/2 | — |
| 24 | [16 Eugenia Circuit, Robina QLD 4226](https://fieldsestate.com.au/property/16-eugenia-circuit-robina) | $1,360,000 | $1,754,232 | **+33%** | 645 m² | 236 m² | 5/2 | — |
| 25 | [15 Porto Boulevard, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/15-porto-boulevard-burleigh-waters) | $1,080,000 | $1,358,692 | **+33%** | 200 m² | — | 3/2 | — |
| 26 | [10 Sandpiper Drive, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/10-sandpiper-drive-burleigh-waters) | $2,000,000 | $1,279,775 | **-33%** | 622 m² | 96 m² | 3/1 | — |
| 27 | [5 Goldfinch Avenue, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/5-goldfinch-avenue-burleigh-waters) | $1,700,000 | $1,089,694 | **-32%** | 601 m² | 159 m² | 3/2 | — |
| 28 | [1 Elizabeth Crescent, Varsity Lakes QLD 4227](https://fieldsestate.com.au/property/1-elizabeth-crescent-varsity-lakes) | $1,850,000 | $2,154,198 | **+32%** | — | 292 m² | 4/2 | canal/waterfront, lake/views |
| 29 | [40 Peninsula Drive, Robina QLD 4226](https://fieldsestate.com.au/property/40-peninsula-drive-robina) | $1,230,000 | $1,577,304 | **+32%** | — | — | 3/2 | golf, lake/views |
| 30 | [13 Casablanca Court, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/13-casablanca-court-burleigh-waters) | $1,537,500 | $1,923,235 | **+32%** | 458 m² | 262 m² | 4/2 | — |
| 31 | [112 Cottesloe Drive, Robina QLD 4226](https://fieldsestate.com.au/property/112-cottesloe-drive-robina) | $1,535,000 | $1,018,300 | **-32%** | — | — | —/— | — |
| 32 | [3 Laura Place, Varsity Lakes QLD 4227](https://fieldsestate.com.au/property/3-laura-place-varsity-lakes) | $1,490,000 | $1,722,407 | **+31%** | 459 m² | 164 m² | 5/3 | canal/waterfront, lake/views |
| 33 | [6 Skua Street, Burleigh Waters, QLD 4220](https://fieldsestate.com.au/property/6-skua-street-burleigh-waters) | $2,000,000 | $1,321,790 | **-30%** | — | — | 3/1 | — |
| 34 | [127 Glen Eagles Drive, Robina QLD 4226](https://fieldsestate.com.au/property/127-glen-eagles-drive-robina) | $1,400,000 | $1,772,277 | **+30%** | 867 m² | — | 4/2 | golf |
| 35 | [7 Nypa Close, Robina QLD 4226](https://fieldsestate.com.au/property/7-nypa-close-robina) | $1,710,000 | $2,161,962 | **+30%** | — | 495 m² | 4/2 | lake/views |
| 36 | 1/30 HEIGHTS DRIVE ROBINA QLD 4226 | $1,380,000 | $1,744,676 | **+30%** | — | — | —/— | — |
| 37 | [62 Easthill Drive, Robina QLD 4226](https://fieldsestate.com.au/property/62-easthill-drive-robina) | $1,055,000 | $1,330,676 | **+30%** | — | — | 3/2 | — |
| 38 | [42 Claremont Drive, Robina QLD 4226](https://fieldsestate.com.au/property/42-claremont-drive-robina) | $1,330,000 | $1,677,430 | **+30%** | 528 m² | 152 m² | 4/3 | — |
| 39 | [9 Wisconsin Street, Varsity Lakes QLD 4227](https://fieldsestate.com.au/property/9-wisconsin-street-varsity-lakes) | $1,450,000 | $900,145 | **-30%** | — | 176 m² | —/— | — |
| 40 | [6 Bilgola Place, Robina QLD 4226](https://fieldsestate.com.au/property/6-bilgola-place-robina) | $1,625,000 | $2,042,020 | **+29%** | 740 m² | 146 m² | 4/3 | canal/waterfront, dual living |
| 41 | [60 Ron Penhaligon Way, Robina QLD 4226](https://fieldsestate.com.au/property/60-ron-penhaligon-way-robina) | $1,485,000 | $1,022,533 | **-29%** | — | 196 m² | —/— | — |
| 42 | [5 Palma Crescent, Varsity Lakes QLD 4227](https://fieldsestate.com.au/property/5-palma-crescent-varsity-lakes) | $1,395,000 | $1,581,558 | **+29%** | — | — | 4/2 | lake/views |
| 43 | [28 Rangeview Court, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/28-rangeview-court-burleigh-waters) | $1,570,000 | $1,902,470 | **+28%** | 778 m² | 192 m² | 5/2 | dual living |
| 44 | 2/10 VALBONNE AVENUE VARSITY LAKES QLD 4227 | $1,250,000 | $1,405,484 | **+28%** | — | — | —/— | — |
| 45 | [34 Mountain View Avenue, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/34-mountain-view-avenue-burleigh-waters) | $1,300,000 | $1,567,703 | **+27%** | 598 m² | 128 m² | 4/2 | — |
| 46 | [24 Pymble Place, Robina QLD 4226](https://fieldsestate.com.au/property/24-pymble-place-robina) | $1,280,000 | $1,561,860 | **+26%** | 927 m² | 239 m² | 5/3 | — |
| 47 | [21 Gardendale Crescent, Burleigh Waters QLD 4220](https://fieldsestate.com.au/property/21-gardendale-crescent-burleigh-waters) | $1,700,000 | $2,015,715 | **+25%** | 482 m² | 143 m² | 3/2 | canal/waterfront |
| 48 | [18 Northpoint Close, Robina QLD 4226](https://fieldsestate.com.au/property/18-northpoint-close-robina) | $1,625,000 | $1,972,826 | **+25%** | 532 m² | — | 5/3 | golf |
| 49 | [890 Medinah Avenue, Robina, QLD 4226](https://fieldsestate.com.au/property/890-medinah-avenue-robina-c76e) | $1,300,000 | $1,574,546 | **+25%** | — | — | 3/2 | golf |
| 50 | [5 Castaway Court, Robina QLD 4226](https://fieldsestate.com.au/property/5-castaway-court-robina) | $1,320,000 | $1,598,228 | **+25%** | — | 154 m² | 4/2 | — |

## Read on the split

- **39 of these 50 we valued too HIGH**, 11 too low — the opposite direction to the
  median error, which runs low. Most homes come in slightly under; the big misses overshoot.
- Over-valued outliers sit on a median **530 m²** of land, under-valued on **676 m²**, at the same
  floor area — consistent with the land-size adjustment being under-powered (optimal multiplier 1.25).
- But the effect is weak across the full sample (r = −0.125, and every land quintile runs MAE 9–11%),
  so land size does **not** explain these. They are idiosyncratic — which is why they are worth
  looking at individually.

## What dropping them would buy

| drop the worst… | remaining | MAE | 80% band on $1.6M |
|---|---|---|---|
| nothing | 641 | 10.5% | $524,000 |
| 5% | 609 | 9.0% | $481,000 |
| 10% | 577 | 8.0% | $430,000 |
| 15% | 545 | 7.3% | $383,000 |

⚠ Excluding them from the *accuracy claim* is only honest if they are also excluded from the
*product* — i.e. those homes get `directional_only`, exactly as the design envelope already does
outside $1M–$2M. Dropping them from the measurement alone would be marking our own homework.

See [[valuation_design_envelope]], [[waterfront_out_of_scope]].
