# Le Reve CLIP-Only 10000-Query Baseline

- Run ID: `20260519_151528`
- Created: `2026-05-19T16:43:28.438017+00:00`
- Dataset: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich`
- Catalog: `data/inventory/lereve_clip10000_catalog.jsonl`
- Eval: `evaluation/lereve_clip10000_exact_eval.jsonl`
- Method: `clip_only_rgb_cosine`
- Products indexed: **10000**
- Held-out query images: **10000**
- Latency: **5280189 ms**

## Why This Baseline Is Honest

The query image is not the same file indexed in the catalog. Each case uses a held-out gallery image and asks CLIP to retrieve the same product from a sibling product image.

## Metrics

| Metric | Value |
|---|---:|
| Top-1 exact accuracy | 22.4% |
| Top-3 exact recall | 29.4% |
| Top-5 exact recall | 32.7% |
| Top-10 exact recall | 37.1% |
| Mean reciprocal rank | 0.275 |
| Mean rank | 1023.533 |
| Median rank | 65.0 |
| P90 rank | 3694.0 |
| Wrong-category top-1 rate | 49.8% |
| Query encode failures | 0 |

## Top Failures

### lereve_clip10000_exact_0001 rank=1831

- Expected: `lereve_100780_kgfk15041` / Frock
- Top-1: `lereve_233650_nbgf14174` / Frock / score=0.932262
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100780_kgfk15041/lereve_100780_kgfk15041_gallery_02_7bfde114bd.jpg`
- Product URL: https://www.lerevecraze.com/product/kgfk15041/

### lereve_clip10000_exact_0002 rank=8125

- Expected: `lereve_100530_kbp14775` / Panjabi
- Top-1: `lereve_237217_ltws14008` / Tunic With Shrug / score=0.946825
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100530_kbp14775/lereve_100530_kbp14775_gallery_02_d30ae42c03.jpg`
- Product URL: https://www.lerevecraze.com/product/kbp14775/

### lereve_clip10000_exact_0003 rank=2903

- Expected: `lereve_100796_kgtn14261` / Tunic
- Top-1: `lereve_18954_nbgf14161` / Frock / score=0.943817
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100796_kgtn14261/lereve_100796_kgtn14261_gallery_02_9cd18bea07.jpg`
- Product URL: https://www.lerevecraze.com/product/kgtn14261/

### lereve_clip10000_exact_0004 rank=3

- Expected: `lereve_10052_mlcs14252` / Long Sleeve Casual Shirt
- Top-1: `lereve_301472_mswlp14004` / Long Sleeve Sweater Polo / score=0.869452
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_10052_mlcs14252/lereve_10052_mlcs14252_gallery_02_c23bdd7fa3.jpg`
- Product URL: https://www.lerevecraze.com/product/mlcs14252/

### lereve_clip10000_exact_0005 rank=183

- Expected: `lereve_100415_msts15109` / T-shirt
- Top-1: `lereve_36998_msts14944` / T-shirt / score=0.904361
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100415_msts15109/lereve_100415_msts15109_gallery_02_9cc6292e0e.jpg`
- Product URL: https://www.lerevecraze.com/product/msts15109/

### lereve_clip10000_exact_0006 rank=1301

- Expected: `lereve_101448_lkz15152` / Kameez
- Top-1: `lereve_103749_lpt16029` / Tunic / score=0.936317
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_101448_lkz15152/lereve_101448_lkz15152_gallery_02_fe95a14985.jpg`
- Product URL: https://www.lerevecraze.com/product/lkz15152/

### lereve_clip10000_exact_0007 rank=1844

- Expected: `lereve_100203_skd15305` / Salwar Kameez
- Top-1: `lereve_105756_skd15375` / Salwar Kameez / score=0.843506
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100203_skd15305/lereve_100203_skd15305_gallery_02_0e9f7bd4e4.jpg`
- Product URL: https://www.lerevecraze.com/product/skd15305/

### lereve_clip10000_exact_0008 rank=9016

- Expected: `lereve_102926_lshr15186` / Saree
- Top-1: `lereve_413085_mspo14128` / Short Sleeve Polo / score=0.755621
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_102926_lshr15186/lereve_102926_lshr15186_gallery_02_a9fc29e12d.jpg`
- Product URL: https://www.lerevecraze.com/product/lshr15186/

### lereve_clip10000_exact_0009 rank=13

- Expected: `lereve_102569_lp14487` / Palazzo
- Top-1: `lereve_21735_llsg14058` / Long Shrug / score=0.825886
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_102569_lp14487/lereve_102569_lp14487_gallery_02_7197f33c83.jpg`
- Product URL: https://www.lerevecraze.com/product/lp14487/

### lereve_clip10000_exact_0010 rank=323

- Expected: `lereve_102483_mqp14239` / Bermuda Pant
- Top-1: `lereve_105756_skd15375` / Salwar Kameez / score=0.852204
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_102483_mqp14239/lereve_102483_mqp14239_gallery_02_a31aa63ba8.jpg`
- Product URL: https://www.lerevecraze.com/product/mqp14239/

### lereve_clip10000_exact_0011 rank=2074

- Expected: `lereve_100145_mspo14665` / Short Sleeve Polo
- Top-1: `lereve_232365_mspo14799` / Short Sleeve Polo / score=0.9392
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100145_mspo14665/lereve_100145_mspo14665_gallery_02_fb8881b2ae.jpg`
- Product URL: https://www.lerevecraze.com/product/mspo14665/

### lereve_clip10000_exact_0012 rank=5070

- Expected: `lereve_105721_kgjk14118` / Jacket
- Top-1: `lereve_227956_lpt15772` / Tunic / score=0.916764
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_105721_kgjk14118/lereve_105721_kgjk14118_gallery_02_3b4b1b5c1b.jpg`
- Product URL: https://www.lerevecraze.com/product/kgjk14118/

### lereve_clip10000_exact_0013 rank=8598

- Expected: `lereve_102496_mdp14448` / Men’s bluish grey Denim pants
- Top-1: `lereve_29032_mspo14573` / Short Sleeve Polo / score=0.824964
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_102496_mdp14448/lereve_102496_mdp14448_gallery_02_fa3b69d063.jpg`
- Product URL: https://www.lerevecraze.com/product/mdp14448/

### lereve_clip10000_exact_0015 rank=3

- Expected: `lereve_25126_ldupatta14034` / Dupatta
- Top-1: `lereve_27323_lhsfr14332` / Tunic / score=0.840231
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_25126_ldupatta14034/lereve_25126_ldupatta14034_gallery_02_a89fddc773.jpg`
- Product URL: https://www.lerevecraze.com/product/ldupatta14034/

### lereve_clip10000_exact_0016 rank=10

- Expected: `lereve_105441_lhb14163` / Hand Bag
- Top-1: `lereve_18513_mti14122` / Tupi / score=0.740755
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_105441_lhb14163/lereve_105441_lhb14163_gallery_02_88b495e739.jpg`
- Product URL: https://www.lerevecraze.com/product/lhb14163/

### lereve_clip10000_exact_0017 rank=21

- Expected: `lereve_201709_lwt14112` / Tops
- Top-1: `lereve_105756_skd15375` / Salwar Kameez / score=0.822122
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_201709_lwt14112/lereve_201709_lwt14112_gallery_02_b0aa4a039d.jpg`
- Product URL: https://www.lerevecraze.com/product/lwt14112/

### lereve_clip10000_exact_0018 rank=9

- Expected: `lereve_103300_nbgst14063` / Skirt-tops set
- Top-1: `lereve_32950_kbts14697` / Short Sleeve Round Neck / score=0.833141
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_103300_nbgst14063/lereve_103300_nbgst14063_gallery_02_3537adcc20.jpg`
- Product URL: https://www.lerevecraze.com/product/nbgst14063/

### lereve_clip10000_exact_0019 rank=787

- Expected: `lereve_200309_lahg14047` / Gown
- Top-1: `lereve_228515_lkz15170` / Kameez / score=0.948038
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_200309_lahg14047/lereve_200309_lahg14047_gallery_02_b806772c13.jpg`
- Product URL: https://www.lerevecraze.com/product/lahg14047/

### lereve_clip10000_exact_0020 rank=1842

- Expected: `lereve_106281_mwc14035` / Waistcoat
- Top-1: `lereve_413085_mspo14128` / Short Sleeve Polo / score=0.746356
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_106281_mwc14035/lereve_106281_mwc14035_gallery_02_a9fc29e12d.jpg`
- Product URL: https://www.lerevecraze.com/product/mwc14035/

### lereve_clip10000_exact_0021 rank=9855

- Expected: `lereve_227369_lahg14025` / Gown
- Top-1: `lereve_226204_lpt16410` / Classy patterned Tunic / score=0.913931
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_227369_lahg14025/lereve_227369_lahg14025_gallery_02_9e948bddca.jpg`
- Product URL: https://www.lerevecraze.com/product/lahg14025/


## Sample Successes

- `lereve_clip10000_exact_0014`: ladies sandals → top-1 score `0.954395`
- `lereve_clip10000_exact_0024`: Formal Shoe → top-1 score `0.920059`
- `lereve_clip10000_exact_0040`: ladies sandals → top-1 score `0.85895`
- `lereve_clip10000_exact_0043`: Knit Tops → top-1 score `0.842414`
- `lereve_clip10000_exact_0045`: Gown → top-1 score `0.920698`
- `lereve_clip10000_exact_0050`: Formal Shoe → top-1 score `0.969572`
- `lereve_clip10000_exact_0066`: ladies sandals → top-1 score `0.91971`
- `lereve_clip10000_exact_0068`: Kid’s Bag → top-1 score `0.919633`
- `lereve_clip10000_exact_0069`: Knit Tops → top-1 score `0.838364`
- `lereve_clip10000_exact_0076`: Black Formal Shoe → top-1 score `0.973409`
