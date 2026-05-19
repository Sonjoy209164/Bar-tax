from __future__ import annotations

import re


# Canonical form for every raw category token.  The keys are the output of
# normalize_token() applied to the raw label; the values are the canonical
# labels the rest of the system compares against.
CANONICAL: dict[str, str] = {
    # Dupatta / Scarf / Hijab — Le Reve groups these as accessories
    "dupatta": "dupatta",
    "scarf": "dupatta",
    "hijab": "dupatta",
    "stole": "dupatta",
    "infinity_scarf": "dupatta",
    "infinity_scarf_set": "dupatta",
    # Frock (kids/girls)
    "frock": "frock",
    "girls_frock": "frock",
    "kid_frock": "frock",
    "kids_frock": "frock",
    "baby_frock": "frock",
    # Panjabi variants
    "panjabi": "panjabi",
    "punjabi": "panjabi",
    "kids_panjabi": "panjabi",
    "boy_panjabi": "panjabi",
    "fatua": "panjabi",
    # Kameez
    "kameez": "kameez",
    # Salwar Kameez
    "salwar_kameez": "salwar_kameez",
    "kameez_set": "salwar_kameez",
    "three_piece": "salwar_kameez",
    "kameez_salwar": "salwar_kameez",
    # T-Shirt
    "t_shirt": "t_shirt",
    "tee": "t_shirt",
    "short_sleeve_round_neck": "t_shirt",
    "long_sleeve_round_neck": "t_shirt",
    "short_sleeve_v_neck": "t_shirt",
    # Polo
    "polo": "polo",
    "short_sleeve_polo": "polo",
    "short_sleeve_polo_shirt": "polo",
    "polo_shirt": "polo",
    # Shirt
    "shirt": "shirt",
    "casual_shirt": "shirt",
    "long_sleeve_casual_shirt": "shirt",
    # Pants — generic
    "pant": "pant",
    "trouser": "pant",
    "bermuda_pant": "pant",
    "three_quarter_pant": "pant",
    "woven_long_pant": "pant",
    "chinos": "pant",
    "formal_pant": "pant",
    "formal_pants": "pant",
    "leggings": "pant",
    # Jeans / Denim
    "jeans": "jeans",
    "denim_pant": "jeans",
    "denim_long": "jeans",
    # Sandals / Footwear
    "sandal": "sandal",
    "juttie": "sandal",
    "mules": "sandal",
    "slipper": "sandal",
    "shoe": "sandal",
    # Jumpsuit
    "jump_suit": "jumpsuit",
    "jumpsuit": "jumpsuit",
    # Direct passthrough
    "tunic": "tunic",
    "saree": "saree",
    "palazzo": "palazzo",
    "jacket": "jacket",
    "bag": "bag",
    "top": "top",
    "skirt": "skirt",
    "gown": "gown",
    "waistcoat": "waistcoat",
    "abaya": "abaya",
    "maxi": "maxi",
    "dress": "dress",
    "sarong": "sarong",
}

# Compatibility groups: any two canonicals within the same frozenset are
# considered commerce-safe siblings.  Used by the category guard so that
# minor labeling differences (e.g. "pant" vs "jeans") do not block a
# correct exact-product claim.
_COMPATIBILITY_GROUPS: list[frozenset[str]] = [
    frozenset({"pant", "jeans"}),           # bottoms (denim vs non-denim)
    frozenset({"pant", "trouser"}),         # legacy alias kept for older catalogs
    frozenset({"dupatta", "scarf"}),        # already canonicalized but kept for clarity
    frozenset({"sandal", "shoe"}),          # footwear
    frozenset({"polo", "t_shirt"}),         # casual men's tops
    frozenset({"kameez", "salwar_kameez"}), # women's ethnic: solo vs set
    frozenset({"gown", "maxi", "dress"}),   # women's long formal
]

# Precompute: canonical → frozenset of all canonicals in the same group(s).
_COMPAT_LOOKUP: dict[str, frozenset[str]] = {}
for _group in _COMPATIBILITY_GROUPS:
    for _canon in _group:
        existing = _COMPAT_LOOKUP.get(_canon, frozenset())
        _COMPAT_LOOKUP[_canon] = existing | _group


def _normalize_token(value: str) -> str:
    text = str(value or "").casefold().replace("&", "and")
    chars = [c if c.isalnum() else " " for c in text]
    return "_".join("".join(chars).split())


def canonicalize(raw: str) -> str:
    """Return the canonical category label for a raw string.

    Unknown or empty inputs return an empty string so callers can detect
    "no category evidence" explicitly.
    """
    if not raw:
        return ""
    token = _normalize_token(raw)
    if not token or token in {"unknown", "none", "n_a", "fashion", "product"}:
        return ""
    return CANONICAL.get(token, token)


def compatible_for_exact(cat1: str, cat2: str) -> bool:
    """Return True when two raw category strings are close enough for the
    category guard to allow an exact-product claim.

    Two categories are compatible when:
    - both canonicalize to the same value, OR
    - they are members of the same compatibility group.
    """
    c1 = canonicalize(cat1)
    c2 = canonicalize(cat2)
    if not c1 or not c2:
        # Missing evidence on either side: do not block.
        return True
    if c1 == c2:
        return True
    siblings = _COMPAT_LOOKUP.get(c1, frozenset())
    return c2 in siblings


def compatible_categories_for(query_cat: str) -> frozenset[str]:
    """Return the set of canonical categories compatible with *query_cat*.

    Used to build the union mask when doing vectorized category matching.
    Returns a frozenset containing at least the canonical form of *query_cat*.
    Returns an empty frozenset when *query_cat* is unknown (no evidence).
    """
    canon = canonicalize(query_cat)
    if not canon:
        return frozenset()
    siblings = _COMPAT_LOOKUP.get(canon, frozenset())
    return siblings | {canon}


def normalize_raw_category(raw: str) -> str:
    """Normalize a raw category string to a token (without canonicalization).

    Kept for backward-compatible callers that only need the normalized token.
    """
    return _normalize_token(raw)
