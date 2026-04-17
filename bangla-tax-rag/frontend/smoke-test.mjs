import { readFile } from "node:fs/promises";

const config = await readJson(new URL("./config.local.json", import.meta.url));
const sample = await readJson(new URL("./data/products.json", import.meta.url));

const apiBaseUrl = normalizeBaseUrl(process.env.RAG_BASE_URL || config.apiBaseUrl);
const apiKey = process.env.RAG_API_KEY || config.apiKey;

if (!apiBaseUrl || !apiKey) {
  throw new Error("Set frontend/config.local.json or RAG_BASE_URL and RAG_API_KEY before running this smoke test.");
}

console.log(`Testing RAG API at ${apiBaseUrl}`);

const inventoryStatus = await apiGet("/inventory/status");
console.log(`Status: ${inventoryStatus.status}, products=${inventoryStatus.total_items}, vector=${inventoryStatus.vector_backend}`);

const upsertCatalog = await apiPost("/inventory/items/upsert", { items: sample.items });
console.log(`Catalog sync: upserted=${upsertCatalog.upserted_count}, total=${upsertCatalog.total_items}`);

const upsertSignals = await apiPost("/inventory/business/signals/upsert", {
  signals: sample.business_signals || []
});
console.log(`Business sync: upserted=${upsertSignals.upserted_count}, total=${upsertSignals.total_signals}`);

const normalAnswer = await apiPost("/inventory/ask", {
  question: "show me smart watches under 250",
  assistant_mode: "sales",
  reply_style: "short",
  top_k: 6,
  answer_engine: "auto"
});
printAnswer("Normal chat", normalAnswer);

const agenticAnswer = await apiPost("/inventory/agentic/ask", {
  question: "which products should I restock first and why?",
  assistant_mode: "support",
  reply_style: "detailed",
  top_k: 6,
  answer_engine: "auto",
  max_reasoning_steps: 4,
  available_data_domains: [
    "catalog",
    "sales",
    "orders",
    "inventory_snapshots",
    "suppliers",
    "margins",
    "returns",
    "customers"
  ]
});
printAnswer("Agentic chat", agenticAnswer);

async function readJson(url) {
  return JSON.parse(await readFile(url, "utf-8"));
}

async function apiGet(path) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: buildHeaders()
  });
  return parseApiResponse(response);
}

async function apiPost(path, body) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(body)
  });
  return parseApiResponse(response);
}

function buildHeaders() {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-API-Key": apiKey
  };
}

async function parseApiResponse(response) {
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const message = data?.detail?.message || data?.detail?.error || data?.message || response.statusText;
    throw new Error(`${response.status} ${message}`);
  }
  return data;
}

function normalizeBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function printAnswer(label, response) {
  const productIds = [
    ...(response.recommended_product_ids || []),
    ...(response.cross_sell_product_ids || []),
    ...(response.hits || []).map((hit) => hit.product_id)
  ];
  console.log(`${label}: hits=${response.total_hits ?? 0}, confidence=${Math.round((response.confidence_score || 0) * 100)}%, trace=${response.trace_id || "none"}`);
  console.log(`Products: ${Array.from(new Set(productIds)).slice(0, 6).join(", ") || "none"}`);
  console.log(`Answer: ${String(response.answer || "").slice(0, 260)}`);
}
