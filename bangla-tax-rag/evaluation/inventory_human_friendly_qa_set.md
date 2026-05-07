# Inventory RAG Human-Friendly QA Evaluation Set

Purpose: evaluate the full inventory RAG system with natural user questions, not robotic keyword prompts.

Use this as a human judgment set. The answer does not need exact wording, but it should satisfy the expected answer, respect constraints, and avoid the forbidden behavior.

## Evaluation Rubric

- Pass: answer is grounded in catalog/business data, names the right product(s), includes requested facts, and respects hard constraints.
- Partial: answer finds a relevant product but misses a requested fact, gives weak reasoning, or includes a questionable alternative.
- Fail: answer recommends the wrong product type, violates a hard constraint, hallucinates unavailable facts, or refuses when a valid catalog answer exists.

## Question Set

### Q01 - Wireless ANC Office Headphones

User question:

> I need wireless ANC headphones for office calls under $300, and they need to be in stock. What should I buy?

Expected friendly answer:

Recommend `Auralite Flex ANC Headphones` (`seed-audio-001`). Say it is USD 249, has 14 units in stock, uses Bluetooth 5.3, has active noise cancellation, and is meant for office calls.

Must not do:

- Do not lead with `BassForge DJ Monitor Headphones`, because it is wired.
- Do not treat earbuds as equal to over-ear headphones.

### Q02 - Wired Editing Headphones

User question:

> I edit audio at night. Do we have wired monitor headphones under $160?

Expected friendly answer:

Recommend `BassForge DJ Monitor Headphones` (`audio-bassforge-dj`). Mention USD 149, 10 in stock, 3.5mm wired connectivity, passive isolation, and editing/studio use.

Must not do:

- Do not recommend Auralite or EchoWave as the lead because this asks for wired monitor headphones.

### Q03 - Student Wireless Earbuds

User question:

> My student budget is tight. I just want wireless earbuds under $80. Anything decent?

Expected friendly answer:

Recommend `AirTone Mini Earbuds` (`audio-airtone-mini-earbuds`). Mention USD 69, 40 in stock, Bluetooth 5.1, and 20 hours battery life.

Must not do:

- Do not lead with `EchoWave Studio Earbuds`, because it is USD 119 and exceeds the budget.

### Q04 - Support Team Headset

User question:

> Our support team needs a wireless headset for calls with a clear mic. What is the best fit?

Expected friendly answer:

Recommend `ClairVoice Office Headset` (`audio-clairvoice-headset`). Mention USD 179, 13 in stock, Bluetooth 5.2, environmental mic filtering, and support calls.

Must not do:

- Do not lead with lifestyle headphones when the user asks for a headset.

### Q05 - USB Podcast Microphone

User question:

> I am starting a podcast. Give me a USB microphone under $170 that is actually available.

Expected friendly answer:

Recommend `VoxCast USB Podcast Microphone` (`seed-audio-004`). Mention USD 159, 3 in stock, cardioid pickup, USB-C input, and podcasting use. Note low stock politely.

Must not do:

- Do not recommend `StreamCore XLR Creator Mic` because this asks for USB.

### Q06 - XLR Creator Microphone

User question:

> I already have an audio interface, so I want an XLR creator mic under $200. What do you suggest?

Expected friendly answer:

Recommend `StreamCore XLR Creator Mic` (`audio-streamcore-xlr`). Mention USD 189, 5 in stock, dynamic cardioid pickup, XLR input, and streaming/creator use.

Must not do:

- Do not recommend `VoxCast USB Podcast Microphone` as the lead because this asks for XLR.

### Q07 - Meeting Room Speakerphone

User question:

> We need one speakerphone for a small conference room. What should I order?

Expected friendly answer:

Recommend `RoomBeam Conference Speakerphone` (`audio-roombeam-conference`). Mention USD 199, 8 in stock, 360-degree pickup, USB-C input, and meeting room use.

Must not do:

- Do not replace it with headphones, earbuds, or a portable music speaker.

### Q08 - Outdoor Portable Speaker

User question:

> I need a portable Bluetooth speaker for outdoor office events, ideally around $150.

Expected friendly answer:

Recommend `Soniq Max Portable Speaker` (`audio-soniq-max-speaker`). Mention USD 139, 17 in stock, Bluetooth 5.3, IPX7 water resistance, and 24-hour battery life.

Must not do:

- Do not lead with the conference speakerphone.

### Q09 - Travel Laptop Under $1000

User question:

> I travel a lot and want a light laptop under $1000. What is the sensible choice?

Expected friendly answer:

Recommend `Aurora 13 Air Laptop` (`laptop-aurora-13-air`). Mention USD 899, 19 in stock, 13-inch screen, 8GB RAM, 256GB SSD, and 14-hour battery life.

Must not do:

- Do not lead with `Nimbus 14 Business Ultrabook`, because it costs USD 1199 and exceeds the budget.

### Q10 - Manager Laptop With More Power

User question:

> My budget can stretch to $1300. I need a reliable business laptop for office productivity and travel.

Expected friendly answer:

Recommend `Nimbus 14 Business Ultrabook` (`laptop-nimbus-14`). Mention USD 1199, 9 in stock, 14-inch screen, 16GB RAM, 512GB SSD, and 12-hour battery life.

Must not do:

- Do not recommend gaming or desktop products.

### Q11 - Creator Laptop

User question:

> Do we have a serious creator laptop with 32GB RAM and 1TB storage?

Expected friendly answer:

Recommend `Nimbus 16 Pro Creator Laptop` (`laptop-nimbus-16-pro`). Mention USD 1699, 6 in stock, low stock status, 16-inch screen, 32GB RAM, 1TB SSD, and creator/performance positioning.

Must not do:

- Do not claim RTX graphics unless the catalog explicitly says it.

### Q12 - Gaming Monitor

User question:

> I want a gaming monitor under $350 with a high refresh rate. What should I get?

Expected friendly answer:

Recommend `StrikeView 27 Gaming Monitor` (`game-strikeview-27-165`). Mention USD 329, 9 in stock, 27-inch screen, 2560x1440 resolution, 165Hz refresh rate, and Fast IPS panel.

Must not do:

- Do not lead with office monitors if the gaming monitor fits.

### Q13 - Office QHD Monitor

User question:

> I need a good 27-inch office monitor under $300, not a gaming pitch.

Expected friendly answer:

Recommend `VisionEdge 27 QHD Monitor` (`monitor-visionedge-27`). Mention USD 289, 15 in stock, 27-inch screen, 2560x1440 resolution, 75Hz refresh rate, and IPS panel.

Must not do:

- Do not lead with `StrikeView 27 Gaming Monitor`, because the user asked for office, not gaming.

### Q14 - Ultrawide Productivity Monitor

User question:

> My spreadsheet work needs more horizontal space. Do we have an ultrawide monitor?

Expected friendly answer:

Recommend `PixelRaft 34 Ultrawide Monitor` (`monitor-pixelraft-34-ultrawide`). Mention USD 499, 7 in stock, 34-inch ultrawide, 3440x1440 resolution, 100Hz refresh rate, and productivity fit.

Must not do:

- Do not answer with a normal 27-inch monitor unless framed as a cheaper fallback.

### Q15 - Triple Display Dock

User question:

> I want to turn a USB-C laptop into a multi-monitor desk setup. What dock should I buy?

Expected friendly answer:

Recommend `DockHub 4K Triple Display Station` (`dock-hub-4k`). Mention USD 229, 11 in stock, HDMI/USB-C/Ethernet ports, 100W power delivery, and triple 4K display support.

Must not do:

- Do not recommend only a laptop stand or cable pack.

### Q16 - Quiet Mouse

User question:

> I need a quiet wireless mouse for an office desk. Anything inexpensive?

Expected friendly answer:

Recommend `PointEra Silent Mouse` (`mouse-pointera-silent`). Mention USD 39, 45 in stock, silent office use, 2.4GHz plus Bluetooth connectivity, and 18-month battery life.

Must not do:

- Do not recommend a keyboard or generic accessory bundle instead.

### Q17 - Mechanical Keyboard

User question:

> Do we carry a mechanical keyboard for typing-heavy work?

Expected friendly answer:

Recommend `KeyFlow Mechanical Keyboard` (`keyboard-keyflow-mech`). Mention USD 119, 24 in stock, tactile switches, TKL layout, and USB-C wired connectivity.

Must not do:

- Do not confuse this with a laptop accessory.

### Q18 - Outdoor Smartwatch Under $250

User question:

> Recommend the best smartwatch under $250 for outdoor workouts. Built-in GPS and water resistance matter more than lowest price.

Expected friendly answer:

Recommend `TrailMark Pro Smart Watch` (`watch-trailmark-pro`). Mention USD 219, 6 in stock, low stock status, built-in GPS, 5ATM water resistance, AMOLED display, and fitness/outdoor fit.

Must not do:

- Do not lead with `PulseLine Lite Watch`, because it only has phone-connected GPS.
- Do not abstain, because TrailMark is a valid fit.

### Q19 - Premium Adventure Watch

User question:

> If I can spend a little more, what is the best adventure watch for serious outdoor use?

Expected friendly answer:

Recommend `Summit X Adventure Watch` (`watch-summit-x`). Mention USD 299, 7 in stock, multi-band GPS, 10ATM water resistance, 96-hour battery life, and outdoor MIP display.

Must not do:

- Do not over-prioritize cheaper watches when the prompt asks for serious outdoor use.

### Q20 - Budget Fitness Tracker

User question:

> I just need a cheap fitness tracker with long battery life. GPS is not important.

Expected friendly answer:

Recommend `VitalLoop Fit Band` (`band-vitalloop-fit`). Mention USD 79, 34 in stock, 120-hour battery life, 3ATM water resistance, health tracking, and no GPS.

Must not do:

- Do not pretend it has GPS.

### Q21 - Stylish Office Watch

User question:

> I want a watch that looks more office-friendly than sporty. What should I consider?

Expected friendly answer:

Recommend `CityPulse Classic Watch` (`watch-citypulse-classic`). Mention USD 189, 16 in stock, hybrid analog display, 336-hour battery life, 5ATM water resistance, and office/style positioning.

Must not do:

- Do not lead with adventure or fitness-first watches unless framed as alternatives.

### Q22 - Midrange OLED Phone

User question:

> Do we have a midrange phone with an OLED screen and decent storage?

Expected friendly answer:

Recommend `NovaCore S Smartphone` (`phone-novacore-s`). Mention USD 499, 14 in stock, 256GB storage, 6.5-inch OLED display, 5000mAh battery, and 50MP dual camera.

Must not do:

- Do not jump to the flagship unless the user asks for premium.

### Q23 - Premium Camera Phone

User question:

> What is the premium phone option if camera and storage matter most?

Expected friendly answer:

Recommend `NovaCore Ultra Smartphone` (`phone-novacore-ultra`). Mention USD 999, 8 in stock, 512GB storage, 6.8-inch LTPO OLED, 5100mAh battery, and 50MP triple camera.

Must not do:

- Do not describe camera specs not in the catalog.

### Q24 - Travel Charging Bundle

User question:

> Can you build me a small travel charging bundle for a phone and laptop bag?

Expected friendly answer:

Recommend a bundle such as `VoltWay 65W GaN Charger` (`charger-voltway-65gan`) plus `VoltWay 20K Power Bank` (`powerbank-voltway-20k`) plus `CableCraft Pro Pack` (`acc-cablecraft-propack`). Mention USD 49, USD 69, and USD 29, all in stock, for a total of USD 147.

Must not do:

- Do not recommend only one product when the user asks for a bundle.

### Q25 - NovaCore Protection Cross-Sell

User question:

> I am buying a NovaCore phone. What cheap add-ons should I include so it is protected and ready to charge?

Expected friendly answer:

Recommend `ArmorLoop NovaCore Case` (`case-armorloop-novacore`), `ScreenMate Clean Kit` (`acc-screenmate-clean-kit`), and optionally `VoltWay 65W GaN Charger` (`charger-voltway-65gan`). Mention prices USD 29, USD 15, and USD 49, and that all are in stock.

Must not do:

- Do not recommend products unrelated to phones or protection/charging.

### Q26 - Premium Ergonomic Chair

User question:

> My back hurts from long desk sessions. What premium chair should I buy?

Expected friendly answer:

Recommend `ErgoMesh Pro Chair` (`seed-office-004`). Mention USD 549, 4 in stock, low stock status, adjustable lumbar support, mesh material, and 4D armrests.

Must not do:

- Do not hide the low stock risk.

### Q27 - Midrange Ergonomic Chair

User question:

> I need an ergonomic office chair, but $549 is too much. Do we have a cheaper mesh option?

Expected friendly answer:

Recommend `LumbarFlex Air Chair` (`chair-lumbarflex-air`). Mention USD 329, 9 in stock, dynamic lumbar support, mesh material, and 3D armrests.

Must not do:

- Do not keep pushing ErgoMesh as the only answer.

### Q28 - Standing Desk

User question:

> Do we have a standing desk for a premium office setup?

Expected friendly answer:

Recommend `FlexiSpan 120 Standing Desk` (`desk-flexispan-120`). Mention USD 699, 5 in stock, low stock status, 120cm width, 72-118cm height range, and dual motor.

Must not do:

- Do not recommend only chairs or lamps.

### Q29 - Secure File Storage

User question:

> I need a lockable cabinet for office documents. What is available?

Expected friendly answer:

Recommend `FileVault 3-Drawer Cabinet` (`cabinet-filevault-3`). Mention USD 259, 6 in stock, 3 drawers, keyed lock, and steel material.

Must not do:

- Do not suggest digital storage devices.

### Q30 - Desk Planning Setup

User question:

> I am setting up a planning corner for a small team. What office items would you bundle?

Expected friendly answer:

Recommend a small office bundle such as `BriefGrid 48 Whiteboard` (`whiteboard-briefgrid-48`), `LumenLeaf Task Lamp` (`lamp-lumenleaf-task`), and `StackWise Desk Tray Set` (`organizer-stackwise-tray`). Mention prices USD 99, USD 69, and USD 34, all in stock, total USD 202.

Must not do:

- Do not answer with a single product only.

### Q31 - Small Home Wi-Fi

User question:

> I need Wi-Fi 6 for a small home office. What router makes sense?

Expected friendly answer:

Recommend `SkyRoute AX1800 Router` (`net-skyroute-ax1800`). Mention USD 129, 17 in stock, Wi-Fi 6, 4 Gigabit LAN ports, and small home coverage.

Must not do:

- Do not lead with mesh unless the user asks for larger coverage.

### Q32 - Bigger Home Coverage

User question:

> My house has dead zones. Would a mesh kit be better than a basic router?

Expected friendly answer:

Recommend `SkyRoute Mesh 2-Pack` (`net-skyroute-mesh-2pk`) for broader coverage. Mention USD 229, 11 in stock, Wi-Fi 6, two nodes, and coverage up to 3500 sq ft. Optionally mention `SignalRise Wi-Fi Extender` as a cheaper dead-zone fix at USD 59.

Must not do:

- Do not recommend only the basic router without explaining coverage tradeoff.

### Q33 - Travel Hotspot

User question:

> I travel for work and need internet for a few devices. Do we have a portable hotspot?

Expected friendly answer:

Recommend `CloudPath 5G Hotspot` (`net-cloudpath-5g-hotspot`). Mention USD 199, 8 in stock, 12-hour battery, nano-SIM plus eSIM support, and up to 16 devices.

Must not do:

- Do not recommend a home router.

### Q34 - Portable Creator Storage

User question:

> I need fast portable storage for creator files. What should I buy?

Expected friendly answer:

Recommend `FlashPeak 1TB Portable SSD` (`stor-flashpeak-1tb-ssd`). Mention USD 129, 19 in stock, 1TB capacity, USB-C 10Gbps, and shock-resistant rugged design.

Must not do:

- Do not lead with the desktop hard drive if the user says portable/creator.

### Q35 - Desktop Backup Drive

User question:

> I want a cheap desktop backup drive with lots of capacity. Speed is not the main thing.

Expected friendly answer:

Recommend `ArchiveBox 4TB Desktop Drive` (`stor-archivebox-4tb-hdd`). Mention USD 109, 14 in stock, 4TB capacity, USB 3.2, and external adapter power.

Must not do:

- Do not lead with the 1TB portable SSD when capacity and backup are the priority.

### Q36 - Camera or Tablet microSD

User question:

> Do we have a large microSD card for a camera or tablet?

Expected friendly answer:

Recommend `CardEdge 512GB microSD` (`stor-cardedge-512-microsd`). Mention USD 59, 26 in stock, 512GB capacity, U3 V30 speed class, and SD adapter included.

Must not do:

- Do not recommend portable SSDs as the lead for a microSD request.

### Q37 - Auralite Exact Lookup

User question:

> Do you have Auralite Flex ANC Headphones? Give me price, stock, and why it fits office calls.

Expected friendly answer:

Say yes. `Auralite Flex ANC Headphones` (`seed-audio-001`) costs USD 249 and has 14 units in stock. Explain that it fits office calls because it is wireless, has active noise cancellation, Bluetooth 5.3, clear voice pickup/office-call positioning, and 35-hour battery life.

Must not do:

- Do not omit stock.
- Do not say ANC support is missing.

### Q38 - Auralite vs BassForge Comparison

User question:

> Compare Auralite Flex ANC Headphones and BassForge DJ Monitor Headphones. Which one should I buy for office calls?

Expected friendly answer:

Recommend Auralite for office calls. Explain Auralite is wireless Bluetooth 5.3 with active noise cancellation, office-call use, USD 249, and 14 in stock. Explain BassForge is cheaper at USD 149 with 10 in stock, but it is 3.5mm wired and better for editing/studio monitor use.

Must not do:

- Do not claim BassForge is wireless.
- Do not choose BassForge for office calls unless the user prioritizes price over wireless call comfort.

### Q39 - TrailMark vs PulseLine Comparison

User question:

> Compare TrailMark Pro and PulseLine Lite. I hike on weekends but I also care about price.

Expected friendly answer:

Recommend `TrailMark Pro Smart Watch` if outdoor/hiking features matter most: USD 219, 6 in stock, built-in GPS, 5ATM water resistance, AMOLED display, 48-hour battery. Explain `PulseLine Lite Watch` is cheaper at USD 129 with 18 in stock and 72-hour battery, but it only has phone-connected GPS and is more basic.

Must not do:

- Do not rank PulseLine first without explaining the outdoor feature tradeoff.

### Q40 - Remote Meeting Kit

User question:

> Build a remote meeting kit under $600 for a manager who uses a laptop and external screens.

Expected friendly answer:

Recommend a kit like `ClearFrame 4K Webcam` (`webcam-clearframe-4k`), `ClairVoice Office Headset` (`audio-clairvoice-headset`), and `DockHub 4K Triple Display Station` (`dock-hub-4k`). Mention prices USD 149, USD 179, and USD 229, all in stock, total USD 557.

Must not do:

- Do not exceed the budget without saying so.
- Do not answer with only one product.

### Q41 - Laptop Desk Bundle Around $1500

User question:

> I want a laptop desk setup around $1500: laptop, monitor, dock, and maybe a stand. Keep it practical.

Expected friendly answer:

Recommend `Aurora 13 Air Laptop` (`laptop-aurora-13-air`), `VisionEdge 27 QHD Monitor` (`monitor-visionedge-27`), `DockHub 4K Triple Display Station` (`dock-hub-4k`), and `ViewStand Fold Laptop Stand` (`acc-viewstand-fold`). Mention prices USD 899, USD 289, USD 229, and USD 45, all in stock, total USD 1462.

Must not do:

- Do not use `Nimbus 14 Business Ultrabook` in this bundle unless you explain it would push the total over budget.

### Q42 - Creator Podcast Bundle

User question:

> Build me a creator podcast setup under $400. I need a microphone and useful desk or video accessories.

Expected friendly answer:

Recommend a bundle such as `VoxCast USB Podcast Microphone` (`seed-audio-004`), `ClearFrame 4K Webcam` (`webcam-clearframe-4k`), and `LumenLeaf Task Lamp` (`lamp-lumenleaf-task`). Mention prices USD 159, USD 149, and USD 69, all in stock, total USD 377.

Must not do:

- Do not answer with only a microphone.
- Do not recommend XLR gear unless the user says they have an audio interface.

### Q43 - Top Restock Ranking

User question:

> Rank the top 5 products we should restock first. Use low stock, demand, margin, supplier lead time, and supplier risk.

Expected friendly answer:

Give a ranked restock answer, not just one product. It should include these high-priority candidates:

- `VoxCast USB Podcast Microphone` (`seed-audio-004`): 3 on hand, demand score 0.91, 64 sold, 21-day lead time, supplier risk 0.35, margin 33%.
- `StreamCore XLR Creator Mic` (`audio-streamcore-xlr`): 5 on hand, demand score 0.96, 48 sold, 21-day lead time, supplier risk 0.35, margin 33%.
- `ErgoMesh Pro Chair` (`seed-office-004`): 4 on hand, demand score 0.74, 30-day lead time, supplier risk 0.42, margin 40%.
- `FlexiSpan 120 Standing Desk` (`desk-flexispan-120`): 5 on hand, demand score 0.74, 30-day lead time, supplier risk 0.42, margin 38%.
- `TrailMark Pro Smart Watch` (`watch-trailmark-pro`): 6 on hand, demand score 0.82, 18-day lead time, supplier risk 0.32, margin 35%.

Must not do:

- Do not give only the top 1 when the user asks for top 5.
- Do not ignore business signals.

### Q44 - Stockout Risk

User question:

> Which products are risky to promise customers because stock is tight?

Expected friendly answer:

Mention products with low stock, especially `VoxCast USB Podcast Microphone` with 3 units, `ErgoMesh Pro Chair` with 4, `StreamCore XLR Creator Mic` with 5, `FlexiSpan 120 Standing Desk` with 5, and `TrailMark Pro Smart Watch` with 6. Explain that promise risk depends on demand and lead time too, not stock alone.

Must not do:

- Do not list high-stock items as urgent stockout risks.

### Q45 - High-Margin Low-Stock Review

User question:

> Which low-stock products are still worth prioritizing because margin is decent?

Expected friendly answer:

Mention `ErgoMesh Pro Chair` (4 stock, 40% margin), `FlexiSpan 120 Standing Desk` (5 stock, 38% margin), `TrailMark Pro Smart Watch` (6 stock, 35% margin), and the creator microphones around 33% margin. Explain margin should be balanced with demand and lead time.

Must not do:

- Do not rank purely by margin without stock/demand context.

### Q46 - No Refrigerators

User question:

> Do you sell refrigerators? I need one for an apartment.

Expected friendly answer:

Clearly say the current catalog does not show refrigerators, so there is no reliable refrigerator recommendation. Optionally offer to look for smart-home or kitchen-adjacent products only if useful, but do not pretend a robot vacuum or sensor is a refrigerator.

Must not do:

- Do not recommend unrelated smart-home items as refrigerators.

### Q47 - Impossible Gaming Laptop

User question:

> Find me a gaming laptop under $500 with 32GB RAM, RTX graphics, and at least 1TB SSD in stock. If none exists, say so clearly.

Expected friendly answer:

Say no reliable catalog match exists. Explain that `Nimbus 16 Pro Creator Laptop` has 32GB RAM and 1TB SSD but is USD 1699 and the catalog does not state RTX graphics. Do not recommend `CarryShield 15 Laptop Sleeve`, `VoltWay 65W GaN Charger`, or a tablet as a laptop.

Must not do:

- Do not recommend accessories as laptops.
- Do not invent RTX graphics.

### Q48 - Unknown SKU or Missing Product

User question:

> Can you check if we have SKU FRG-APT-900 and tell me the price?

Expected friendly answer:

Say that SKU `FRG-APT-900` is not found in the current catalog, so the system cannot provide a reliable price. Ask for another SKU or product name.

Must not do:

- Do not guess a price.

### Q49 - Out-of-Domain Legal Question

User question:

> What is the income tax rate for Bangladesh this year?

Expected friendly answer:

For the inventory system, this should not answer from the product catalog. It should say the question is outside the inventory catalog context or route to the tax/legal RAG only if that workflow is explicitly available.

Must not do:

- Do not answer tax law from inventory product data.

### Q50 - Casual Small Talk With Inventory Handoff

User question:

> Hey, before I shop, can you help me figure out what to buy for a cleaner desk setup?

Expected friendly answer:

Respond naturally and offer to help. Suggest a practical desk setup path using inventory, such as `LumenLeaf Task Lamp`, `StackWise Desk Tray Set`, `PointEra Silent Mouse`, `KeyFlow Mechanical Keyboard`, or `ViewStand Fold Laptop Stand`, then ask whether the user wants budget, ergonomic, or premium.

Must not do:

- Do not refuse just because the wording starts casually.
- Do not invent non-catalog products.

