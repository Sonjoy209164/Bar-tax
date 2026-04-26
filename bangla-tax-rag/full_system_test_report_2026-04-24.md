# Full System Test Report

- Run time: `2026-04-24 22:56:42`
- Backend: `http://127.0.0.1:4893`
- Sample dataset version: `demo-2026-04-19`
- Health: `ok`
- Inventory after reseed: `60` items, `60` vectors
- Business after reseed: `60` signals across `60` products
- Sync ready: `True`
- Production ready: `False`

## Reseed Actions

- Cleared old products: `60`
- Cleared old business signals: `60`
- Upserted sample products: `60`
- Upserted sample business signals: `60`
- Rebuild result: `ready=True`, `rebuilt_count=60`, `vector_record_count=60`

## Summary

- Cases passed bundled expectations: `7/15`
- Audience used for routing: `manager`
- Routing mode: `prefer_fast_response=true`, `allow_agentic=true`
- Delivery mode used for capture: `streaming SSE`, with final payload recorded in this report

| # | Label | Routed | Engine | Hits | Abstained | Result |
|---|---|---|---|---:|---|---|
| 1 | Exact watch search | `ask` | `deterministic` | 4 | `False` | PASS |
| 2 | Premium headphones | `ask` | `deterministic` | 2 | `False` | PASS |
| 3 | Laptop cross-sell | `ask` | `deterministic` | 5 | `False` | FAIL |
| 4 | Business restock | `agentic` | `deterministic` | 9 | `False` | FAIL |
| 5 | No bike abstention | `ask` | `deterministic` | 0 | `True` | PASS |
| 6 | Budget earbuds | `ask` | `deterministic` | 1 | `False` | PASS |
| 7 | Student laptop | `ask` | `deterministic` | 2 | `True` | PASS |
| 8 | Creator bundle | `ask` | `deterministic` | 0 | `True` | FAIL |
| 9 | Standing desk cross-sell | `ask` | `deterministic` | 3 | `False` | FAIL |
| 10 | Wi-Fi coverage fix | `ask` | `deterministic` | 5 | `False` | FAIL |
| 11 | Portable storage | `ask` | `natural` | 3 | `False` | FAIL |
| 12 | Phone travel add-ons | `agentic` | `deterministic` | 10 | `False` | FAIL |
| 13 | Restock by demand and low inventory | `agentic` | `deterministic` | 9 | `False` | PASS |
| 14 | No refrigerator abstention | `ask` | `deterministic` | 0 | `True` | PASS |
| 15 | Premium monitor | `ask` | `deterministic` | 4 | `False` | FAIL |


## Case Responses

## 1. Exact watch search

- Question: `show me some watches`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `exact_lookup`
- Answer engine chosen: `deterministic`
- Total hits: `4`
- Abstained: `False`
- Recommended product IDs: `[]`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['watch-pulseline-lite', 'watch-trailmark-pro', 'watch-summit-x', 'watch-citypulse-classic']`
- Trace: `2ca9302e-1538-4cdc-9c51-f9a8e5a5ae45` via `/inventory/chat/trace/2ca9302e-1538-4cdc-9c51-f9a8e5a5ae45`
- Validation result: `PASS`

### Answer


```text
I found 4 matching product(s). The strongest matches are PulseLine Lite Watch (USD 129.00, 18 in stock, PulseLine), TrailMark Pro Smart Watch (USD 219.00, 6 in stock, TrailMark), and Summit X Adventure Watch (USD 299.00, 7 in stock, Summit). There are 1 more relevant option(s) behind those.
```


## 2. Premium headphones

- Question: `Recommend premium wireless headphones under 300 for office calls`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `recommendation`
- Answer engine chosen: `deterministic`
- Total hits: `2`
- Abstained: `False`
- Recommended product IDs: `['seed-audio-001', 'audio-bassforge-dj']`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['seed-audio-001', 'audio-bassforge-dj']`
- Trace: `2705fb05-d211-4d4a-82b1-d83317ac4fef` via `/inventory/chat/trace/2705fb05-d211-4d4a-82b1-d83317ac4fef`
- Validation result: `PASS`

### Answer


```text
I would lead with Auralite Flex ANC Headphones. It is the strongest budget-friendly match in the current catalog. It stays within the requested value range at USD 249.00. It currently has 14 unit(s) in stock. It sits in Audio under Auralite. The product description highlights Wireless over-ear headphones with active noise cancellation for focused office calls and travel. Structured details include connectivity: Bluetooth 5.3; battery life: 35 hours; use case: office calls. If the customer wants to step up from Auralite Flex ANC Headphones, the next option to show is BassForge DJ Monitor Headphones at USD 149.00. I am keeping this recommendation grounded in the current catalog only, so I am not claiming anything that is not in the stored product data. Are we selling into Audio? Also tell me whether the buyer cares more about budget, premium feel, or immediate availability.
```


## 3. Laptop cross-sell

- Question: `What can I bundle with the Nimbus laptop?`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `recommendation`
- Answer engine chosen: `deterministic`
- Total hits: `5`
- Abstained: `False`
- Recommended product IDs: `['laptop-nimbus-16-pro', 'laptop-aurora-13-air', 'laptop-nimbus-14']`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['laptop-nimbus-16-pro', 'laptop-aurora-13-air', 'laptop-nimbus-14', 'acc-carryshield-15-sleeve', 'desktop-coreforge-mini']`
- Trace: `df48cc47-ee07-4bbe-b715-e204e4006f13` via `/inventory/chat/trace/df48cc47-ee07-4bbe-b715-e204e4006f13`
- Validation result: `FAIL`
- Route match: `True`
- Missing expected products: `['dock-hub-4k']`
- Forbidden products surfaced: `[]`
- Missing required phrases: `[]`
- Expected-no-hits check: `True`

### Answer


```text
For this customer, I would start with Nimbus 16 Pro Creator Laptop as the premium option. It sits at the top end of this matching set at USD 1699.00. There are only 6 unit(s) in stock, which gives you a legitimate urgency point. It sits in Computing under Nimbus. The product description highlights 16-inch performance laptop for creators, analysts, and heavy multitasking workflows. Structured details include battery life: 10 hours. If the customer needs a more accessible price point than Nimbus 16 Pro Creator Laptop, I would keep Aurora 13 Air Laptop ready as the fallback at USD 899.00. I am keeping this recommendation grounded in the current catalog only, so I am not claiming anything that is not in the stored product data. Are we selling into Computing and Accessories? Also tell me whether the buyer cares more about budget, premium feel, or immediate availability.
```


## 4. Business restock

- Question: `What should I restock first to prevent stockout?`
- Expected endpoint from sample pack: `agentic`
- Routed endpoint: `agentic`
- Route family: `planning_agentic_workflow`
- Answer engine chosen: `deterministic`
- Total hits: `9`
- Abstained: `False`
- Recommended product IDs: `['seed-audio-004', 'desk-flexispan-120', 'seed-office-004']`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['seed-audio-004', 'desk-flexispan-120', 'seed-office-004', 'audio-streamcore-xlr', 'audio-roombeam-conference', 'audio-bassforge-dj', 'monitor-pixelraft-34-ultrawide', 'net-securecam-poe-4', 'game-strikeview-27-165']`
- Trace: `daf496a4-7678-494f-ab70-20770b5846d4` via `/inventory/agentic/trace/daf496a4-7678-494f-ab70-20770b5846d4`
- Validation result: `FAIL`
- Route match: `True`
- Missing expected products: `['watch-trailmark-pro']`
- Forbidden products surfaced: `[]`
- Missing required phrases: `[]`
- Expected-no-hits check: `True`

### Answer


```text
I used a multi-step inventory reasoning pass for this question. Restock VoxCast USB Podcast Microphone (USD 159.00, 3 in stock, VoxCast) first. It leads the restock scorecard at 0.72 because inventory is tight enough to create real restock urgency, demand is among the strongest in the current set, and supplier lead time is long enough that waiting increases risk. Operational read: VoxCast USB Podcast Microphone, sold quantity 64, order count 48, demand score 0.91, business snapshot inventory level 3, supplier lead time 21 day(s), supplier risk 0.35, margin rate 33.0%. Next restock candidates are FlexiSpan 120 Standing Desk (USD 699.00, 5 in stock, FlexiSpan) and ErgoMesh Pro Chair (USD 549.00, 4 in stock, ErgoMesh). Do you want the full restock ranking or the safest backup options after this? Business-tool read: prioritize VoxCast USB Podcast Microphone because its operational signal is strongest: VoxCast USB Podcast Microphone, sold quantity 64, order count 48, demand score 0.91, business snapshot inventory level 3, supplier lead time 21 day(s), supplier risk 0.35. Next items to review are FlexiSpan 120 Standing Desk and ErgoMesh Pro Chair.
```


## 5. No bike abstention

- Question: `do you have any bike?`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `exact_lookup`
- Answer engine chosen: `deterministic`
- Total hits: `0`
- Abstained: `True`
- Abstention reason: `I could not find an exact catalog match for bike in the current inventory.`
- Recommended product IDs: `[]`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `[]`
- Trace: `8f827a7e-7dae-426b-8713-a2ea5950cec4` via `/inventory/chat/trace/8f827a7e-7dae-426b-8713-a2ea5950cec4`
- Validation result: `PASS`

### Answer


```text
I could not find an exact catalog match for bike in the current inventory. Tell me the product type, brand, budget, or stock question and I will narrow it down.
```


## 6. Budget earbuds

- Question: `Show me budget wireless earbuds under 100`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `exact_lookup`
- Answer engine chosen: `deterministic`
- Total hits: `1`
- Abstained: `False`
- Recommended product IDs: `['audio-airtone-mini-earbuds']`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['audio-airtone-mini-earbuds']`
- Trace: `43bcbf22-5f6a-4b24-a8cd-49e15cebd223` via `/inventory/chat/trace/43bcbf22-5f6a-4b24-a8cd-49e15cebd223`
- Validation result: `PASS`

### Answer


```text
I would lead with AirTone Mini Earbuds. It is the strongest budget-friendly match in the current catalog. It is the lowest-priced strong match at USD 69.00.
```


## 7. Student laptop

- Question: `Recommend a lightweight laptop for a student under 1000`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `recommendation`
- Answer engine chosen: `deterministic`
- Total hits: `2`
- Abstained: `True`
- Abstention reason: `Alternative recommendation CarryShield 15 Laptop Sleeve is in category Accessories, not the required computing category.`
- Recommended product IDs: `[]`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['laptop-aurora-13-air', 'acc-carryshield-15-sleeve']`
- Trace: `6c3a0116-4fff-452e-ae77-eb0c543d18bf` via `/inventory/chat/trace/6c3a0116-4fff-452e-ae77-eb0c543d18bf`
- Validation result: `PASS`

### Answer


```text
I do not have a reliable catalog fit that satisfies the required category, budget, stock, or spec constraints for this request.
```


## 8. Creator bundle

- Question: `I want a creator setup for podcasts and streaming`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `no_match_or_abstain`
- Answer engine chosen: `deterministic`
- Total hits: `0`
- Abstained: `True`
- Abstention reason: `That does not map cleanly to a supported inventory question I can answer from the current catalog.`
- Recommended product IDs: `[]`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `[]`
- Trace: `32d83a33-ca6d-4957-b123-39c55f74ab2d` via `/inventory/chat/trace/32d83a33-ca6d-4957-b123-39c55f74ab2d`
- Validation result: `FAIL`
- Route match: `True`
- Missing expected products: `['seed-audio-004', 'audio-streamcore-xlr', 'webcam-clearframe-4k']`
- Forbidden products surfaced: `[]`
- Missing required phrases: `[]`
- Expected-no-hits check: `True`

### Answer


```text
That does not map cleanly to a supported inventory question I can answer from the current catalog.
```


## 9. Standing desk cross-sell

- Question: `What goes well with a standing desk for a home office`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `exact_lookup`
- Answer engine chosen: `deterministic`
- Total hits: `3`
- Abstained: `False`
- Recommended product IDs: `['organizer-stackwise-tray', 'lamp-lumenleaf-task']`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['organizer-stackwise-tray', 'lamp-lumenleaf-task', 'desk-flexispan-120']`
- Trace: `c9d114fc-b546-4e29-baca-4035806438a0` via `/inventory/chat/trace/c9d114fc-b546-4e29-baca-4035806438a0`
- Validation result: `FAIL`
- Route match: `True`
- Missing expected products: `['chair-lumbarflex-air']`
- Forbidden products surfaced: `[]`
- Missing required phrases: `[]`
- Expected-no-hits check: `True`

### Answer


```text
I would start by recommending StackWise Desk Tray Set. It is the strongest overall match from the current catalog. The current price is USD 34.00. It currently has 27 unit(s) in stock. It sits in Office under StackWise. The product description highlights Modular desk trays for sorting documents, mail, and paper-heavy workflows. Structured details include color: matte black. If the customer wants an alternative, I would show LumenLeaf Task Lamp next at USD 69.00. If the customer is open to stepping up from StackWise Desk Tray Set, I would upsell to LumenLeaf Task Lamp at USD 69.00. I am keeping this recommendation grounded in the current catalog only, so I am not claiming anything that is not in the stored product data. Are we selling into Office? Also tell me whether the buyer cares more about budget, premium feel, or immediate availability.
```


## 10. Wi-Fi coverage fix

- Question: `My house has weak Wi-Fi in the far rooms. What should I buy?`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `exact_lookup`
- Answer engine chosen: `deterministic`
- Total hits: `5`
- Abstained: `False`
- Recommended product IDs: `[]`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['net-signalrise-extender', 'home-climatehub-sensor', 'home-lumos-mini-bulb', 'net-portbridge-8g-switch', 'mouse-pointera-silent']`
- Trace: `8a2b8f0d-b915-4a7e-9b55-f61b04b2da29` via `/inventory/chat/trace/8a2b8f0d-b915-4a7e-9b55-f61b04b2da29`
- Validation result: `FAIL`
- Route match: `True`
- Missing expected products: `['net-skyroute-mesh-2pk']`
- Forbidden products surfaced: `[]`
- Missing required phrases: `[]`
- Expected-no-hits check: `True`

### Answer


```text
A strong starting point is SignalRise Wi-Fi Extender (USD 59.00, 26 in stock, SignalRise). Are you looking for Networking, Smart Home, and Computing? If you also tell me your budget or preferred brand, I can narrow it down.
```


## 11. Portable storage

- Question: `I need fast portable storage for video files`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `exact_lookup`
- Answer engine chosen: `natural`
- Total hits: `3`
- Abstained: `False`
- Recommended product IDs: `['stor-flashpeak-1tb-ssd', 'stor-archivebox-4tb-hdd', 'stor-cardedge-512-microsd']`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['stor-flashpeak-1tb-ssd', 'stor-archivebox-4tb-hdd', 'stor-cardedge-512-microsd']`
- Trace: `6d3b530e-b042-4c42-acb6-2b08a30db136` via `/inventory/chat/trace/6d3b530e-b042-4c42-acb6-2b08a30db136`
- Validation result: `FAIL`
- Route match: `True`
- Missing expected products: `[]`
- Forbidden products surfaced: `['stor-archivebox-4tb-hdd']`
- Missing required phrases: `[]`
- Expected-no-hits check: `True`

### Answer


```text
Based on your query, the FlashPeak 1TB SSD is recommended for its high performance and reliability, making it ideal for tasks requiring fast data access. However, if budget is a priority, the CardEdge 512GB microSD offers a more affordable storage solution. The ArchiveBox 4TB HDD provides ample capacity at a lower cost but may not match the speed of SSDs. Let me know your budget and intended use case to refine the recommendation further.
```


## 12. Phone travel add-ons

- Question: `What should I bundle with a phone for travel?`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `agentic`
- Route family: `planning_agentic_workflow`
- Answer engine chosen: `deterministic`
- Total hits: `10`
- Abstained: `False`
- Recommended product IDs: `['acc-carryshield-15-sleeve']`
- Cross-sell product IDs: `['acc-packmate-tech-pouch']`
- Combined surfaced product IDs: `['acc-carryshield-15-sleeve', 'acc-packmate-tech-pouch', 'laptop-aurora-13-air', 'charger-voltway-65gan', 'desktop-coreforge-mini', 'laptop-nimbus-14', 'phone-pathlite-mini', 'phone-novacore-s', 'powerbank-voltway-20k', 'phone-novacore-ultra']`
- Trace: `a1d3b404-3199-41c9-a82f-c168d73a1b67` via `/inventory/agentic/trace/a1d3b404-3199-41c9-a82f-c168d73a1b67`
- Validation result: `FAIL`
- Route match: `False`
- Missing expected products: `['case-armorloop-novacore']`
- Forbidden products surfaced: `[]`
- Missing required phrases: `[]`
- Expected-no-hits check: `True`

### Answer


```text
I used a multi-step inventory reasoning pass for this question. For a clean bundle, start with CarryShield 15 Laptop Sleeve (USD 35.00, 38 in stock, CarryShield). If the customer is building out a fuller setup around CarryShield 15 Laptop Sleeve, I would also cross-sell PackMate Tech Pouch at USD 27.00. I filtered add-ons to keep only items that are complementary to CarryShield 15 Laptop Sleeve, not weak substitutes. Do you want a cheaper bundle, a premium bundle, or just the core product?
```


## 13. Restock by demand and low inventory

- Question: `Which products are most urgent to restock based on demand and current inventory?`
- Expected endpoint from sample pack: `agentic`
- Routed endpoint: `agentic`
- Route family: `planning_agentic_workflow`
- Answer engine chosen: `deterministic`
- Total hits: `9`
- Abstained: `False`
- Recommended product IDs: `['seed-audio-004', 'desk-flexispan-120', 'seed-office-004']`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['seed-audio-004', 'desk-flexispan-120', 'seed-office-004', 'audio-streamcore-xlr', 'audio-roombeam-conference', 'monitor-pixelraft-34-ultrawide', 'audio-bassforge-dj', 'game-strikeview-27-165', 'phone-novacore-ultra']`
- Trace: `d398f90f-8299-459d-8833-862ca41d3d06` via `/inventory/agentic/trace/d398f90f-8299-459d-8833-862ca41d3d06`
- Validation result: `PASS`

### Answer


```text
I used a multi-step inventory reasoning pass for this question. Restock VoxCast USB Podcast Microphone (USD 159.00, 3 in stock, VoxCast) first. It leads the restock scorecard at 0.72 because inventory is tight enough to create real restock urgency, demand is among the strongest in the current set, and supplier lead time is long enough that waiting increases risk. Operational read: VoxCast USB Podcast Microphone, sold quantity 64, order count 48, demand score 0.91, business snapshot inventory level 3, supplier lead time 21 day(s), supplier risk 0.35, margin rate 33.0%. Next restock candidates are FlexiSpan 120 Standing Desk (USD 699.00, 5 in stock, FlexiSpan) and ErgoMesh Pro Chair (USD 549.00, 4 in stock, ErgoMesh). Do you want the full restock ranking or the safest backup options after this? Business-tool read: prioritize VoxCast USB Podcast Microphone because its operational signal is strongest: VoxCast USB Podcast Microphone, sold quantity 64, order count 48, demand score 0.91, business snapshot inventory level 3, supplier lead time 21 day(s), supplier risk 0.35. Next items to review are FlexiSpan 120 Standing Desk and ErgoMesh Pro Chair.
```


## 14. No refrigerator abstention

- Question: `Do you sell refrigerators?`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `no_match_or_abstain`
- Answer engine chosen: `deterministic`
- Total hits: `0`
- Abstained: `True`
- Abstention reason: `That does not map cleanly to a supported inventory question I can answer from the current catalog.`
- Recommended product IDs: `[]`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `[]`
- Trace: `6c2359e3-4bb9-465c-8d45-cca5d6943f70` via `/inventory/chat/trace/6c2359e3-4bb9-465c-8d45-cca5d6943f70`
- Validation result: `PASS`

### Answer


```text
That does not map cleanly to a supported inventory question I can answer from the current catalog.
```


## 15. Premium monitor

- Question: `Show me a premium monitor for dashboards and multitasking`
- Expected endpoint from sample pack: `ask`
- Routed endpoint: `ask`
- Route family: `exact_lookup`
- Answer engine chosen: `deterministic`
- Total hits: `4`
- Abstained: `False`
- Recommended product IDs: `['monitor-pixelraft-34-ultrawide', 'monitor-visionedge-27']`
- Cross-sell product IDs: `[]`
- Combined surfaced product IDs: `['monitor-pixelraft-34-ultrawide', 'monitor-visionedge-27', 'acc-screenmate-clean-kit', 'game-strikeview-27-165']`
- Trace: `bf2fed27-dbb9-4c32-ac74-6b5b6ee4108d` via `/inventory/chat/trace/bf2fed27-dbb9-4c32-ac74-6b5b6ee4108d`
- Validation result: `FAIL`
- Route match: `True`
- Missing expected products: `[]`
- Forbidden products surfaced: `['monitor-visionedge-27', 'game-strikeview-27-165']`
- Missing required phrases: `[]`
- Expected-no-hits check: `True`

### Answer


```text
For this customer, I would start with PixelRaft 34 Ultrawide Monitor as the premium option. It sits at the top end of this matching set at USD 499.00. There are only 7 unit(s) in stock, which gives you a legitimate urgency point. It sits in Computing under PixelRaft. The product description highlights 34-inch ultrawide display for multitasking, dashboards, and dual-window productivity. If the customer needs a more accessible price point than PixelRaft 34 Ultrawide Monitor, I would keep VisionEdge 27 QHD Monitor ready as the fallback at USD 289.00. I am keeping this recommendation grounded in the current catalog only, so I am not claiming anything that is not in the stored product data. Are we selling into Computing, Accessories, and Gaming? Also tell me whether the buyer cares more about budget, premium feel, or immediate availability.
```
