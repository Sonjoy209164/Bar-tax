# Le Reve Image Search Comparison 10000

- Run ID: `20260519_164406`
- Created: `2026-05-19T16:44:06.509090+00:00`
- Catalog: `data/inventory/lereve_clip10000_catalog.jsonl`
- Eval: `evaluation/lereve_clip10000_exact_eval.jsonl`
- Cache: `data/inventory/lereve_clip10000_clip_vectors.json`
- Products indexed: **10000**
- Held-out query images: **10000**
- Latency: **27614 ms**

## Method Notes

- `clip_only_rgb_cosine`: Raw CLIP cosine over indexed primary product images.
- `clip_metadata_factor_rerank`: CLIP plus query category/color factors from the labeled eval set. This is an upper-bound proxy for a future visual factor extractor, not a customer-visible oracle.
- `cif_rag_without_claim_contracts`: Ablation: keeps the visual risk score/margin gate, but removes typed claim-contract evidence such as category agreement and product-photo proof before accepting an exact-product claim.
- `cif_rag_without_risk_policy`: Ablation: keeps typed claim-contract evidence such as category and product-photo proof, but removes score/margin risk gating before accepting an exact-product claim.
- `cif_rag_guarded_decision`: Uses the metadata-reranked list, then only accepts exact product claims when category, score, margin, and product-photo evidence pass a conservative commerce-risk gate.

## Main Table

| Method | Top-1 Exact | Top-3 Recall | Top-5 Recall | Top-10 Recall | Wrong Category Top-1 | Accepted Exact Rate | Accepted Exact Precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `clip_only_rgb_cosine` | 22.7% | 29.5% | 32.7% | 37.1% | 53.9% | 100.0% | 22.4% |
| `clip_metadata_factor_rerank` | 37.8% | 50.7% | 56.5% | 64.2% | 7.0% | 100.0% | 37.4% |
| `cif_rag_without_claim_contracts` | 14.8% | 50.7% | 56.5% | 64.2% | 7.0% | 20.9% | 70.6% |
| `cif_rag_without_risk_policy` | 35.7% | 50.7% | 56.5% | 64.2% | 7.0% | 93.0% | 38.4% |
| `cif_rag_guarded_decision` | 14.0% | 50.7% | 56.5% | 64.2% | 7.0% | 18.7% | 74.9% |

## Safety Metrics

| Method | Accepted Wrong Exact / All | Accepted Wrong Category / Accepted | Abstain Or Non-Exact | MRR | Median Rank | P90 Rank |
|---|---:|---:|---:|---:|---:|---:|
| `clip_only_rgb_cosine` | 77.6% | 53.9% | 0.0% | 0.277 | 65.0 | 3693.0 |
| `clip_metadata_factor_rerank` | 62.6% | 7.0% | 0.0% | 0.468 | 3.0 | 174.0 |
| `cif_rag_without_claim_contracts` | 6.2% | 10.6% | 79.1% | 0.468 | 3.0 | 174.0 |
| `cif_rag_without_risk_policy` | 57.3% | 0.0% | 7.0% | 0.468 | 3.0 | 174.0 |
| `cif_rag_guarded_decision` | 4.7% | 0.0% | 81.3% | 0.468 | 3.0 | 174.0 |

## Top CIF Blocks

### lereve_clip10000_exact_0001 rank=590

- Expected: `lereve_100780_kgfk15041` / Frock
- Top-1 candidate: `lereve_233650_nbgf14174` / Frock
- Decision: `no_confident_match` / category guard blocked exact product claim
- Scores: clip `0.932262`, final `0.967262`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100780_kgfk15041/lereve_100780_kgfk15041_gallery_02_7bfde114bd.jpg`

### lereve_clip10000_exact_0002 rank=575

- Expected: `lereve_100530_kbp14775` / Panjabi
- Top-1 candidate: `lereve_203055_kbp14670` / Panjabi
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.936825`, final `1.151825`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100530_kbp14775/lereve_100530_kbp14775_gallery_02_d30ae42c03.jpg`

### lereve_clip10000_exact_0003 rank=270

- Expected: `lereve_100796_kgtn14261` / Tunic
- Top-1 candidate: `lereve_22305_kgtn14222` / Tunic
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.893494`, final `1.108494`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100796_kgtn14261/lereve_100796_kgtn14261_gallery_02_9cd18bea07.jpg`

### lereve_clip10000_exact_0005 rank=17

- Expected: `lereve_100415_msts15109` / T-shirt
- Top-1 candidate: `lereve_329841_msts15471` / Slim-fit Cotton Short Sleeve T-shirt
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.85831`, final `1.07331`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100415_msts15109/lereve_100415_msts15109_gallery_02_9cc6292e0e.jpg`

### lereve_clip10000_exact_0006 rank=142

- Expected: `lereve_101448_lkz15152` / Kameez
- Top-1 candidate: `lereve_288688_lkz15694` / Black princess-cut Kameez
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.909983`, final `1.124983`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_101448_lkz15152/lereve_101448_lkz15152_gallery_02_fe95a14985.jpg`

### lereve_clip10000_exact_0008 rank=120

- Expected: `lereve_102926_lshr15186` / Saree
- Top-1 candidate: `lereve_362543_lshry14869` / Bottle Green & Copper Toned Exclusive Kanjeevaram Inspired Saree
- Decision: `no_confident_match` / visual score below commerce-safe threshold
- Scores: clip `0.536758`, final `0.751758`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_102926_lshr15186/lereve_102926_lshr15186_gallery_02_a9fc29e12d.jpg`

### lereve_clip10000_exact_0010 rank=9

- Expected: `lereve_102483_mqp14239` / Bermuda Pant
- Top-1 candidate: `lereve_270889_kbqp14195` / Kid’s boy tourist motifs printed pants
- Decision: `no_confident_match` / visual score below commerce-safe threshold
- Scores: clip `0.775717`, final `0.990717`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_102483_mqp14239/lereve_102483_mqp14239_gallery_02_a31aa63ba8.jpg`

### lereve_clip10000_exact_0013 rank=488

- Expected: `lereve_102496_mdp14448` / Men’s bluish grey Denim pants
- Top-1 candidate: `lereve_359649_mdp14532` / Blue Denim Pant
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.816258`, final `1.031258`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_102496_mdp14448/lereve_102496_mdp14448_gallery_02_fa3b69d063.jpg`

### lereve_clip10000_exact_0019 rank=9

- Expected: `lereve_200309_lahg14047` / Gown
- Top-1 candidate: `lereve_288215_lgn14093` / Grey floral Gown
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.932714`, final `1.100714`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_200309_lahg14047/lereve_200309_lahg14047_gallery_02_b806772c13.jpg`

### lereve_clip10000_exact_0020 rank=17

- Expected: `lereve_106281_mwc14035` / Waistcoat
- Top-1 candidate: `lereve_459153_mwc14121` / Green Jacquard Waistcoat
- Decision: `no_confident_match` / visual score below commerce-safe threshold
- Scores: clip `0.62546`, final `0.84046`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_106281_mwc14035/lereve_106281_mwc14035_gallery_02_a9fc29e12d.jpg`

### lereve_clip10000_exact_0021 rank=5310

- Expected: `lereve_227369_lahg14025` / Gown
- Top-1 candidate: `lereve_519064_lahg14132` / Blue Satin Georgette Abaya
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.878682`, final `1.099682`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_227369_lahg14025/lereve_227369_lahg14025_gallery_02_9e948bddca.jpg`

### lereve_clip10000_exact_0023 rank=17

- Expected: `lereve_459508_lisf14001` / Infinity Scarf
- Top-1 candidate: `lereve_459518_lisfs14001` / Infinity Scarf Set
- Decision: `no_confident_match` / visual score below commerce-safe threshold
- Scores: clip `0.745139`, final `0.925139`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_459508_lisf14001/lereve_459508_lisf14001_gallery_02_0eb5424655.jpg`

### lereve_clip10000_exact_0027 rank=118

- Expected: `lereve_102014_ljst14015` / Jump Suit
- Top-1 candidate: `lereve_105005_msrn14061` / Sarong
- Decision: `no_confident_match` / category guard blocked exact product claim
- Scores: clip `0.883726`, final `0.918726`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_102014_ljst14015/lereve_102014_ljst14015_gallery_02_63cd0eade7.jpg`

### lereve_clip10000_exact_0029 rank=65

- Expected: `lereve_100804_kgtn14367` / Tunic
- Top-1 candidate: `lereve_21352_kgtn14184` / Tunic
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.903535`, final `1.118535`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100804_kgtn14367/lereve_100804_kgtn14367_gallery_02_aca0a3b526.jpg`

### lereve_clip10000_exact_0030 rank=453

- Expected: `lereve_100565_kbpo14146` / Short Sleeve Polo-Shirt
- Top-1 candidate: `lereve_32118_kbpo14417` / Short Sleeve Polo-Shirt
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.857409`, final `1.072409`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100565_kbpo14146/lereve_100565_kbpo14146_gallery_02_112f45ed6d.jpg`

### lereve_clip10000_exact_0032 rank=303

- Expected: `lereve_101635_lkz14721` / Kameez
- Top-1 candidate: `lereve_32061_lkz14495` / Kameez
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.914299`, final `1.129299`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_101635_lkz14721/lereve_101635_lkz14721_gallery_02_a42807e045.jpg`

### lereve_clip10000_exact_0033 rank=32

- Expected: `lereve_100788_kgskd14238` / Salwar Kameez
- Top-1 candidate: `lereve_236384_kgskd14167` / Salwar Kameez
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.895968`, final `1.116968`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100788_kgskd14238/lereve_100788_kgskd14238_gallery_02_f2cd419119.jpg`

### lereve_clip10000_exact_0034 rank=153

- Expected: `lereve_102938_lshr15223` / Saree
- Top-1 candidate: `lereve_341290_lshrin14578` / Saree
- Decision: `no_confident_match` / visual score below commerce-safe threshold
- Scores: clip `0.566433`, final `0.781433`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_102938_lshr15223/lereve_102938_lshr15223_gallery_02_a9fc29e12d.jpg`

### lereve_clip10000_exact_0035 rank=90

- Expected: `lereve_103232_lp14595` / Palazzo
- Top-1 candidate: `lereve_322914_lp14873` / Palazzo
- Decision: `no_confident_match` / visual score below commerce-safe threshold
- Scores: clip `0.733835`, final `0.948835`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_103232_lp14595/lereve_103232_lp14595_gallery_02_284dd2bedf.jpg`

### lereve_clip10000_exact_0037 rank=199

- Expected: `lereve_100186_mspo14721` / Short Sleeve Polo
- Top-1 candidate: `lereve_232341_mspo14778` / Short Sleeve Polo
- Decision: `similar_style` / visually plausible but exact margin or score is unsafe
- Scores: clip `0.968753`, final `1.183753`
- Query image: `/mnt/nvme0n1p3/sonjoy/lereve_products_dataset_rich/images/lereve_100186_mspo14721/lereve_100186_mspo14721_gallery_02_615827a696.jpg`
