# Boutique Inventory Multilingual QA Set

Use this set to evaluate the customer-facing boutique inventory bot after catalog or parser changes.

The expected answer does not need to match word-for-word. It must preserve the factual outcome, product IDs, stock state, and language style.

## English

| ID | Question | Expected answer |
|---|---|---|
| EN-01 | Do you have oily skin sunscreen under 1000? | Recommend `beauty-sunscreen-oily-spf50`, say Oil Control Sunscreen SPF 50 is BDT 950 and 9 in stock. It may also mention nearby Beauty options. |
| EN-02 | Do you have the Lotus Buti Jamdani in blue? | Say yes, `saree-jmd-lotus-blue` is available at BDT 6,800 with 2 in stock, and mention red as another in-stock same-design color. |
| EN-03 | white panjabi L available? | Say yes, `panjabi-cotton-white-l` is available at BDT 2,600 with 3 in stock. Must not answer with the size M SKU. |
| EN-04 | blue floral three piece M available? | Say `threepiece-floral-georgette-blue-m` exists but is out of stock, and suggest `threepiece-floral-georgette-pink-m` as the closest available option. |
| EN-05 | Show me a ladies rose gold watch. | Recommend `watch-ladies-rose-gold`, BDT 2,200, 4 in stock. This should be a direct search answer, not a matching accessory answer. |
| EN-06 | I need a men's oud perfume for gift. | Recommend `perfume-men-oud-100ml`, BDT 3,200, 5 in stock. |

## Banglish

| ID | Question | Expected answer |
|---|---|---|
| BNGL-01 | men er brown loafer size 42 ache? | Say yes in Banglish/Ji style. Recommend `shoe-men-loafer-brown-42`, BDT 2,850, 3 stock e ache. |
| BNGL-02 | red lipstick ache? | Recommend `cosmetic-lipstick-matte-red`, BDT 650, 12 stock e ache. |
| BNGL-03 | ei same design ta green color e ache? | With prior focus on `saree-jmd-lotus-red`, say `saree-jmd-lotus-green` exists but stock e nei; mention red and royal blue are in stock. |
| BNGL-04 | ladies daily use bag dekhan | Recommend `bag-tote-black-everyday`, BDT 1,650, 6 stock e ache. |
| BNGL-05 | 3000 er moddhe men er formal shirt pant ache? | Should return men's formal shirt/pant options under budget, especially `shirt-formal-white-l`, `shirt-oxford-blue-m`, `pant-chino-navy-32`, or `pant-formal-black-34`. |

## Bangla

| ID | Question | Expected answer |
|---|---|---|
| BNG-01 | ৪০০০ টাকার মধ্যে অফিসে পরার হালকা শাড়ি দেখান | Recommend office/lightweight sarees under BDT 4,000, especially Pastel Soft Muslin and Everyday Cotton Block Print sarees. |
| BNG-02 | নেভি কাতান শাড়ির সাথে কোন ব্যাগ মানাবে? | Recommend matching options for the navy bridal katan saree, including `bag-potli-gold-beaded` and `bag-clutch-antique-gold`. |
| BNG-03 | লাল লিপস্টিক আছে? | Recommend `cosmetic-lipstick-matte-red`, BDT 650, 12 stock. |
| BNG-04 | তৈলাক্ত ত্বকের জন্য সানস্ক্রিন আছে? | Recommend `beauty-sunscreen-oily-spf50`; mention it is for oily/acne-prone skin and in stock. |
| BNG-05 | সাদা পাঞ্জাবি সাইজ L আছে? | Recommend `panjabi-cotton-white-l`, BDT 2,600, 3 in stock. |

## Failure Notes To Watch

- Do not let old electronics demo products appear.
- Do not answer a direct watch/perfume/lipstick query as a matching-accessory query.
- Do not use another size SKU as if it satisfied the requested exact size.
- Same-design follow-ups must use focused product context.
- If an item exists but stock is zero, say it exists but is out of stock and offer available alternatives.
