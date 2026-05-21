const state = {
  apiBaseUrl: window.location.origin,
  apiKey: "5230ff9faefe885d22345444e006cab576acdae5ea75d499",
  conversation: [],
  focusedProductIds: [],
  lastAnswerPlan: null,
  busy: false,
  sessionId: "session-" + Math.random().toString(36).slice(2, 10),
  orderActive: false,
  awaitingOrderConfirm: false,
  pendingImageB64: null,
  pendingImageName: null,
  cart: [],                 // [{product_id, name, unit_price, quantity}]
  micRecording: false,
  recognition: null,
  catalogOpen: true,
  messagesVisible: true,
  catalogLoaded: false,
  catalogItems: [],
  assistantMode: "sales",
  replyStyle: "detailed",
  answerEngine: "deterministic",
};

const IMAGE_UPLOAD_MAX_EDGE = 1280;
const IMAGE_UPLOAD_JPEG_QUALITY = 0.86;

const el = {
  workspace:       document.querySelector("#workspace"),
  chatPanel:       document.querySelector("#chatPanel"),
  messages:        document.querySelector("#messages"),
  messagesToggle:  document.querySelector("#messagesToggle"),
  messagesStatus:  document.querySelector("#messagesStatus"),
  form:            document.querySelector("#chatForm"),
  input:           document.querySelector("#chatInput"),
  send:            document.querySelector("#sendButton"),
  statusPill:      document.querySelector("#statusPill"),
  statusText:      document.querySelector("#statusText"),
  chips:           document.querySelector("#chips"),
  imageUploadArea: document.querySelector("#imageUploadArea"),
  imageInput:      document.querySelector("#imageInput"),
  imagePreview:    document.querySelector("#imagePreview"),
  clearImageBtn:   document.querySelector("#clearImageBtn"),
  imageLabel:      document.querySelector("#imageLabel"),
  orderStatusBar:  document.querySelector("#orderStatusBar"),
  orderConfirmBar: document.querySelector("#orderConfirmBar"),
  confirmOrderBtn: document.querySelector("#confirmOrderBtn"),
  cancelOrderBtn:  document.querySelector("#cancelOrderBtn"),
  cartPanel:       document.querySelector("#cartPanel"),
  cartToggle:      document.querySelector("#cartToggle"),
  cartItems:       document.querySelector("#cartItems"),
  cartCount:       document.querySelector("#cartCount"),
  cartChevron:     document.querySelector("#cartChevron"),
  cartTotalRow:    document.querySelector("#cartTotalRow"),
  cartSubtotal:    document.querySelector("#cartSubtotal"),
  micBtn:          document.querySelector("#micBtn"),
  trackBar:        document.querySelector("#trackBar"),
  trackInput:      document.querySelector("#trackInput"),
  trackBtn:        document.querySelector("#trackBtn"),
  trackClose:      document.querySelector("#trackClose"),
  trackOrderToggle:document.querySelector("#trackOrderToggle"),
  catalogToggle:   document.querySelector("#catalogToggle"),
  catalogRefresh:  document.querySelector("#catalogRefresh"),
  catalogSearch:   document.querySelector("#catalogSearch"),
  catalogCategory: document.querySelector("#catalogCategory"),
  catalogItems:    document.querySelector("#catalogItems"),
  catalogCount:    document.querySelector("#catalogCount"),
  catalogEmpty:    document.querySelector("#catalogEmpty"),
  imageExamples:   document.querySelector("#imageExamples"),
  textExamples:    document.querySelector("#textExamples"),
  catalogExamples: document.querySelector("#catalogExamples"),
  memoryExamples:  document.querySelector("#memoryExamples"),
};

init();

async function init() {
  await loadLocalConfig();
  await loadRuntimeConfig();
  bindEvents();
  initVoiceInput();
  setCatalogOpen(true);
  setMessagesVisible(true);
  addMessage(
    "assistant",
    "Ready. Ask in Bangla, Banglish, or English — products, styling, delivery, orders, comparisons. I’ll answer naturally from the catalog, and I’ll say when I’m unsure."
  );
  await checkHealth();
  await loadCatalog({ quiet: true });
}

async function loadLocalConfig() {
  try {
    const resp = await fetch("./config.local.json", { cache: "no-store" });
    if (!resp.ok) return;
    const config = await resp.json();
    if (config.apiBaseUrl) state.apiBaseUrl = String(config.apiBaseUrl).replace(/\/+$/, "");
    if (typeof config.apiKey === "string") state.apiKey = config.apiKey.trim();
  } catch (_) {}
}

async function loadRuntimeConfig() {
  try {
    const resp = await fetch("./runtime-config.json", { cache: "no-store" });
    if (!resp.ok) return;
    const config = await resp.json();
    if (config.apiBaseUrl) state.apiBaseUrl = String(config.apiBaseUrl).replace(/\/+$/, "");
  } catch (_) {}
}

function bindEvents() {
  el.form.addEventListener("submit", e => { e.preventDefault(); void handleSubmit(); });
  el.input.addEventListener("input", resizeInput);
  el.input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void handleSubmit(); }
  });
  el.chips.addEventListener("click", e => {
    const btn = e.target.closest("button");
    if (!btn) return;
    el.input.value = btn.dataset.question || btn.textContent.trim();
    resizeInput();
    el.input.focus();
  });
  el.imageInput.addEventListener("change", handleImageSelect);
  bindImageDropAndPaste();
  el.imageExamples?.addEventListener("click", e => {
    const card = e.target.closest(".image-example-card");
    if (!card) return;
    void useImageExample(card);
  });
  el.textExamples?.addEventListener("click", e => {
    const card = e.target.closest(".text-example-card");
    if (!card) return;
    setInputQuestion(card.dataset.question || "");
  });
  el.catalogExamples?.addEventListener("click", e => {
    const card = e.target.closest(".catalog-example-card");
    if (!card) return;
    setInputQuestion(card.dataset.question || "");
  });
  el.memoryExamples?.addEventListener("click", e => {
    const card = e.target.closest(".memory-example-card");
    if (!card) return;
    setInputQuestion(card.dataset.question || "");
  });
  el.clearImageBtn.addEventListener("click", clearImage);
  el.confirmOrderBtn.addEventListener("click", () => void sendMessage("yes"));
  el.cancelOrderBtn.addEventListener("click", () => void cancelOrder());
  el.cartToggle.addEventListener("click", toggleCart);
  el.messagesToggle.addEventListener("click", () => setMessagesVisible(!state.messagesVisible));
  el.micBtn.addEventListener("click", toggleMic);
  el.trackOrderToggle.addEventListener("click", () => el.trackBar.classList.toggle("active"));
  el.trackClose.addEventListener("click", () => el.trackBar.classList.remove("active"));
  el.trackBtn.addEventListener("click", () => void trackOrder());
  el.catalogToggle.addEventListener("click", () => {
    setCatalogOpen(!state.catalogOpen);
    if (state.catalogOpen && !state.catalogLoaded) void loadCatalog();
  });
  el.catalogRefresh.addEventListener("click", () => void loadCatalog({ force: true }));
  el.catalogSearch.addEventListener("input", renderCatalog);
  el.catalogCategory.addEventListener("change", renderCatalog);
  el.catalogItems.addEventListener("click", e => {
    const askBtn = e.target.closest(".catalog-ask-btn");
    if (!askBtn) return;
    el.input.value = askBtn.dataset.question || "";
    resizeInput();
    el.input.focus();
    if (window.innerWidth < 920) setCatalogOpen(false);
  });
}

function setInputQuestion(question) {
  el.input.value = question || "";
  resizeInput();
  el.input.focus();
}

function setMessagesVisible(visible) {
  state.messagesVisible = Boolean(visible);
  el.chatPanel.classList.toggle("messages-hidden", !state.messagesVisible);
  el.messagesToggle.textContent = state.messagesVisible ? "Hide Messages" : "Show Messages";
  el.messagesToggle.setAttribute("aria-expanded", String(state.messagesVisible));
  el.messagesStatus.textContent = state.messagesVisible
    ? "Visible. Memory still uses the last 8 turns."
    : "Hidden. Memory still uses the last 8 turns.";
  if (state.messagesVisible) {
    requestAnimationFrame(() => {
      el.messages.scrollTop = el.messages.scrollHeight;
    });
  }
}

// ── Catalog Panel ──────────────────────────────────────────────────────────────

function setCatalogOpen(open) {
  state.catalogOpen = Boolean(open);
  el.workspace.classList.toggle("catalog-hidden", !state.catalogOpen);
  el.catalogToggle.textContent = state.catalogOpen ? "Hide Catalog" : "Show Catalog";
  el.catalogToggle.setAttribute("aria-expanded", String(state.catalogOpen));
}

async function loadCatalog(options = {}) {
  if (state.catalogLoaded && !options.force) {
    renderCatalog();
    renderCatalogExamples();
    renderMemoryExamples();
    return;
  }
  el.catalogCount.textContent = "Loading catalog...";
  el.catalogItems.innerHTML = "";
  const loading = document.createElement("div");
  loading.className = "catalog-empty";
  loading.textContent = "Loading products...";
  el.catalogItems.appendChild(loading);

  try {
    const data = await apiGet("/inventory/items");
    state.catalogItems = Array.isArray(data.items) ? data.items : [];
    state.catalogLoaded = true;
    renderCatalogCategories();
    renderCatalog();
    renderCatalogExamples();
    renderMemoryExamples();
  } catch (error) {
    el.catalogCount.textContent = "Catalog unavailable";
    el.catalogItems.innerHTML = "";
    const empty = document.createElement("div");
    empty.className = "catalog-empty";
    empty.textContent = `Catalog load failed: ${error.message}`;
    el.catalogItems.appendChild(empty);
    if (!options.quiet) addMessage("assistant", `Catalog load failed: ${error.message}`);
  }
}

function renderCatalogCategories() {
  const current = el.catalogCategory.value;
  const categories = Array.from(new Set(
    state.catalogItems.map(item => item.category || item.attributes?.category_key || "Other").filter(Boolean)
  )).sort((a, b) => a.localeCompare(b));

  el.catalogCategory.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All";
  el.catalogCategory.appendChild(all);
  categories.forEach(category => {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    el.catalogCategory.appendChild(option);
  });
  if (categories.includes(current)) el.catalogCategory.value = current;
}

function renderCatalog() {
  const query = normalizeCatalogText(el.catalogSearch.value);
  const category = el.catalogCategory.value;
  const filtered = state.catalogItems.filter(item => {
    const itemCategory = item.category || item.attributes?.category_key || "Other";
    if (category && itemCategory !== category) return false;
    if (!query) return true;
    return catalogSearchText(item).includes(query);
  });

  el.catalogCount.textContent = `${filtered.length} of ${state.catalogItems.length} products`;
  el.catalogItems.innerHTML = "";

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "catalog-empty";
    empty.textContent = state.catalogItems.length ? "No products match this filter." : "No products loaded yet.";
    el.catalogItems.appendChild(empty);
    return;
  }

  filtered.forEach(item => el.catalogItems.appendChild(renderCatalogItem(item)));
}

function renderCatalogExamples() {
  if (!el.catalogExamples) return;
  el.catalogExamples.innerHTML = "";
  const examples = pickCatalogExamples();
  if (!examples.length) {
    const empty = document.createElement("div");
    empty.className = "catalog-example-empty";
    empty.textContent = "No live catalog examples available yet.";
    el.catalogExamples.appendChild(empty);
    return;
  }

  examples.forEach(({ item, target }) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "catalog-example-card";
    card.dataset.question = target.question(item);

    const imageUrl = firstCatalogImageUrl(item);
    if (imageUrl) {
      const img = document.createElement("img");
      img.src = resolveCatalogAssetUrl(imageUrl);
      img.alt = item.name || item.product_id || "Catalog product";
      img.loading = "lazy";
      card.appendChild(img);
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "catalog-example-placeholder";
      placeholder.textContent = "No image";
      card.appendChild(placeholder);
    }

    const body = document.createElement("span");
    body.className = "catalog-example-body";

    const label = document.createElement("span");
    label.className = "catalog-example-label";
    label.textContent = target.label;
    body.appendChild(label);

    const name = document.createElement("span");
    name.className = "catalog-example-name";
    name.textContent = item.name || item.product_id || "Product";
    body.appendChild(name);

    const facts = document.createElement("span");
    facts.className = "catalog-example-facts";
    facts.textContent = compactCatalogFacts(item);
    body.appendChild(facts);

    const question = document.createElement("span");
    question.className = "catalog-example-question";
    question.textContent = card.dataset.question;
    body.appendChild(question);

    card.appendChild(body);
    el.catalogExamples.appendChild(card);
  });
}

function renderMemoryExamples() {
  if (!el.memoryExamples) return;
  el.memoryExamples.innerHTML = "";
  const anchor = pickMemoryAnchor();
  const anchorQuestion = anchor
    ? `do you have ${anchor.name}?`
    : "Panjabi ache?";
  const anchorLabel = anchor
    ? `${anchor.name}`
    : "Focus any product";

  const flow = [
    {
      label: "1. Focus product",
      question: anchorQuestion,
      note: anchorLabel,
    },
    {
      label: "2. Price follow-up",
      question: "etar dam koto?",
      note: "Should use the focused product.",
    },
    {
      label: "3. Size follow-up",
      question: "M size ache?",
      note: "Should keep the same product context.",
    },
    {
      label: "4. Cheaper similar",
      question: "er cheye kom dam er similar ache?",
      note: "Should search alternatives around the anchor.",
    },
    {
      label: "5. Second option",
      question: "second one er details dao",
      note: "Should resolve list position from last answer.",
    },
  ];

  flow.forEach(step => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "memory-example-card";
    card.dataset.question = step.question;

    const label = document.createElement("span");
    label.className = "memory-example-label";
    label.textContent = step.label;
    card.appendChild(label);

    const question = document.createElement("span");
    question.className = "memory-example-question";
    question.textContent = step.question;
    card.appendChild(question);

    const note = document.createElement("span");
    note.className = "memory-example-note";
    note.textContent = step.note;
    card.appendChild(note);

    el.memoryExamples.appendChild(card);
  });
}

function pickCatalogExamples() {
  const targets = [
    { keys: ["panjabi"], label: "Panjabi", question: item => `${item.name} size L ache?` },
    { keys: ["saree"], label: "Saree", question: item => `${item.name} er price koto?` },
    { keys: ["salwar_kameez", "salwar kameez", "three_piece"], label: "Salwar Kameez", question: item => `${item.name} size M ache?` },
    { keys: ["shirt"], label: "Shirt", question: item => `${item.name} size M available?` },
    { keys: ["polo"], label: "Polo", question: item => `${item.name} er kon color ache?` },
    { keys: ["t_shirt", "t-shirt", "tee"], label: "T-shirt", question: item => `${item.name} size M ache?` },
    { keys: ["bag", "hand_bag", "hand bag"], label: "Bag", question: item => `do you have ${item.name}?` },
    { keys: ["sandal", "shoe", "footwear"], label: "Footwear", question: item => `${item.name} size 38 ache?` },
  ];
  const used = new Set();
  const examples = [];

  targets.forEach(target => {
    const item = bestCatalogItemForTarget(target, used);
    if (!item) return;
    used.add(item.product_id || item.sku || item.name);
    examples.push({ item, target });
  });

  if (examples.length < 8) {
    rankedCatalogItems()
      .filter(item => !used.has(item.product_id || item.sku || item.name))
      .slice(0, 8 - examples.length)
      .forEach(item => examples.push({
        item,
        target: {
          label: humanCategory(item),
          question: productQuestion,
        },
      }));
  }

  return examples.slice(0, 8);
}

function bestCatalogItemForTarget(target, used = new Set()) {
  const candidates = rankedCatalogItems()
    .filter(item => !used.has(item.product_id || item.sku || item.name));
  const normalizedKeys = target.keys.map(normalizeCategoryKey);
  return candidates.find(item => normalizedKeys.includes(normalizedCategory(item)))
    || candidates.find(item => {
      const category = normalizedCategory(item);
      return normalizedKeys.some(key => category.includes(key));
    });
}

function rankedCatalogItems() {
  return [...state.catalogItems]
    .filter(item => item && (item.name || item.product_id))
    .sort((a, b) => catalogExampleScore(b) - catalogExampleScore(a));
}

function catalogExampleScore(item) {
  let score = 0;
  if (Number(item.stock || 0) > 0) score += 40;
  if (item.price !== null && item.price !== undefined) score += 20;
  if (firstCatalogImageUrl(item)) score += 20;
  if (normalizedCategory(item) && normalizedCategory(item) !== "unknown") score += 8;
  if (String(item.name || "").length < 70) score += 4;
  if (isSafeDemoProductName(item)) score += 10;
  else score -= 20;
  return score;
}

function pickMemoryAnchor() {
  const preferred = ["panjabi", "shirt", "polo", "t_shirt", "salwar_kameez", "saree"];
  const safeRanked = rankedCatalogItems().filter(isSafeDemoProductName);
  return safeRanked.find(item => preferred.includes(normalizedCategory(item)))
    || safeRanked[0]
    || rankedCatalogItems().find(item => preferred.includes(normalizedCategory(item)))
    || rankedCatalogItems()[0]
    || null;
}

function productQuestion(item) {
  return `do you have ${item.name || item.product_id}?`;
}

function compactCatalogFacts(item) {
  const color = item.attributes?.color || item.color;
  const stock = Number(item.stock || 0);
  return [
    humanCategory(item),
    color,
    formatCatalogPrice(item),
    stock > 0 ? `${stock} stock` : "out of stock",
  ].filter(Boolean).join(" · ");
}

function humanCategory(item) {
  return item.category || item.attributes?.category_key || "Product";
}

function normalizedCategory(item) {
  return normalizeCategoryKey(item.attributes?.category_key || item.category || "");
}

function normalizeCategoryKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function isSafeDemoProductName(item) {
  const name = String(item?.name || "");
  if (!name) return false;
  if (name.length > 72) return false;
  return !/(&|\bvs\b|\band\b|\bversus\b|\/)/i.test(name);
}

function renderCatalogItem(item) {
  const node = document.createElement("article");
  node.className = "catalog-item";

  const catalogImageUrl = firstCatalogImageUrl(item);
  if (catalogImageUrl) {
    const img = document.createElement("img");
    img.className = "catalog-thumb";
    img.src = resolveCatalogAssetUrl(catalogImageUrl);
    img.alt = item.name || item.product_id || "Catalog product";
    img.loading = "lazy";
    node.appendChild(img);
  }

  const top = document.createElement("div");
  top.className = "catalog-item-top";
  const name = document.createElement("h3");
  name.className = "catalog-item-name";
  name.textContent = item.name || item.product_id;
  const price = document.createElement("div");
  price.className = "catalog-item-price";
  price.textContent = formatCatalogPrice(item);
  top.appendChild(name);
  top.appendChild(price);
  node.appendChild(top);

  const meta = document.createElement("div");
  meta.className = "catalog-meta-line";
  meta.textContent = [
    item.category || item.attributes?.category_key,
    item.status || stockLabel(item.stock),
    `${Number(item.stock || 0)} stock`,
  ].filter(Boolean).join(" · ");
  node.appendChild(meta);

  const attrs = [
    item.attributes?.section,
    item.attributes?.gender,
    item.attributes?.color,
    item.attributes?.size,
    item.attributes?.fabric,
    item.attributes?.occasion,
  ].filter(Boolean).slice(0, 5);
  if (attrs.length) {
    const tags = document.createElement("div");
    tags.className = "catalog-tags";
    attrs.forEach(value => {
      const tag = document.createElement("span");
      tag.className = "catalog-tag";
      tag.textContent = value;
      tags.appendChild(tag);
    });
    node.appendChild(tags);
  }

  const desc = item.short_description || item.full_description;
  if (desc) {
    const line = document.createElement("div");
    line.className = "catalog-meta-line";
    line.textContent = desc.length > 120 ? `${desc.slice(0, 117)}...` : desc;
    node.appendChild(line);
  }

  const actions = document.createElement("div");
  actions.className = "catalog-item-actions";
  const ask = document.createElement("button");
  ask.className = "catalog-ask-btn";
  ask.type = "button";
  ask.textContent = "Ask";
  ask.dataset.question = `do you have ${item.name}?`;
  actions.appendChild(ask);
  node.appendChild(actions);

  return node;
}

function catalogSearchText(item) {
  const pieces = [
    item.product_id,
    item.sku,
    item.name,
    item.category,
    item.brand,
    item.short_description,
    item.full_description,
    ...(item.tags || []),
    ...Object.values(item.attributes || {}),
  ];
  return normalizeCatalogText(pieces.filter(Boolean).join(" "));
}

function firstCatalogImageUrl(item) {
  const images = Array.isArray(item?.images) ? item.images : [];
  const primary = images.find(image => image?.role === "primary") || images[0];
  if (!primary) return null;
  if (primary.url) return primary.url;
  if (primary.local_path && item?.product_id && primary.image_id) {
    return `/inventory/assets/${encodeURIComponent(item.product_id)}/${encodeURIComponent(primary.image_id)}`;
  }
  return primary.local_path || null;
}

function resolveCatalogAssetUrl(value) {
  if (!value || typeof value !== "string") return "";
  if (/^(https?:|data:|blob:|\/)/i.test(value)) return value;
  if (value.startsWith("frontend/")) return `/${value}`;
  return value;
}

function normalizeCatalogText(text) {
  return String(text || "").toLowerCase().trim();
}

function formatCatalogPrice(item) {
  if (item.price === null || item.price === undefined) return item.currency || "";
  return `${item.currency || "BDT"} ${Number(item.price).toLocaleString()}`;
}

function stockLabel(stock) {
  const n = Number(stock || 0);
  if (n <= 0) return "Out of stock";
  if (n <= 3) return "Low stock";
  return "Active";
}

// ── Voice Input ────────────────────────────────────────────────────────────────

function initVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    el.micBtn.title = "Voice input not supported in this browser";
    el.micBtn.style.opacity = "0.4";
    el.micBtn.style.pointerEvents = "none";
    return;
  }
  const r = new SpeechRecognition();
  r.continuous = false;
  r.interimResults = true;
  r.maxAlternatives = 1;
  r.lang = detectBrowserLang();

  r.onresult = e => {
    const transcript = Array.from(e.results).map(r => r[0].transcript).join("");
    el.input.value = transcript;
    resizeInput();
    if (e.results[e.results.length - 1].isFinal) stopMic();
  };
  r.onerror = () => stopMic();
  r.onend = () => stopMic();
  state.recognition = r;
}

function detectBrowserLang() {
  const nav = navigator.language || "en-US";
  if (nav.startsWith("bn")) return "bn-BD";
  return nav;
}

function toggleMic() {
  if (!state.recognition) return;
  if (state.micRecording) {
    stopMic();
  } else {
    state.micRecording = true;
    el.micBtn.classList.add("recording");
    el.micBtn.title = "Listening… tap to stop";
    // cycle language: if current is bn-BD switch to en-US and vice versa
    state.recognition.lang = state.recognition.lang === "bn-BD" ? "en-US" : "bn-BD";
    state.recognition.start();
  }
}

function stopMic() {
  state.micRecording = false;
  el.micBtn.classList.remove("recording");
  el.micBtn.title = "Voice input (Bangla/English)";
  try { state.recognition.stop(); } catch (_) {}
}

// ── Cart ───────────────────────────────────────────────────────────────────────

function toggleCart() {
  el.cartPanel.classList.toggle("open");
  el.cartChevron.textContent = el.cartPanel.classList.contains("open") ? "▲" : "▼";
}

function addToCart(productId, name, unitPrice, quantity = 1) {
  const existing = state.cart.find(i => i.product_id === productId);
  if (existing) { existing.quantity += quantity; }
  else { state.cart.push({ product_id: productId, name, unit_price: unitPrice, quantity }); }
  renderCart();
  // also POST to server
  apiPost("/orders/cart/quantity", { session_id: state.sessionId, product_id: productId, quantity: existing ? existing.quantity : quantity }).catch(() => {});
}

function renderCart() {
  const count = state.cart.reduce((s, i) => s + i.quantity, 0);
  el.cartCount.textContent = `(${count} item${count !== 1 ? "s" : ""})`;
  el.cartItems.innerHTML = "";
  let subtotal = 0;
  state.cart.forEach(item => {
    subtotal += item.unit_price * item.quantity;
    const row = document.createElement("div");
    row.className = "cart-item-row";
    row.innerHTML = `
      <span class="cart-item-name" title="${item.name}">${item.name.slice(0, 35)}</span>
      <div class="cart-item-controls">
        <button class="cart-qty-btn" data-pid="${item.product_id}" data-delta="-1">−</button>
        <span style="min-width:22px;text-align:center;">${item.quantity}</span>
        <button class="cart-qty-btn" data-pid="${item.product_id}" data-delta="1">+</button>
        <span style="min-width:70px;text-align:right;">BDT ${(item.unit_price * item.quantity).toLocaleString()}</span>
        <button class="cart-remove-btn" data-pid="${item.product_id}" title="Remove">✕</button>
      </div>`;
    el.cartItems.appendChild(row);
  });
  el.cartTotalRow.style.display = state.cart.length ? "flex" : "none";
  el.cartSubtotal.textContent = `BDT ${subtotal.toLocaleString()}`;

  // wire buttons
  el.cartItems.querySelectorAll(".cart-qty-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const pid = btn.dataset.pid;
      const delta = parseInt(btn.dataset.delta);
      const item = state.cart.find(i => i.product_id === pid);
      if (!item) return;
      item.quantity = Math.max(1, item.quantity + delta);
      apiPost("/orders/cart/quantity", { session_id: state.sessionId, product_id: pid, quantity: item.quantity }).catch(() => {});
      renderCart();
    });
  });
  el.cartItems.querySelectorAll(".cart-remove-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const pid = btn.dataset.pid;
      state.cart = state.cart.filter(i => i.product_id !== pid);
      apiPost("/orders/cart/remove", { session_id: state.sessionId, product_id: pid }).catch(() => {});
      renderCart();
    });
  });

  if (count > 0 && !el.cartPanel.classList.contains("open")) {
    el.cartPanel.classList.add("open");
    el.cartChevron.textContent = "▲";
  }
}

// ── Order Tracking ─────────────────────────────────────────────────────────────

async function trackOrder() {
  const val = el.trackInput.value.trim();
  if (!val) return;
  try {
    let url;
    if (val.startsWith("ORD-") || val.match(/^ORD/i)) {
      url = `${state.apiBaseUrl}/orders/${encodeURIComponent(val)}`;
    } else {
      url = `${state.apiBaseUrl}/orders/track/${encodeURIComponent(val)}`;
    }
    const resp = await fetch(url, { headers: buildHeaders() });
    const data = await resp.json();
    if (Array.isArray(data)) {
      if (data.length === 0) {
        addMessage("assistant", `No orders found for ${val}.`);
      } else {
        const lines = data.map(o =>
          `Order **${o.order_id}** — Status: ${o.tracking_status} | Total: BDT ${o.grand_total?.toLocaleString() || "?"} | ${o.created_at?.slice(0, 10) || ""}`
        );
        addMessage("assistant", lines.join("\n"));
      }
    } else {
      addMessage("assistant",
        `Order **${data.order_id}** — Status: ${data.order_status || data.status} | Tracking: ${data.tracking_status || "pending"}\nTotal: BDT ${data.grand_total?.toLocaleString() || "?"}`
      );
    }
  } catch (e) {
    addMessage("assistant", `Tracking failed: ${e.message}`);
  }
  el.trackBar.classList.remove("active");
  el.trackInput.value = "";
}

// ── Feedback ───────────────────────────────────────────────────────────────────

function feedbackProductIdsFromResponse(response = {}) {
  const ids = [
    ...(response?.recommended_product_ids || []),
    ...(response?.cross_sell_product_ids || []),
    ...((response?.hits || []).map(hit => hit?.product_id).filter(Boolean)),
  ];
  return Array.from(new Set(ids.map(id => String(id).trim()).filter(Boolean))).slice(0, 8);
}

function compactFeedbackAnswerPlan(plan) {
  if (!plan) return null;
  return {
    intent: plan.intent || null,
    detected_intent: plan.detected_intent || null,
    intent_confidence: plan.intent_confidence ?? null,
    primary_product_id: plan.primary_product_id || null,
    alternative_product_ids: plan.alternative_product_ids || [],
    cross_sell_product_ids: plan.cross_sell_product_ids || [],
    excluded_product_ids: plan.excluded_product_ids || [],
    abstain: Boolean(plan.abstain),
    abstention_reason: plan.abstention_reason || null,
    next_best_question: plan.next_best_question || null,
  };
}

function feedbackContextFromResponse(response = {}) {
  return {
    traceId: response.trace_id || null,
    confidenceScore: typeof response.confidence_score === "number" ? response.confidence_score : null,
    abstained: typeof response.abstained === "boolean" ? response.abstained : null,
    abstentionReason: response.abstention_reason || null,
    answerPlan: compactFeedbackAnswerPlan(response.answer_plan),
    productIds: feedbackProductIdsFromResponse(response),
  };
}

function addFeedbackRow(msgNode, question, answer, intent, feedbackContext = {}) {
  const row = document.createElement("div");
  row.className = "feedback-row";
  const label = document.createElement("span");
  label.className = "feedback-label";
  label.textContent = "Helpful?";
  const up = document.createElement("button");
  up.className = "feedback-btn";
  up.textContent = "👍";
  up.title = "This helped";
  const down = document.createElement("button");
  down.className = "feedback-btn";
  down.textContent = "👎";
  down.title = "This didn't help";
  const commentBox = document.createElement("div");
  commentBox.className = "feedback-comment";
  commentBox.hidden = true;
  const textarea = document.createElement("textarea");
  textarea.rows = 2;
  textarea.maxLength = 500;
  textarea.placeholder = "What was wrong? Example: wrong product, missed size/color, not human enough";
  const actions = document.createElement("div");
  actions.className = "feedback-comment-actions";
  const sendComment = document.createElement("button");
  sendComment.type = "button";
  sendComment.className = "feedback-submit";
  sendComment.textContent = "Send";
  const skipComment = document.createElement("button");
  skipComment.type = "button";
  skipComment.className = "feedback-skip";
  skipComment.textContent = "Skip";
  actions.appendChild(sendComment);
  actions.appendChild(skipComment);
  commentBox.appendChild(textarea);
  commentBox.appendChild(actions);

  let submitted = false;
  const vote = async (rating, comment = null) => {
    if (submitted) return;
    submitted = true;
    up.classList.add("voted");
    down.classList.add("voted");
    up.disabled = true;
    down.disabled = true;
    sendComment.disabled = true;
    skipComment.disabled = true;
    textarea.disabled = true;
    label.textContent = rating === "up" ? "Saving..." : "Saving for review...";
    const productIds = feedbackContext.productIds?.length ? feedbackContext.productIds : state.focusedProductIds;
    try {
      const result = await apiPost("/feedback", {
        session_id: state.sessionId,
        question,
        answer: answer.slice(0, 500),
        rating,
        comment: comment || null,
        intent: intent || feedbackContext.answerPlan?.intent || null,
        product_ids: productIds.slice(0, 8),
        trace_id: feedbackContext.traceId || null,
        confidence_score: feedbackContext.confidenceScore,
        abstained: feedbackContext.abstained,
        abstention_reason: feedbackContext.abstentionReason || null,
        answer_plan: feedbackContext.answerPlan || null,
        source: "chat_ui",
      });
      label.textContent = rating === "up"
        ? "Thanks!"
        : (result.pending_case_created ? "Saved for review" : "Feedback saved");
      commentBox.hidden = true;
    } catch (error) {
      submitted = false;
      up.classList.remove("voted");
      down.classList.remove("voted");
      up.disabled = false;
      down.disabled = false;
      sendComment.disabled = false;
      skipComment.disabled = false;
      textarea.disabled = false;
      label.textContent = "Feedback failed";
    }
  };
  up.addEventListener("click", () => vote("up"));
  down.addEventListener("click", () => {
    if (submitted) return;
    commentBox.hidden = false;
    textarea.focus();
  });
  sendComment.addEventListener("click", () => vote("down", textarea.value.trim()));
  skipComment.addEventListener("click", () => vote("down"));
  row.appendChild(label);
  row.appendChild(up);
  row.appendChild(down);
  msgNode.appendChild(row);
  msgNode.appendChild(commentBox);
}

// ── Image Upload ───────────────────────────────────────────────────────────────

function handleImageSelect(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  setPendingImageFromFile(file);
}

function bindImageDropAndPaste() {
  const dropTargets = [el.imageUploadArea, el.chatPanel].filter(Boolean);
  let dragDepth = 0;

  dropTargets.forEach(target => {
    target.addEventListener("dragenter", event => {
      if (!eventHasImageFile(event)) return;
      event.preventDefault();
      event.stopPropagation();
      dragDepth += 1;
      setImageDropActive(true);
    });
    target.addEventListener("dragover", event => {
      if (!eventHasImageFile(event)) return;
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = "copy";
      setImageDropActive(true);
    });
    target.addEventListener("dragleave", event => {
      if (!eventHasImageFile(event)) return;
      event.stopPropagation();
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) setImageDropActive(false);
    });
    target.addEventListener("drop", event => {
      if (!eventHasImageFile(event)) return;
      event.preventDefault();
      event.stopPropagation();
      dragDepth = 0;
      setImageDropActive(false);
      const file = firstImageFile(event.dataTransfer?.files);
      if (file) {
        setPendingImageFromFile(file);
      } else {
        showImageHint("Drop an image file to search.");
      }
    });
  });

  document.addEventListener("paste", event => {
    const file = firstClipboardImage(event.clipboardData);
    if (!file) return;
    event.preventDefault();
    setPendingImageFromFile(file, file.name || "pasted-screenshot.png");
  });
}

function eventHasImageFile(event) {
  const types = Array.from(event.dataTransfer?.types || []);
  if (types.includes("Files")) return true;
  return firstImageFile(event.dataTransfer?.files) !== null;
}

function firstImageFile(fileList) {
  return Array.from(fileList || []).find(file => isImageFile(file)) || null;
}

function firstClipboardImage(clipboardData) {
  const items = Array.from(clipboardData?.items || []);
  for (const item of items) {
    if (String(item.type || "").startsWith("image/")) {
      const file = item.getAsFile();
      if (file) return file;
    }
  }
  return firstImageFile(clipboardData?.files);
}

function isImageFile(file) {
  return Boolean(file && String(file.type || "").startsWith("image/"));
}

function setPendingImageFromFile(file, fallbackName = "image-search-upload.png") {
  if (!isImageFile(file)) {
    showImageHint("Please use a JPG, PNG, WEBP, or screenshot image.");
    return;
  }
  const reader = new FileReader();
  reader.onload = async e => {
    try {
      const dataUrl = await normalizeImageDataUrl(String(e.target.result || ""));
      setPendingImageFromDataUrl(dataUrl, file.name || fallbackName);
    } catch (_) {
      setPendingImageFromDataUrl(String(e.target.result || ""), file.name || fallbackName);
    }
  };
  reader.onerror = () => showImageHint("Could not read this image. Try another file.");
  reader.readAsDataURL(file);
}

async function useImageExample(card) {
  if (state.busy) return;
  const imagePath = card.dataset.image;
  const question = card.dataset.question || "";
  const name = card.dataset.name || "demo-product.jpg";
  if (!imagePath) return;
  try {
    const response = await fetch(imagePath, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const dataUrl = await blobToDataUrl(blob);
    setPendingImageFromDataUrl(dataUrl, name);
    el.input.value = question;
    resizeInput();
    el.input.focus();
  } catch (error) {
    addMessage("assistant", `Could not load demo image: ${error.message}`);
  }
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("FileReader failed"));
    reader.readAsDataURL(blob);
  });
}

function normalizeImageDataUrl(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const width = img.naturalWidth || img.width;
      const height = img.naturalHeight || img.height;
      if (!width || !height) {
        resolve(dataUrl);
        return;
      }
      const maxEdge = Math.max(width, height);
      if (maxEdge <= IMAGE_UPLOAD_MAX_EDGE) {
        resolve(dataUrl);
        return;
      }
      const scale = IMAGE_UPLOAD_MAX_EDGE / maxEdge;
      const nextWidth = Math.max(1, Math.round(width * scale));
      const nextHeight = Math.max(1, Math.round(height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = nextWidth;
      canvas.height = nextHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        resolve(dataUrl);
        return;
      }
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, nextWidth, nextHeight);
      ctx.drawImage(img, 0, 0, nextWidth, nextHeight);
      resolve(canvas.toDataURL("image/jpeg", IMAGE_UPLOAD_JPEG_QUALITY));
    };
    img.onerror = () => reject(new Error("Image resize failed"));
    img.src = dataUrl;
  });
}

function setPendingImageFromDataUrl(dataUrl, name) {
  const imageB64 = dataUrl.split(",", 2)[1];
  if (!imageB64) {
    showImageHint("Could not prepare this image. Try a JPG or PNG.");
    return;
  }
  state.pendingImageB64 = imageB64;
  state.pendingImageName = name || "image-search-upload.png";
  el.imagePreview.src = dataUrl;
  el.imagePreview.style.display = "block";
  el.clearImageBtn.style.display = "inline";
  el.imageUploadArea?.classList.add("image-ready");
  showImageHint(`Ready: ${shortImageName(state.pendingImageName)}`);
  el.input.focus();
}

function setImageDropActive(active) {
  el.imageUploadArea?.classList.toggle("drag-active", Boolean(active));
}

function showImageHint(text) {
  el.imageLabel.textContent = text;
}

function shortImageName(name) {
  const clean = String(name || "image").trim();
  return clean.length > 28 ? `${clean.slice(0, 25)}...` : clean;
}

function clearImage() {
  state.pendingImageB64 = null;
  state.pendingImageName = null;
  el.imageInput.value = "";
  el.imagePreview.style.display = "none";
  el.imagePreview.src = "";
  el.clearImageBtn.style.display = "none";
  el.imageUploadArea?.classList.remove("drag-active", "image-ready");
  el.imageLabel.textContent = "Drag, paste, or choose a product photo.";
}

// ── Send ───────────────────────────────────────────────────────────────────────

async function handleSubmit() {
  const text = el.input.value.trim();
  if (state.pendingImageB64) { await sendImageSearch(text); }
  else { await sendMessage(text); }
}

async function sendImageSearch(queryText) {
  if (state.busy) return;
  state.busy = true;
  el.send.disabled = true;
  const displayText = queryText || "Image search";
  addMessage("user", displayText + (state.pendingImageName ? ` [${state.pendingImageName}]` : ""));
  const thinking = addMessage("assistant", "Searching by image…");
  try {
    const response = await apiPost("/inventory/image-search", {
      query_text: queryText || "",
      image_b64: state.pendingImageB64,
      session_id: state.sessionId,
      top_k: 5,
    });
    thinking.querySelector(".body").textContent = response.answer || "No similar items found.";
    renderImageResults(thinking, response);
    renderImageMeta(thinking, response);
    addFeedbackRow(thinking, displayText, response.answer || "", "image_search", feedbackContextFromResponse(response));
    state.conversation.push({ role: "user", content: displayText });
    state.conversation.push({ role: "assistant", content: response.answer || "" });
    state.focusedProductIds = Array.from(new Set([
      response.primary_product_id,
      ...(response.same_design_variant_ids || []),
      ...(response.similar_product_ids || []),
      ...((response.hits || []).map(hit => hit.product_id)),
    ].filter(Boolean))).slice(0, 8);
  } catch (error) {
    thinking.querySelector(".body").textContent = `Image search failed: ${error.message}`;
  } finally {
    clearImage();
    state.busy = false;
    el.send.disabled = false;
    el.input.value = "";
    resizeInput();
    el.input.focus();
  }
}

async function sendMessage(rawText) {
  const text = rawText.trim();
  if (!text || state.busy) return;
  state.busy = true;
  el.send.disabled = true;
  el.input.value = "";
  resizeInput();
  addMessage("user", text);
  const thinking = addMessage("assistant", "…");

  try {
    const payload = {
      question: text,
      session_id: state.sessionId,
      top_k: 5,
      assistant_mode: state.assistantMode,
      reply_style: state.replyStyle,
      answer_engine: state.answerEngine,
      conversation_history: state.conversation.slice(-8),
      focused_product_ids: state.focusedProductIds,
      last_answer_plan: state.lastAnswerPlan,
    };
    const response = await apiPost("/inventory/ask", payload);
    const answer = response.answer || "No answer returned.";
    thinking.querySelector(".body").textContent = answer;
    renderProductResults(thinking, response);
    renderMeta(thinking, response);

    const intent = response?.answer_plan?.intent;
    addFeedbackRow(thinking, text, answer, intent, feedbackContextFromResponse(response));

    state.conversation.push({ role: "user", content: text });
    state.conversation.push({ role: "assistant", content: answer });
    state.lastAnswerPlan = response.answer_plan || null;
    const nextFocus = [
      ...(response.recommended_product_ids || []),
      ...(response.cross_sell_product_ids || []),
    ];
    state.focusedProductIds = Array.from(new Set(nextFocus)).slice(0, 8);

    detectOrderState(text, answer);
    detectProactiveCart(response);
  } catch (error) {
    thinking.querySelector(".body").textContent = `Request failed: ${error.message}`;
  } finally {
    state.busy = false;
    el.send.disabled = false;
    el.input.focus();
  }
}

// ── Order State Machine ────────────────────────────────────────────────────────

function detectOrderState(userText, botAnswer) {
  const orderKw    = ["order korte", "order dite", "book kore", "eta nibo", "cart e add", "checkout", "order confirm", "place order", "kinbo", "i want to order"];
  const confirmKw  = ["should i confirm", "confirm this order", "confirm?", "shall i confirm"];
  const cancelKw   = ["order cancelled", "no active order"];
  const confirmedKw = ["order confirmed", "your order id is"];

  const u = userText.toLowerCase();
  const b = botAnswer.toLowerCase();

  if (orderKw.some(k => u.includes(k))) {
    state.orderActive = true;
    el.orderStatusBar.classList.add("active");
  }
  if (confirmKw.some(k => b.includes(k))) {
    state.awaitingOrderConfirm = true;
    el.orderConfirmBar.classList.add("active");
  }
  if (cancelKw.some(k => b.includes(k)) || confirmedKw.some(k => b.includes(k))) {
    state.orderActive = false;
    state.awaitingOrderConfirm = false;
    el.orderStatusBar.classList.remove("active");
    el.orderConfirmBar.classList.remove("active");
    if (confirmedKw.some(k => b.includes(k))) state.cart = [];
    renderCart();
  }
}

function detectProactiveCart(response) {
  // If bot returned product IDs and user was ordering, add to local cart state
  const pids = response.recommended_product_ids || [];
  if (state.orderActive && pids.length && response.answer_plan) {
    const plan = response.answer_plan;
    // Only auto-add if the plan has a product name + price (draft was started)
  }
}

async function cancelOrder() {
  state.orderActive = false;
  state.awaitingOrderConfirm = false;
  el.orderStatusBar.classList.remove("active");
  el.orderConfirmBar.classList.remove("active");
  addMessage("user", "Cancel my order");
  const thinking = addMessage("assistant", "…");
  try {
    await fetch(`${state.apiBaseUrl}/orders/cancel/${state.sessionId}`, {
      method: "DELETE",
      headers: buildHeaders(),
    });
    thinking.querySelector(".body").textContent = "Order cancelled. Let me know if you want to browse more products.";
    state.cart = [];
    renderCart();
  } catch (_) {
    thinking.querySelector(".body").textContent = "Order cancelled.";
  }
}

// ── Proactive low-stock notice ─────────────────────────────────────────────────

function maybeLowStockNotice(msgNode, response) {
  // In future: check if any recommended product has stock <= 2, add inline notice
  // Requires product detail in response — placeholder hook
}

// ── API helpers ────────────────────────────────────────────────────────────────

async function apiPost(path, payload) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const message = data?.detail?.message || data?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

async function apiGet(path) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    headers: buildHeaders(),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const message = data?.detail?.message || data?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

function buildHeaders() {
  const h = { "Content-Type": "application/json" };
  if (state.apiKey) h["X-API-Key"] = state.apiKey;
  return h;
}

function addMessage(role, text) {
  const node = document.createElement("article");
  node.className = `message ${role}`;
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = text;
  node.appendChild(body);
  el.messages.appendChild(node);
  el.messages.scrollTop = el.messages.scrollHeight;
  return node;
}

function renderMeta(node, response) {
  const meta = document.createElement("div");
  meta.className = "meta";
  const intent = response?.answer_plan?.intent || "inventory";
  const language = response?.answer_plan?.preferences?.language;
  const ids = [
    ...(response?.recommended_product_ids || []),
    ...(response?.cross_sell_product_ids || []),
  ];
  const parts = [`intent: ${intent}`];
  if (language) parts.push(`lang: ${language}`);
  if (ids.length) parts.push(`items: ${ids.slice(0, 3).join(", ")}`);
  meta.textContent = parts.join(" · ");
  node.appendChild(meta);
}

function renderImageMeta(node, response) {
  const meta = document.createElement("div");
  meta.className = "meta";
  const parts = [`image-search`, `${response?.total || 0} result(s)`];
  if (response?.decision_label) parts.push(labelText(response.decision_label));
  if (response?.requested_color) parts.push(`requested: ${response.requested_color}`);
  if (response?.query_image_id) parts.push(`image: ${response.query_image_id}`);
  meta.textContent = parts.join(" · ");
  node.appendChild(meta);
}

function renderImageResults(node, response) {
  const hits = Array.isArray(response?.hits) ? response.hits.slice(0, 6) : [];
  if (!hits.length) return;
  const grid = document.createElement("div");
  grid.className = "image-results";
  hits.forEach(hit => {
    grid.appendChild(renderResultCard(hit, {
      badge: hit.decision_label || hit.match_type || "similar_style",
      scoreLabel: typeof hit.score === "number" ? `${Math.round(hit.score * 100)}% visual` : "visual match",
      fallbackAlt: "Matched product",
    }));
  });
  node.appendChild(grid);
  renderImageQuickActions(node, response);
}

function renderProductResults(node, response) {
  const hits = productCardsFromResponse(response).slice(0, 6);
  if (!hits.length) return;
  const grid = document.createElement("div");
  grid.className = "image-results product-results";
  hits.forEach((hit, index) => {
    grid.appendChild(renderResultCard(hit, {
      badge: index === 0 ? "catalog_primary" : "catalog_match",
      scoreLabel: typeof hit.score === "number" ? `${Math.round(hit.score * 100)}% match` : "catalog match",
      fallbackAlt: "Product",
    }));
  });
  node.appendChild(grid);
  renderProductQuickActions(node, hits);
}

function productCardsFromResponse(response) {
  const byId = new Map();
  const catalogById = new Map((state.catalogItems || []).map(item => [String(item.product_id), item]));

  function addProduct(productId, source = {}) {
    const id = String(productId || source?.product_id || "").trim();
    if (!id || byId.has(id)) return;
    const catalogItem = catalogById.get(id);
    const merged = {
      ...(catalogItem || {}),
      ...(source || {}),
      product_id: id,
    };
    const imageUrl = source?.image_url || firstCatalogImageUrl(catalogItem) || firstCatalogImageUrl(source);
    if (imageUrl) merged.image_url = imageUrl;
    if (catalogItem?.attributes && !merged.attributes) merged.attributes = catalogItem.attributes;
    byId.set(id, merged);
  }

  (response?.recommended_product_ids || []).forEach(id => addProduct(id));
  (response?.cross_sell_product_ids || []).forEach(id => addProduct(id));
  (response?.hits || []).forEach(hit => addProduct(hit?.product_id, hit));

  return Array.from(byId.values()).filter(hit => hit.image_url || hit.name || hit.product_id);
}

function renderResultCard(hit, options = {}) {
  const card = document.createElement("div");
  card.className = "image-result-card";

  const imageUrl = hit.image_url || firstCatalogImageUrl(hit);
  if (imageUrl) {
    const img = document.createElement("img");
    img.src = resolveCatalogAssetUrl(imageUrl);
    img.alt = hit.name || options.fallbackAlt || "Product";
    img.loading = "lazy";
    card.appendChild(img);
  }

  const body = document.createElement("div");
  body.className = "image-result-body";
  const badge = document.createElement("div");
  badge.className = `image-result-badge ${badgeClass(options.badge)}`;
  badge.textContent = labelText(options.badge || "catalog_match");
  const name = document.createElement("p");
  name.className = "image-result-name";
  name.textContent = hit.name || hit.product_id || "Product";
  const facts = document.createElement("div");
  facts.className = "image-result-facts";
  facts.textContent = resultFacts(hit, options.scoreLabel);
  body.appendChild(badge);
  body.appendChild(name);
  body.appendChild(facts);
  card.appendChild(body);
  return card;
}

function resultFacts(hit, scoreLabel) {
  const price = typeof hit.price === "number"
    ? `${hit.currency || "BDT"} ${hit.price.toLocaleString()}`
    : "Price N/A";
  const stock = Number.isFinite(hit.stock) ? `${hit.stock} in stock` : "Stock N/A";
  const attrs = hit.attributes || {};
  const color = hit.color || attrs.color || attrs.color_family || "";
  const size = hit.size || attrs.size || attrs.sizes || "";
  const colorText = color ? ` · ${String(color).replaceAll("|", ", ")}` : "";
  const sizeText = size ? ` · ${String(size).replaceAll("|", ", ")}` : "";
  return `${price} · ${stock}${colorText}${sizeText} · ${scoreLabel || "catalog match"}`;
}

function renderProductQuickActions(node, hits) {
  if (!hits.length) return;
  const actions = ["Price koto?", "Available size?", "Show similar", "Order this"];
  const row = document.createElement("div");
  row.className = "image-result-actions product-result-actions";
  actions.forEach(text => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = text;
    btn.addEventListener("click", () => {
      el.input.value = text;
      resizeInput();
      el.input.focus();
    });
    row.appendChild(btn);
  });
  node.appendChild(row);
}

function renderImageQuickActions(node, response) {
  const primary = response?.primary_product_id;
  const colors = Array.isArray(response?.available_colors) ? response.available_colors.slice(0, 5) : [];
  const decision = response?.decision_label;
  // Backend-suggested next question goes first — it already knows the decision.
  const suggested = (response?.follow_up_question || "").trim();
  const requestedSize = (response?.requested_size || "").trim();
  const actions = [];
  if (suggested) actions.push(suggested);
  if (colors.length && decision !== "no_confident_match") {
    actions.push("Other colors?");
  }
  if (primary) {
    // Skip the size chip if the customer just got a size-specific answer.
    if (!requestedSize) actions.push("M size ache?");
    actions.push("Price koto?");
    actions.push("Show similar");
    if (decision === "confirmed_exact" || decision === "confirmed_same_design_variant") {
      actions.push("Order this");
    }
  }
  if (!actions.length) return;
  // De-duplicate (the suggested question can collide with the defaults).
  const seen = new Set();
  const row = document.createElement("div");
  row.className = "image-result-actions";
  actions.forEach(text => {
    const key = text.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = text;
    btn.addEventListener("click", () => {
      el.input.value = text;
      resizeInput();
      el.input.focus();
    });
    row.appendChild(btn);
  });
  node.appendChild(row);
}

function labelText(value) {
  const labels = {
    confirmed_exact: "Exact",
    confirmed_same_design_variant: "Same design",
    likely_same_design: "Likely same design",
    similar_style: "Similar",
    no_confident_match: "Not confident",
    visual_similar: "Similar",
    same_design_variant: "Same design",
    catalog_primary: "Top match",
    catalog_match: "Catalog match",
  };
  return labels[value] || String(value || "Similar").replaceAll("_", " ");
}

function badgeClass(value) {
  if (value === "confirmed_exact") return "exact";
  if (value === "confirmed_same_design_variant" || value === "likely_same_design") return "design";
  if (value === "no_confident_match") return "weak";
  if (value === "catalog_primary") return "exact";
  if (value === "catalog_match") return "similar";
  return "similar";
}

async function checkHealth() {
  try {
    const resp = await fetch(`${state.apiBaseUrl}/health`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    setStatus("ready", "Connected");
  } catch (error) {
    setStatus("error", "Offline");
    addMessage("assistant", `Backend connection failed: ${error.message}`);
  }
}

function setStatus(kind, text) {
  el.statusPill.classList.remove("ready", "error");
  if (kind) el.statusPill.classList.add(kind);
  el.statusText.textContent = text;
}

function resizeInput() {
  el.input.style.height = "auto";
  el.input.style.height = `${Math.min(el.input.scrollHeight, 160)}px`;
}
