# Inventory Few-Shot A/B Eval

- Run time: `2026-04-26 13:44:05`
- A/B dimension: `natural_answer_few_shot_enabled`
- Few-shot examples in scope: `premium recommendation`, `nearby alternative with caveat`, `abstain with follow-up`
- Raw results JSON: `/home/sonjoy/Bar tax/bangla-tax-rag/results/inventory_few_shot_ab_eval_2026-04-26.json`

## Snapshot

| Suite | Few-shot Off | Few-shot On | Delta |
|---|---:|---:|---:|
| Inventory eval matrix pass rate | `0.938` | `0.875` | `-0.063` |
| Inventory eval matrix false-positive abstains | `0` | `0` | `+0` |
| Inventory eval matrix false-negative abstains | `0` | `0` | `+0` |
| Full-system pack pass rate | `0.467` | `0.467` | `+0.000` |
| Full-system pack false-positive abstains | `2` | `2` | `+0` |
| Full-system pack false-negative abstains | `0` | `0` | `+0` |
| Full-system natural-answer fallback rate | `0.909` | `1.000` | `+0.091` |

## Key Deltas

- Inventory eval matrix pass count: `15/16` -> `14/16`.
- Full-system pack pass count: `7/15` -> `7/15`.
- Full-system natural-answer attempts: `11` -> `11`.
- Full-system natural-answer fallback cases: `10` -> `11`.
- Full-system natural-answer success cases: `1` -> `0`.

## Regression Read

- Natural-answer fallback rate got worse with few-shot on.

## Format / Hallucination Signals

- Few-shot off format flags: `{'answer_plan_verification_issue': 1}`
- Few-shot on format flags: `{'answer_plan_verification_issue': 1}`
- Interpretation: these flags include JSON/markdown leakage, multiple follow-up questions, few-shot example leakage, and verifier-raised answer issues.

## Changed Full-System Cases

### Budget earbuds

- Pass: `True` -> `True`
- Engine: `deterministic` -> `deterministic`
- Abstained: `False` -> `False`
- Fallback reason: `Natural answer model returned invalid structured output; deterministic fallback was used.` -> `Natural answer failed final answer verification; deterministic fallback was used.`
- Format flags: `[]` -> `[]`

**Few-shot off**

```text
I would lead with AirTone Mini Earbuds. It is the strongest budget-friendly match in the current catalog. It is the lowest-priced strong match at USD 69.00.
```

**Few-shot on**

```text
I would lead with AirTone Mini Earbuds. It is the strongest budget-friendly match in the current catalog. It is the lowest-priced strong match at USD 69.00.
```

### Laptop cross-sell

- Pass: `False` -> `False`
- Engine: `natural` -> `deterministic`
- Abstained: `False` -> `False`
- Fallback reason: `None` -> `Natural answer model returned invalid structured output; deterministic fallback was used.`
- Format flags: `[]` -> `[]`

**Few-shot off**

```text
The Nimbus 14 Business Ultrabook (score 0.8358) is the primary recommendation for a business ultrabook, offering 16GB RAM and 512GB SSD in a portable form factor. The Nimbus 16 Pro Creator Laptop (score 0.8352) is a premium alternative with 32GB RAM and 1TB SSD, ideal for intensive creative work but at a higher price point. Both are excellent choices depending on your priority between portability (14) or performance (16 Pro).
```

**Few-shot on**

```text
For this customer, I would start with Nimbus 14 Business Ultrabook as the premium option. It supports a premium pitch at USD 1199.00. There are only 9 unit(s) in stock, which gives you a legitimate urgency point. It sits in Computing under Nimbus. The product description highlights Lightweight business laptop for managers, analysts, and frequent travelers. Structured details include battery life: 12 hours. If the customer needs a more accessible price point than Nimbus 14 Business Ultrabook, I would keep Nimbus 16 Pro Creator Laptop ready as the fallback at USD 1699.00. I am keeping this recommendation grounded in the current catalog only, so I am not claiming anything that is not in the stored product data. Do you want a more accessible fallback next to Nimbus 14 Business Ultrabook, or should I keep the conversation fully premium?
```

### Portable storage

- Pass: `False` -> `False`
- Engine: `deterministic` -> `deterministic`
- Abstained: `False` -> `False`
- Fallback reason: `Natural answer model returned invalid structured output; deterministic fallback was used.` -> `Natural answer failed final answer verification; deterministic fallback was used.`
- Format flags: `[]` -> `[]`

**Few-shot off**

```text
I would start by recommending FlashPeak 1TB Portable SSD. It is the strongest overall match from the current catalog. The current price is USD 129.00. If they push back on price, I would shift to ArchiveBox 4TB Desktop Drive.
```

**Few-shot on**

```text
I would start by recommending FlashPeak 1TB Portable SSD. It is the strongest overall match from the current catalog. The current price is USD 129.00. If they push back on price, I would shift to ArchiveBox 4TB Desktop Drive.
```

### Premium headphones

- Pass: `True` -> `True`
- Engine: `deterministic` -> `deterministic`
- Abstained: `False` -> `False`
- Fallback reason: `Natural answer failed final answer verification; deterministic fallback was used.` -> `Natural answer model returned invalid structured output; deterministic fallback was used.`
- Format flags: `[]` -> `[]`

**Few-shot off**

```text
I would lead with Auralite Flex ANC Headphones. It is the strongest budget-friendly match in the current catalog. It stays within the requested value range at USD 249.00. It currently has 14 unit(s) in stock. It sits in Audio under Auralite. The product description highlights Wireless over-ear headphones with active noise cancellation for focused office calls and travel. Structured details include connectivity: Bluetooth 5.3; battery life: 35 hours; use case: office calls. If the customer wants to step up from Auralite Flex ANC Headphones, the next option to show is BassForge DJ Monitor Headphones at USD 149.00. I am keeping this recommendation grounded in the current catalog only, so I am not claiming anything that is not in the stored product data. Are we selling into Audio? Also tell me whether the buyer cares more about budget, premium feel, or immediate availability.
```

**Few-shot on**

```text
I would lead with Auralite Flex ANC Headphones. It is the strongest budget-friendly match in the current catalog. It stays within the requested value range at USD 249.00. It currently has 14 unit(s) in stock. It sits in Audio under Auralite. The product description highlights Wireless over-ear headphones with active noise cancellation for focused office calls and travel. Structured details include connectivity: Bluetooth 5.3; battery life: 35 hours; use case: office calls. If the customer wants to step up from Auralite Flex ANC Headphones, the next option to show is BassForge DJ Monitor Headphones at USD 149.00. I am keeping this recommendation grounded in the current catalog only, so I am not claiming anything that is not in the stored product data. Are we selling into Audio? Also tell me whether the buyer cares more about budget, premium feel, or immediate availability.
```
