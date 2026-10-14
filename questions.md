# Topic

San Francisco commercial real estate market dynamics across four product
types (multifamily, office, industrial, hospitality), told through recent
individual transactions: what traded, who bought and sold, at what price and
yield, and how it was financed.

## Scope

- **Place:** the City and County of San Francisco. Note any deal or market
  figure that covers the wider Bay Area or "SF Peninsula" instead.
- **Time:** "recent" means transactions that closed from October 2024 through
  October 2026. Older deals may be recorded as comparison points but should
  be marked as such in the claim's `period`.
- **Product types:** multifamily (apartments, including mixed-use with ground
  floor retail), office (including life science / lab where a source calls it
  office), industrial (warehouse, flex, PDR, R&D), hospitality (hotels).

## How to record a transaction

`verify.py` checks one number per claim, so each deal becomes several claims
that share the same `subject` prefix, for example
`"550 Example St (office) - price per rentable SF"`. Record each figure as the
source states it (`$412 million`, `$1,050 per square foot`, `5.25%`). Do not
convert units or compute figures the source doesn't print; if only one is
given (e.g. price but not $/SF), leave the other out.

Listings are recorded the same way, with "asking" in the `subject` and `unit`
(e.g. `"1680 Mission St (office) - asking price"`), so asking figures are never
mixed up with closed-sale figures.

Seller, buyer, lender and closing date are not numbers, so the checker cannot
verify them on their own. Put them in the `subject` of the price claim, and
make sure the quoted sentence names them so a person can confirm by reading.

## Field definitions

- **Total transaction price:** the headline sale price. Note if it is a
  partial interest, a portfolio allocation, or includes assumed debt.
- **Price per gross SF:** price divided by gross building area (GSF / GBA).
- **Price per rentable SF:** price divided by net rentable area (RSF / NRA).
  Many sources just say "per square foot" without saying which; record those
  with unit `dollars per square foot (basis not stated)`.
- **Price per unit / per key:** for multifamily (per unit) and hotels (per
  key). Not requested, but usually the standard metric and worth capturing.
- **Cap rate:** going-in (in-place) unless the source says pro forma / stabilized.
  Record which in the `subject`.
- **Loan size:** original principal of the acquisition or refinance loan.
- **Loan-to-value (LTV):** loan / appraised or purchase value.
- **Loan-to-cost (LTC):** loan / total project or acquisition cost (common on
  construction, value-add and conversion deals).
- **Interest rate:** fixed coupon, or floating spread plus index (e.g.
  "SOFR + 300 bps"). Record spread and any stated all-in rate as separate claims.

# Questions

## By transaction (answer for every deal found)

1. What property traded, what product type is it, and when did the sale close
   (or when was it announced, if the close date isn't given)?
2. What was the total transaction price?
3. What was the price per gross square foot?
4. What was the price per rentable square foot?
5. What was the price per unit (multifamily) or per key (hotel)?
6. What was the cap rate, and is it going-in or pro forma?
7. Who was the seller, and who was the buyer?
8. Was the sale distressed (foreclosure, note sale, lender-owned, receiver
   sale, deed in lieu)?
9. How was it financed: loan size, lender, loan-to-value, loan-to-cost, and
   interest rate (fixed rate or spread over index)?

## By product type (market context)

10. **Multifamily:** what are recent San Francisco apartment sale prices per
    unit and per square foot, and what cap rates are deals trading at?
11. **Office:** what are recent office sale prices per square foot, how far
    below prior sale prices or peak valuations are they, and what share of
    recent sales were distressed?
12. **Industrial:** what are recent industrial / PDR sale prices per square
    foot and cap rates?
13. **Hospitality:** what are recent hotel sale prices per key, and what cap
    rates or revenue-per-available-room (RevPAR) figures accompany them?
14. Across all four, what was total San Francisco investment sales volume
    in the most recent quarters, and how did it change from a year earlier?

## Financing environment

15. What loan-to-value and loan-to-cost levels are lenders offering on San
    Francisco acquisitions by product type?
16. What interest rates or spreads are recent San Francisco acquisition and
    refinance loans carrying?

## Listings (properties for sale or lease)

17. What San Francisco properties are currently listed for sale, by product
    type, and at what asking price, asking price per square foot, per unit or
    per key, and asking (in-place or pro forma) cap rate?
18. Who is the seller and listing broker, how occupied is the property, and
    has the asking price been cut or the property relisted?
19. What are asking rents: office and industrial in dollars per square foot
    per year (noting full service or NNN), multifamily in dollars per unit per
    month, and hotel average daily rate where given?
20. How do asking prices and asking cap rates compare with recent closed
    sales of the same product type?
