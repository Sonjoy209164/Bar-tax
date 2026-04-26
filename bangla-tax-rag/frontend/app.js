const DEFAULT_DATA_DOMAINS = [
  "catalog",
  "sales",
  "orders",
  "inventory_snapshots",
  "suppliers",
  "margins",
  "returns",
  "customers"
];

const DEFAULT_LOCAL_BACKEND_URL = "http://localhost:4893";

const state = {
  apiBaseUrl: sessionStorage.getItem("inventoryDemo.apiBaseUrl") || defaultApiBaseUrl(),
  apiKey: sessionStorage.getItem("inventoryDemo.apiKey") || "",
  dataDomains:
    sessionStorage.getItem("inventoryDemo.dataDomains") || DEFAULT_DATA_DOMAINS.join(", "),
  frontendRuntimeConfig: null,
  servedByBackend: false,
  sampleData: null,
  liveCatalog: [],
  runtimeConfig: null,
  lastTraceId: null,
  lastTraceHint: null,
  lastRouteDecision: null,
  recentHits: [],
  conversationHistory: [],
  focusedProductIds: [],
  activeFilters: null,
  lastAnswerPlan: null,
  debugSessions: [],
  sampleSyncState: {
    checking: false,
    syncing: false,
    done: false,
    itemsSynced: false,
    signalsSynced: null,
    needsReset: false,
    existingItemCount: 0,
    existingSignalCount: 0,
    extraItemCount: 0,
    extraSignalCount: 0,
    message: "Sample JSON has not been synced to this backend yet."
  },
  busy: false
};

const elements = {
  apiBaseUrl: document.querySelector("#apiBaseUrl"),
  apiKey: document.querySelector("#apiKey"),
  availableDomains: document.querySelector("#availableDomains"),
  connectionDot: document.querySelector("#connectionDot"),
  connectionLabel: document.querySelector("#connectionLabel"),
  connectionDetail: document.querySelector("#connectionDetail"),
  saveSettingsButton: document.querySelector("#saveSettingsButton"),
  checkStatusButton: document.querySelector("#checkStatusButton"),
  loadCatalogButton: document.querySelector("#loadCatalogButton"),
  syncCatalogButton: document.querySelector("#syncCatalogButton"),
  rebuildSyncButton: document.querySelector("#rebuildSyncButton"),
  loadConfigButton: document.querySelector("#loadConfigButton"),
  loadConfigButtonSecondary: document.querySelector("#loadConfigButtonSecondary"),
  productCount: document.querySelector("#productCount"),
  catalogSource: document.querySelector("#catalogSource"),
  focusedProducts: document.querySelector("#focusedProducts"),
  clearFocusButton: document.querySelector("#clearFocusButton"),
  productList: document.querySelector("#productList"),
  productTemplate: document.querySelector("#productTemplate"),
  assistantMode: document.querySelector("#assistantMode"),
  replyStyle: document.querySelector("#replyStyle"),
  endpointMode: document.querySelector("#endpointMode"),
  answerEngine: document.querySelector("#answerEngine"),
  audienceMode: document.querySelector("#audienceMode"),
  streamMode: document.querySelector("#streamMode"),
  preferFastResponse: document.querySelector("#preferFastResponse"),
  allowAgentic: document.querySelector("#allowAgentic"),
  routeSummary: document.querySelector("#routeSummary"),
  lastRoutePath: document.querySelector("#lastRoutePath"),
  messages: document.querySelector("#messages"),
  chatForm: document.querySelector("#chatForm"),
  questionInput: document.querySelector("#questionInput"),
  clearDebugSessionsButton: document.querySelector("#clearDebugSessionsButton"),
  turnDebugSessions: document.querySelector("#turnDebugSessions"),
  lastTraceId: document.querySelector("#lastTraceId"),
  runTestsButton: document.querySelector("#runTestsButton"),
  testResults: document.querySelector("#testResults"),
  loadTraceButton: document.querySelector("#loadTraceButton"),
  traceOutput: document.querySelector("#traceOutput"),
  healthStatusLabel: document.querySelector("#healthStatusLabel"),
  healthStatusDetail: document.querySelector("#healthStatusDetail"),
  inventoryStatusLabel: document.querySelector("#inventoryStatusLabel"),
  inventoryStatusDetail: document.querySelector("#inventoryStatusDetail"),
  syncStatusLabel: document.querySelector("#syncStatusLabel"),
  syncStatusDetail: document.querySelector("#syncStatusDetail"),
  businessStatusLabel: document.querySelector("#businessStatusLabel"),
  businessStatusDetail: document.querySelector("#businessStatusDetail"),
  productionStatusLabel: document.querySelector("#productionStatusLabel"),
  productionStatusDetail: document.querySelector("#productionStatusDetail")
};

void boot();

async function boot() {
  try {
    wireEvents();
    await loadRuntimeFrontendConfig();
    await loadLocalConfig();
    applySettingsToInputs();
    renderSyncCatalogButtonState();
    renderStatusCards();
    await loadSampleData();
    renderSyncCatalogButtonState();
    renderProducts();
    renderFocusedProducts();
    renderDebugSessions();
    resetRouteSummary();
    addMessage(
      "bot",
      "This cockpit now exercises the real backend instead of a narrow demo slice. Check status, sync the sample catalog, then use Auto Route + Streaming to test normal RAG, agentic reasoning, sync rebuild, and trace diagnostics."
    );

    if (state.apiBaseUrl) {
      await checkStatus({ quiet: true, autoLoadCatalog: true });
    }
  } catch (error) {
    setConnection("bad", "Frontend boot failed", error instanceof Error ? error.message : String(error));
    elements.traceOutput.textContent = `Frontend boot failed: ${
      error instanceof Error ? error.message : String(error)
    }`;
  }
}

function wireEvents() {
  elements.saveSettingsButton.addEventListener("click", saveSettings);
  elements.checkStatusButton.addEventListener("click", () => void checkStatus());
  elements.loadCatalogButton.addEventListener("click", () => void loadBackendCatalog());
  elements.syncCatalogButton.addEventListener("click", () => void syncSampleData());
  elements.rebuildSyncButton.addEventListener("click", () => void rebuildSync());
  elements.loadConfigButton.addEventListener("click", () => void loadRuntimeConfig());
  elements.loadConfigButtonSecondary.addEventListener("click", () => void loadRuntimeConfig());
  elements.clearFocusButton.addEventListener("click", clearFocusedProducts);
  elements.chatForm.addEventListener("submit", askFromForm);
  elements.clearDebugSessionsButton.addEventListener("click", clearDebugSessions);
  elements.runTestsButton.addEventListener("click", () => void runQualityTests());
  elements.loadTraceButton.addEventListener("click", () => void loadTrace(state.lastTraceId));
}

async function loadSampleData() {
  const response = await fetch("./data/products.json");
  if (!response.ok) {
    throw new Error("Could not load frontend/data/products.json");
  }
  state.sampleData = await response.json();
}

async function loadRuntimeFrontendConfig() {
  try {
    const response = await fetch("./runtime-config.json", { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const config = await response.json();
    state.frontendRuntimeConfig = config;
    state.servedByBackend = Boolean(config.sameOriginApi);

    const storedApiBaseUrl = sessionStorage.getItem("inventoryDemo.apiBaseUrl");
    if (!storedApiBaseUrl && config.apiBaseUrl) {
      state.apiBaseUrl = normalizeBaseUrl(config.apiBaseUrl);
    }

    setConnection(
      "neutral",
      "Backend-mounted frontend detected",
      "Using same-origin FastAPI wiring so streaming, traces, and route selection hit the live pipeline directly."
    );
  } catch (error) {
    console.warn("Could not load frontend runtime config", error);
  }
}

async function loadLocalConfig() {
  if (state.servedByBackend) {
    return;
  }
  try {
    const response = await fetch("./config.local.json", { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const config = await response.json();
    if (config.apiBaseUrl) {
      state.apiBaseUrl = normalizeBaseUrl(config.apiBaseUrl);
    }
    if (typeof config.apiKey === "string") {
      state.apiKey = config.apiKey.trim();
    }
    if (typeof config.dataDomains === "string" && config.dataDomains.trim()) {
      state.dataDomains = config.dataDomains.trim();
    }
    setConnection(
      "neutral",
      "Local config loaded",
      "Using frontend/config.local.json for direct backend testing from this browser."
    );
  } catch (error) {
    console.warn("Could not load frontend/config.local.json", error);
  }
}

function applySettingsToInputs() {
  elements.apiBaseUrl.value = state.apiBaseUrl;
  elements.apiKey.value = state.apiKey;
  elements.availableDomains.value = state.dataDomains;
}

function saveSettings() {
  const previousBaseUrl = state.apiBaseUrl;
  state.apiBaseUrl = normalizeBaseUrl(elements.apiBaseUrl.value);
  state.apiKey = elements.apiKey.value.trim();
  state.dataDomains = elements.availableDomains.value.trim() || DEFAULT_DATA_DOMAINS.join(", ");
  elements.apiBaseUrl.value = state.apiBaseUrl;
  elements.availableDomains.value = state.dataDomains;
  sessionStorage.setItem("inventoryDemo.apiBaseUrl", state.apiBaseUrl);
  sessionStorage.setItem("inventoryDemo.dataDomains", state.dataDomains);
  if (state.apiKey) {
    sessionStorage.setItem("inventoryDemo.apiKey", state.apiKey);
  } else {
    sessionStorage.removeItem("inventoryDemo.apiKey");
  }
  if (previousBaseUrl !== state.apiBaseUrl) {
    state.sampleSyncState = {
      checking: false,
      syncing: false,
      done: false,
      itemsSynced: false,
      signalsSynced: null,
      needsReset: false,
      existingItemCount: 0,
      existingSignalCount: 0,
      extraItemCount: 0,
      extraSignalCount: 0,
      message: "Backend changed. Sample sync state needs to be checked again."
    };
    renderSyncCatalogButtonState();
  }
  setConnection("neutral", "Settings saved", "API settings are stored in this browser tab session.");
}

async function checkStatus(options = {}) {
  saveSettings();
  await withBusy(async () => {
    const snapshot = await fetchRuntimeSnapshot();
    renderStatusCards(snapshot);
    if (snapshot.config && !snapshot.config.unavailable) {
      state.runtimeConfig = snapshot.config;
    }
    if (options.autoLoadCatalog) {
      const catalog = await optionalApiGet("/inventory/items");
      if (!catalog.unavailable) {
        state.liveCatalog = catalog.items || [];
        renderProducts();
        await refreshSampleSyncState({ catalog });
      }
    } else {
      await refreshSampleSyncState();
    }

    const inventoryStatus = snapshot.inventoryStatus;
    const syncStatus = snapshot.syncStatus;
    const businessStatus = snapshot.businessStatus;
    const productionStatus = snapshot.productionStatus;
    const good =
      inventoryStatus &&
      !inventoryStatus.unavailable &&
      inventoryStatus.ready &&
      (!syncStatus || syncStatus.unavailable || syncStatus.ready) &&
      (!productionStatus || productionStatus.unavailable || productionStatus.production_ready);

    const detailParts = [];
    if (inventoryStatus && !inventoryStatus.unavailable) {
      detailParts.push(
        `${inventoryStatus.total_items || 0} mirrored products on ${inventoryStatus.vector_backend}`
      );
    }
    if (businessStatus && !businessStatus.unavailable) {
      detailParts.push(`${businessStatus.total_signals || 0} business signals`);
    }
    if (productionStatus && !productionStatus.unavailable) {
      detailParts.push(
        productionStatus.production_ready ? "production-ready storage" : "production issues detected"
      );
    }
    setConnection(
      good ? "good" : "bad",
      good ? "Backend reachable" : "Backend reachable with issues",
      detailParts.join(" · ") || "Runtime snapshot loaded."
    );
    elements.traceOutput.textContent = JSON.stringify(snapshot, null, 2);
  }, "Status check failed", { quiet: options.quiet });
}

async function fetchRuntimeSnapshot() {
  const shouldCheckConfig = Boolean(state.apiKey);
  const [health, config, inventoryStatus, syncStatus, businessStatus, productionStatus, agenticStatus] =
    await Promise.all([
      apiGet("/health", { includeApiKey: false }),
      shouldCheckConfig ? optionalApiGet("/config") : Promise.resolve({ unavailable: true, message: "API key required for /config" }),
      apiGet("/inventory/status"),
      optionalApiGet("/inventory/sync/status"),
      optionalApiGet("/inventory/business/status"),
      optionalApiGet("/inventory/production/status"),
      optionalApiGet("/inventory/agentic/status")
    ]);

  return {
    health,
    config,
    inventoryStatus,
    syncStatus,
    businessStatus,
    productionStatus,
    agenticStatus
  };
}

function renderStatusCards(snapshot = null) {
  if (!snapshot) {
    setStatusCard("health", "Not loaded", "Run a status check to populate backend health.");
    setStatusCard("inventory", "Not loaded", "Catalog and vector backend status will appear here.");
    setStatusCard("sync", "Not loaded", "Vector sync readiness will appear here.");
    setStatusCard("business", "Not loaded", "Business signal readiness will appear here.");
    setStatusCard("production", "Not loaded", "Production storage and issue checks will appear here.");
    return;
  }

  const healthDetail = snapshot.config?.unavailable
    ? `Service ${snapshot.health.service} is responding. Runtime config needs an API key.`
    : `${snapshot.health.service} is responding. Model ${
        snapshot.config.generator_model_name || "unknown"
      }, retrieval ${snapshot.config.retrieval_mode || "unknown"}.`;
  setStatusCard("health", snapshot.health.status || "unknown", healthDetail);

  if (snapshot.inventoryStatus?.unavailable) {
    setStatusCard("inventory", "Unavailable", snapshot.inventoryStatus.message || "Inventory endpoint unavailable.");
  } else {
    setStatusCard(
      "inventory",
      snapshot.inventoryStatus.ready ? "Ready" : "Needs attention",
      `${snapshot.inventoryStatus.total_items} products, ${snapshot.inventoryStatus.rag_enabled_items} in RAG, ${snapshot.inventoryStatus.vector_record_count} vectors on ${snapshot.inventoryStatus.vector_backend}.`
    );
  }

  if (snapshot.syncStatus?.unavailable) {
    setStatusCard("sync", "Unavailable", snapshot.syncStatus.message || "Sync endpoint unavailable.");
  } else {
    const issueCount = snapshot.syncStatus.issues?.length || 0;
    const missingCount = snapshot.syncStatus.missing_vector_ids?.length || 0;
    const staleCount = snapshot.syncStatus.stale_vector_ids?.length || 0;
    setStatusCard(
      "sync",
      snapshot.syncStatus.ready ? "Aligned" : "Drift detected",
      `${issueCount} issues, ${missingCount} missing vectors, ${staleCount} stale vectors.`
    );
  }

  if (snapshot.businessStatus?.unavailable) {
    setStatusCard("business", "Unavailable", snapshot.businessStatus.message || "Business endpoint unavailable.");
  } else {
    setStatusCard(
      "business",
      snapshot.businessStatus.ready ? "Ready" : "Partial",
      `${snapshot.businessStatus.total_signals} signals across ${snapshot.businessStatus.product_count} products. Domains: ${
        (snapshot.businessStatus.domains_available || []).join(", ") || "none"
      }.`
    );
  }

  if (snapshot.productionStatus?.unavailable) {
    setStatusCard(
      "production",
      "Unavailable",
      snapshot.productionStatus.message || "Production status endpoint unavailable."
    );
  } else {
    const issueCount = snapshot.productionStatus.issues?.length || 0;
    setStatusCard(
      "production",
      snapshot.productionStatus.production_ready ? "Ready" : "Blocked",
      `${snapshot.productionStatus.storage_backend} storage, ${snapshot.productionStatus.vector_backend} vectors, ${issueCount} reported issues.`
    );
  }
}

function setStatusCard(key, label, detail) {
  elements[`${key}StatusLabel`].textContent = label;
  elements[`${key}StatusDetail`].textContent = detail;
}

async function loadRuntimeConfig() {
  saveSettings();
  await withBusy(async () => {
    if (!state.apiKey) {
      throw new Error("An API key is required to load /config from this backend.");
    }
    const config = await apiGet("/config");
    state.runtimeConfig = config;
    elements.traceOutput.textContent = JSON.stringify({ config }, null, 2);
    setConnection("good", "Runtime config loaded", `${config.app_name} using ${config.generator_model_name}.`);
  }, "Config load failed");
}

async function loadBackendCatalog(options = {}) {
  saveSettings();
  await withBusy(async () => {
    const catalog = await apiGet("/inventory/items");
    state.liveCatalog = catalog.items || [];
    renderProducts();
    await refreshSampleSyncState({ catalog });
    setConnection(
      "good",
      "Backend catalog loaded",
      `${catalog.total_items} products loaded from the backend mirror.`
    );
    if (!options.quiet) {
      elements.traceOutput.textContent = JSON.stringify({ catalog }, null, 2);
    }
  }, "Catalog load failed", { quiet: options.quiet });
}

async function syncSampleData() {
  saveSettings();
  await withBusy(async () => {
    await refreshSampleSyncState(
      state.liveCatalog.length ? { catalog: { items: state.liveCatalog } } : {}
    );
    if (state.sampleSyncState.done) {
      setConnection("neutral", "Sample already synced", state.sampleSyncState.message);
      elements.traceOutput.textContent = JSON.stringify(
        {
          sample_sync_state: state.sampleSyncState,
          note: "Sample JSON sync is locked because this sample version is already present on the current backend."
        },
        null,
        2
      );
      return;
    }

    state.sampleSyncState = {
      ...state.sampleSyncState,
      syncing: true,
      message: "Resetting backend data and loading the bundled sample version."
    };
    renderSyncCatalogButtonState();

    const existingCatalog = await apiGet("/inventory/items");
    const existingBusinessSignals = await apiGet("/inventory/business/signals");
    const resetSummary = await resetBackendForSampleSync({
      catalog: existingCatalog,
      businessSignals: existingBusinessSignals
    });
    const upsertCatalog = await apiPost("/inventory/items/upsert", { items: buildSampleSyncItemsPayload() });
    const upsertBusiness = Array.isArray(state.sampleData.business_signals) && state.sampleData.business_signals.length
      ? await apiPost("/inventory/business/signals/upsert", {
          signals: buildSampleSyncBusinessSignalsPayload()
        })
      : {
          status: "skipped",
          skipped: true,
          upserted_count: 0,
          total_signals: 0,
          product_count: 0,
          business_signal_path: null
        };
    const rebuild = await optionalApiPost("/inventory/sync/rebuild");
    const syncStatus = await optionalApiGet("/inventory/sync/status");
    const catalog = await apiGet("/inventory/items");
    const businessSignals = await apiGet("/inventory/business/signals");
    state.liveCatalog = catalog.items || [];
    renderProducts();
    renderStatusCards(await fetchRuntimeSnapshot());
    await refreshSampleSyncState({ catalog, businessSignals });

    const businessDetail = upsertBusiness.skipped
      ? "no bundled business signals"
      : `${upsertBusiness.upserted_count} business signals`;
    const rebuildDetail = rebuild.unavailable
      ? "sync-rebuild endpoint unavailable"
      : `${rebuild.rebuilt_count} vectors rebuilt`;
    const syncDetail = syncStatus.unavailable
      ? "sync-status endpoint unavailable"
      : `${syncStatus.vector_record_count} vectors after sync`;
    setConnection(
      state.sampleSyncState.done ? "good" : "bad",
      state.sampleSyncState.done ? "Backend reset + sample synced" : "Sample sync incomplete",
      `${resetSummary.deletedCatalogCount} old products cleared; ${resetSummary.deletedSignalCount} old signals cleared; ${upsertCatalog.upserted_count} products synced; ${businessDetail}; ${rebuildDetail}; ${syncDetail}.`
    );
    elements.traceOutput.textContent = JSON.stringify(
      {
        resetSummary,
        upsertCatalog,
        upsertBusiness,
        rebuild,
        syncStatus,
        catalog,
        businessSignals,
        sampleSyncState: state.sampleSyncState
      },
      null,
      2
    );
  }, "Sync failed");
}

async function resetBackendForSampleSync({ catalog, businessSignals }) {
  const catalogProductIds = dedupe((catalog?.items || []).map((item) => item.product_id).filter(Boolean));
  const signalProductIds = dedupe((businessSignals?.signals || []).map((signal) => signal.product_id).filter(Boolean));

  const deleteSignals = signalProductIds.length
    ? await apiPost("/inventory/business/signals/delete", { product_ids: signalProductIds })
    : {
        status: "skipped",
        skipped: true,
        deleted_count: 0,
        total_signals: 0,
        product_count: 0,
        business_signal_path: null
      };

  const deleteCatalog = catalogProductIds.length
    ? await apiPost("/inventory/items/delete", { product_ids: catalogProductIds })
    : {
        status: "skipped",
        skipped: true,
        deleted_count: 0,
        total_items: 0,
        namespace: null,
        catalog_path: null
      };

  return {
    existingCatalogCount: catalogProductIds.length,
    existingSignalCount: signalProductIds.length,
    deletedCatalogCount: deleteCatalog.deleted_count || 0,
    deletedSignalCount: deleteSignals.deleted_count || 0,
    deleteCatalog,
    deleteSignals
  };
}

async function rebuildSync() {
  saveSettings();
  await withBusy(async () => {
    const rebuild = await apiPost("/inventory/sync/rebuild");
    const snapshot = await fetchRuntimeSnapshot();
    renderStatusCards(snapshot);
    setConnection(
      rebuild.ready ? "good" : "bad",
      rebuild.ready ? "Sync rebuilt" : "Sync rebuild completed with issues",
      `${rebuild.rebuilt_count} vectors rebuilt, ${rebuild.deleted_vector_count} deleted, ${rebuild.vector_record_count} total vectors.`
    );
    elements.traceOutput.textContent = JSON.stringify({ rebuild, snapshot }, null, 2);
  }, "Sync rebuild failed");
}

function renderSyncCatalogButtonState() {
  if (!elements.syncCatalogButton) {
    return;
  }

  const stateLabel = state.sampleSyncState || {};
  let text = "Sync Sample JSON";
  let disabled = false;
  let title = "Sync the bundled sample catalog and business signals into the current backend.";

  if (!state.sampleData) {
    text = "Loading Sample JSON...";
    disabled = true;
    title = "Frontend sample data is still loading.";
  } else if (stateLabel.syncing) {
    text = "Resetting + Syncing...";
    disabled = true;
    title = stateLabel.message || "Sample sync is currently running.";
  } else if (stateLabel.checking) {
    text = "Checking Sample...";
    disabled = true;
    title = stateLabel.message || "Checking whether this backend already has the current sample version.";
  } else if (stateLabel.done) {
    text = "Sample Synced Once";
    disabled = true;
    title = stateLabel.message || "This backend already matches the exact bundled sample state.";
  } else if (stateLabel.needsReset || stateLabel.existingItemCount || stateLabel.existingSignalCount) {
    text = "Reset + Sync Sample JSON";
    title =
      stateLabel.message ||
      "This will clear the current backend catalog and business signals, then load the bundled sample once.";
  }

  elements.syncCatalogButton.textContent = text;
  elements.syncCatalogButton.disabled = disabled;
  elements.syncCatalogButton.title = title;
  elements.syncCatalogButton.classList.toggle("secondary", stateLabel.done);
  elements.syncCatalogButton.classList.toggle("accent", !stateLabel.done);
}

async function refreshSampleSyncState(options = {}) {
  if (!state.sampleData) {
    state.sampleSyncState = {
      checking: false,
      syncing: false,
      done: false,
      itemsSynced: false,
      signalsSynced: null,
      needsReset: false,
      existingItemCount: 0,
      existingSignalCount: 0,
      extraItemCount: 0,
      extraSignalCount: 0,
      message: "Frontend sample data is not loaded yet."
    };
    renderSyncCatalogButtonState();
    return state.sampleSyncState;
  }

  state.sampleSyncState = {
    ...state.sampleSyncState,
    checking: true,
    syncing: false,
    message: "Checking whether this backend exactly matches the bundled sample version."
  };
  renderSyncCatalogButtonState();

  let catalog = options.catalog;
  if (!catalog || catalog.unavailable) {
    catalog = await optionalApiGet("/inventory/items");
  }

  let businessSignals = options.businessSignals;
  if (
    (!businessSignals || businessSignals.unavailable) &&
    Array.isArray(state.sampleData.business_signals) &&
    state.sampleData.business_signals.length
  ) {
    businessSignals = await optionalApiGet("/inventory/business/signals");
  }

  const catalogItems = catalog?.unavailable ? [] : catalog.items || [];
  const signalItems =
    businessSignals?.unavailable || !Array.isArray(businessSignals?.signals) ? [] : businessSignals.signals;
  const itemState = analyzeSampleCatalogState(catalogItems);
  const signalState =
    !Array.isArray(state.sampleData.business_signals) || !state.sampleData.business_signals.length
      ? {
          synced: true,
          missingProductIds: [],
          mismatchedProductIds: [],
          extraProductIds: [],
          totalSignals: 0
        }
      : businessSignals?.unavailable
        ? {
            synced: null,
            missingProductIds: [],
            mismatchedProductIds: [],
            extraProductIds: [],
            totalSignals: 0
          }
        : analyzeSampleBusinessSignalState(signalItems);

  const itemsSynced = itemState.synced === true;
  const signalsSynced = signalState.synced;
  const existingItemCount = catalog?.unavailable ? 0 : catalogItems.length;
  const existingSignalCount =
    businessSignals?.unavailable || !Array.isArray(state.sampleData.business_signals) ? 0 : signalItems.length;
  const extraItemCount = itemState.extraProductIds.length;
  const extraSignalCount = signalState.extraProductIds.length;
  const done =
    itemsSynced === true &&
    signalsSynced === true &&
    extraItemCount === 0 &&
    extraSignalCount === 0;
  const needsReset = !done && (existingItemCount > 0 || existingSignalCount > 0);

  state.sampleSyncState = {
    checking: false,
    syncing: false,
    done,
    itemsSynced,
    signalsSynced,
    needsReset,
    existingItemCount,
    existingSignalCount,
    extraItemCount,
    extraSignalCount,
    message: done
      ? buildSampleSyncDoneMessage()
      : buildSampleSyncPendingMessage({
          catalogUnavailable: Boolean(catalog?.unavailable),
          businessSignalsUnavailable: Boolean(businessSignals?.unavailable),
          itemState,
          signalState,
          existingItemCount,
          existingSignalCount
        })
  };

  renderSyncCatalogButtonState();
  return state.sampleSyncState;
}

function buildSampleSyncItemsPayload() {
  return (state.sampleData?.items || []).map((item) => ({
    ...item,
    metadata: {
      ...(item.metadata || {}),
      sample_sync_origin: "frontend-demo-json",
      sample_sync_version: state.sampleData?.version || "unknown"
    }
  }));
}

function buildSampleSyncBusinessSignalsPayload() {
  return (state.sampleData?.business_signals || []).map((signal) => ({
    ...signal,
    metadata: {
      ...(signal.metadata || {}),
      sample_sync_origin: "frontend-demo-json",
      sample_sync_version: state.sampleData?.version || "unknown"
    }
  }));
}

function analyzeSampleCatalogState(catalogItems) {
  const sampleItems = state.sampleData?.items || [];
  const sampleVersion = state.sampleData?.version || "unknown";
  const sampleIds = new Set(sampleItems.map((item) => item.product_id));
  const catalogById = new Map((catalogItems || []).map((item) => [item.product_id, item]));

  const missingProductIds = [];
  const mismatchedProductIds = [];
  for (const sampleItem of sampleItems) {
    const backendItem = catalogById.get(sampleItem.product_id);
    if (!backendItem) {
      missingProductIds.push(sampleItem.product_id);
      continue;
    }
    if ((backendItem.metadata || {}).sample_sync_version !== sampleVersion) {
      mismatchedProductIds.push(sampleItem.product_id);
    }
  }

  const extraProductIds = (catalogItems || [])
    .map((item) => item.product_id)
    .filter((productId) => !sampleIds.has(productId));

  return {
    synced: missingProductIds.length === 0 && mismatchedProductIds.length === 0,
    missingProductIds,
    mismatchedProductIds,
    extraProductIds,
    totalItems: (catalogItems || []).length
  };
}

function analyzeSampleBusinessSignalState(signalRecords) {
  const sampleSignals = state.sampleData?.business_signals || [];
  const sampleVersion = state.sampleData?.version || "unknown";
  const sampleIds = new Set(sampleSignals.map((signal) => signal.product_id));
  const signalByProductId = new Map((signalRecords || []).map((signal) => [signal.product_id, signal]));

  const missingProductIds = [];
  const mismatchedProductIds = [];
  for (const sampleSignal of sampleSignals) {
    const backendSignal = signalByProductId.get(sampleSignal.product_id);
    if (!backendSignal) {
      missingProductIds.push(sampleSignal.product_id);
      continue;
    }
    if ((backendSignal.metadata || {}).sample_sync_version !== sampleVersion) {
      mismatchedProductIds.push(sampleSignal.product_id);
    }
  }

  const extraProductIds = (signalRecords || [])
    .map((signal) => signal.product_id)
    .filter((productId) => !sampleIds.has(productId));

  return {
    synced: missingProductIds.length === 0 && mismatchedProductIds.length === 0,
    missingProductIds,
    mismatchedProductIds,
    extraProductIds,
    totalSignals: (signalRecords || []).length
  };
}

function buildSampleSyncDoneMessage() {
  return `Backend exactly matches bundled sample ${state.sampleData?.version || "unknown"}. Sync is now locked.`;
}

function buildSampleSyncPendingMessage({
  catalogUnavailable,
  businessSignalsUnavailable,
  itemState,
  signalState,
  existingItemCount,
  existingSignalCount
}) {
  if (catalogUnavailable) {
    return "Could not inspect the backend catalog yet, so sample sync cannot be locked.";
  }

  const parts = [];
  if (existingItemCount || existingSignalCount) {
    parts.push(
      `backend currently holds ${existingItemCount} products and ${existingSignalCount} business signals`
    );
  }
  if (itemState.missingProductIds.length) {
    parts.push(`${itemState.missingProductIds.length} sample products are missing`);
  }
  if (itemState.mismatchedProductIds.length) {
    parts.push(`${itemState.mismatchedProductIds.length} sample products are stale or mismatched`);
  }
  if (itemState.extraProductIds.length) {
    parts.push(`${itemState.extraProductIds.length} non-sample products must be cleared`);
  }
  if (signalState.synced === null) {
    parts.push(
      businessSignalsUnavailable
        ? "business signals could not be verified on this backend"
        : "business signals still need verification"
    );
  } else {
    if (signalState.missingProductIds.length) {
      parts.push(`${signalState.missingProductIds.length} sample business signals are missing`);
    }
    if (signalState.mismatchedProductIds.length) {
      parts.push(`${signalState.mismatchedProductIds.length} sample business signals are stale or mismatched`);
    }
    if (signalState.extraProductIds.length) {
      parts.push(`${signalState.extraProductIds.length} non-sample business signals must be cleared`);
    }
  }
  if (!parts.length) {
    parts.push("Bundled sample data has not been applied yet.");
  }
  return `${parts.join("; ")}. Reset + sync will rebuild this backend into the exact bundled sample state.`;
}

function renderProducts() {
  const items = getCurrentCatalogItems();
  const usingLiveCatalog = state.liveCatalog.length > 0;
  elements.catalogSource.textContent = usingLiveCatalog ? "Backend Catalog" : "Sample JSON";
  elements.productCount.textContent = `${items.length} products`;
  elements.productList.innerHTML = "";

  for (const item of items) {
    const node = elements.productTemplate.content.cloneNode(true);
    const card = node.querySelector("[data-product-card]");
    const active = state.focusedProductIds.includes(item.product_id);
    if (active) {
      card.classList.add("active");
    }
    card.addEventListener("click", () => {
      toggleProductFocus(item.product_id);
    });
    node.querySelector("[data-name]").textContent = item.name;
    node.querySelector("[data-meta]").textContent = [
      item.category || "Uncategorized",
      item.brand || "Unknown brand",
      item.sku,
      `stock ${item.stock ?? "?"}`
    ].join(" · ");
    node.querySelector("[data-price]").textContent = `${item.currency || "USD"} ${Number(item.price || 0).toFixed(2)}`;
    elements.productList.appendChild(node);
  }
}

function renderFocusedProducts() {
  elements.focusedProducts.innerHTML = "";

  if (!state.focusedProductIds.length) {
    const empty = document.createElement("span");
    empty.className = "focus-pill";
    empty.textContent = "No manual product focus";
    elements.focusedProducts.appendChild(empty);
    return;
  }

  for (const productId of state.focusedProductIds) {
    const item = findProductById(productId);
    const pill = document.createElement("span");
    pill.className = "focus-pill";
    pill.textContent = item ? `${item.name} (${item.sku})` : productId;
    elements.focusedProducts.appendChild(pill);
  }
}

function clearFocusedProducts() {
  state.focusedProductIds = [];
  renderProducts();
  renderFocusedProducts();
}

function toggleProductFocus(productId) {
  if (state.focusedProductIds.includes(productId)) {
    state.focusedProductIds = state.focusedProductIds.filter((value) => value !== productId);
  } else {
    state.focusedProductIds = dedupe([...state.focusedProductIds, productId]).slice(0, 12);
  }
  renderProducts();
  renderFocusedProducts();
}

async function askFromForm(event) {
  event.preventDefault();
  const question = elements.questionInput.value.trim();
  if (!question || state.busy) {
    return;
  }

  elements.questionInput.value = "";
  addMessage("user", question);
  const liveMessage = createLiveMessage(
    "bot",
    elements.streamMode.value === "stream"
      ? "Opening a live backend stream..."
      : "Submitting the request to the backend..."
  );

  await askQuestion({
    question,
    endpoint: elements.endpointMode.value,
    assistantMode: elements.assistantMode.value,
    replyStyle: elements.replyStyle.value,
    answerEngine: elements.answerEngine.value,
    render: true,
    liveMessage
  });
}

async function askQuestion({
  question,
  endpoint,
  assistantMode,
  replyStyle,
  answerEngine,
  render,
  liveMessage
}) {
  saveSettings();
  const requestContext = buildRequestContext(question);
  let debugSession = null;

  return await withBusy(
    async () => {
      let routeDecision = null;
      let resolvedEndpoint = endpoint;
      let routeRequestPayload = null;

      if (render) {
        debugSession = startDebugSession({
          question,
          endpoint,
          assistantMode,
          replyStyle,
          answerEngine,
          requestContext
        });
      }

      if (endpoint === "route") {
        routeRequestPayload = {
          question,
          assistant_mode: assistantMode,
          reply_style: replyStyle,
          filters: requestContext.filters || undefined,
          audience: elements.audienceMode.value,
          prefer_fast_response: elements.preferFastResponse.checked,
          allow_agentic: elements.allowAgentic.checked,
          available_data_domains: parseAvailableDomains()
        };
        if (debugSession) {
          debugSession.routeRequest = safeClone(routeRequestPayload);
          debugSession.status = "routing";
          syncDebugSession(debugSession);
        }
        routeDecision = await apiPost("/inventory/route", routeRequestPayload);
        resolvedEndpoint = mapRoutePath(routeDecision.recommended_path);
        state.lastRouteDecision = routeDecision;
        renderRouteSummary(routeDecision, resolvedEndpoint);
        if (debugSession) {
          debugSession.routeDecision = safeClone(routeDecision);
          debugSession.resolvedEndpoint = resolvedEndpoint;
          debugSession.status = "requesting";
          syncDebugSession(debugSession);
        }
      } else {
        state.lastRouteDecision = null;
        resetRouteSummary();
        if (debugSession) {
          debugSession.resolvedEndpoint = resolvedEndpoint;
          debugSession.status = "requesting";
          syncDebugSession(debugSession);
        }
      }

      const payload = buildChatPayload({
        question,
        assistantMode,
        replyStyle,
        answerEngine,
        requestContext,
        resolvedEndpoint
      });
      const traceHint = resolvedEndpoint === "agentic" ? "inventory_agentic" : "inventory_ask";
      if (debugSession) {
        debugSession.traceHint = traceHint;
        debugSession.requestContext = safeClone(requestContext);
        debugSession.chatPath = getChatPath(resolvedEndpoint, {
          stream: render && elements.streamMode.value === "stream"
        });
        debugSession.chatRequest = safeClone(payload);
        syncDebugSession(debugSession);
      }

      let response;
      if (render && elements.streamMode.value === "stream") {
        response = await askQuestionStream({
          resolvedEndpoint,
          payload,
          requestContext,
          routeDecision,
          liveMessage,
          debugSession
        });
      } else {
        response = await apiPost(getChatPath(resolvedEndpoint), payload);
        response.demo_scope = requestContext;
        response.demo_route = routeDecision;
        if (render && liveMessage) {
          finalizeLiveMessage(liveMessage, response);
        }
        if (debugSession) {
          debugSession.response = safeClone(response);
          debugSession.status = "response_ready";
          syncDebugSession(debugSession);
        }
      }

      state.lastTraceId = response.trace_id || null;
      state.lastTraceHint = traceHint;
      elements.lastTraceId.textContent = state.lastTraceId
        ? `Trace ${shortId(state.lastTraceId)}`
        : "No trace";
      elements.lastRoutePath.textContent =
        endpoint === "route"
          ? `Route ${resolvedEndpoint === "agentic" ? "→ Agentic" : "→ Normal RAG"}`
          : resolvedEndpoint === "agentic"
            ? "Direct Agentic"
            : "Direct Normal RAG";

      if (render) {
        rememberConversation(question, response, requestContext);
      }
      if (render && response.trace_id) {
        await loadTrace(response.trace_id, {
          quiet: true,
          traceHint,
          debugSession,
          allowWhileBusy: true
        });
      } else if (debugSession) {
        debugSession.status = "done";
        debugSession.completedAt = new Date().toISOString();
        syncDebugSession(debugSession);
      }
      return response;
    },
    "Chat request failed",
    {
      quiet: !render,
      onError: (error) => {
        if (debugSession) {
          debugSession.status = "failed";
          debugSession.error = error instanceof Error ? error.message : String(error);
          debugSession.completedAt = new Date().toISOString();
          syncDebugSession(debugSession);
        }
        if (render && liveMessage) {
          failLiveMessage(
            liveMessage,
            error instanceof Error ? error.message : "The backend request failed."
          );
        }
      }
    }
  );
}

function buildChatPayload({
  question,
  assistantMode,
  replyStyle,
  answerEngine,
  requestContext,
  resolvedEndpoint
}) {
  const payload = {
    question,
    assistant_mode: assistantMode,
    reply_style: replyStyle,
    top_k: 6,
    answer_engine: answerEngine || "auto",
    conversation_history: state.conversationHistory.slice(-8),
    focused_product_ids: requestContext.focusedProductIds,
    active_filters: state.activeFilters,
    last_answer_plan: state.lastAnswerPlan
  };

  if (requestContext.filters) {
    payload.filters = requestContext.filters;
  }

  if (resolvedEndpoint === "agentic") {
    payload.max_reasoning_steps = 4;
    payload.audience = elements.audienceMode.value;
    payload.available_data_domains = parseAvailableDomains();
  }

  return payload;
}

async function askQuestionStream({
  resolvedEndpoint,
  payload,
  requestContext,
  routeDecision,
  liveMessage,
  debugSession
}) {
  let finalResponse = null;
  let partialMetadata = null;

  await apiStream(getChatPath(resolvedEndpoint, { stream: true }), payload, {
    onStatus(payloadStatus) {
      if (payloadStatus?.status) {
        updateLiveMessageText(liveMessage, `Backend stream started (${payloadStatus.status})...`);
        if (debugSession) {
          debugSession.streamStatuses = [...(debugSession.streamStatuses || []), safeClone(payloadStatus)];
          syncDebugSession(debugSession);
        }
      }
    },
    onMetadata(payloadMetadata) {
      partialMetadata = payloadMetadata;
      updateLiveMessageMeta(liveMessage, payloadMetadata, routeDecision);
      if (debugSession) {
        debugSession.streamMetadata = safeClone(payloadMetadata);
        syncDebugSession(debugSession);
      }
    },
    onDelta(delta) {
      streamIntoLiveMessage(liveMessage, delta);
      if (debugSession) {
        debugSession.streamDeltaCount = (debugSession.streamDeltaCount || 0) + 1;
      }
    },
    onFinal(payloadFinal) {
      finalResponse = {
        ...payloadFinal,
        demo_scope: requestContext,
        demo_route: routeDecision
      };
    }
  });

  if (!finalResponse) {
    throw new Error("Streaming endpoint completed without a final response payload.");
  }

  if (partialMetadata && !liveMessage.hasStreamed) {
    updateLiveMessageText(liveMessage, finalResponse.answer || "");
  }
  finalizeLiveMessage(liveMessage, finalResponse);
  if (debugSession) {
    debugSession.response = safeClone(finalResponse);
    debugSession.status = "response_ready";
    syncDebugSession(debugSession);
  }
  return finalResponse;
}

async function runQualityTests() {
  saveSettings();
  elements.testResults.innerHTML = "";
  for (const testCase of state.sampleData?.test_questions || []) {
    const response = await askQuestion({
      question: testCase.question,
      endpoint: testCase.endpoint || elements.endpointMode.value || "route",
      assistantMode: testCase.assistant_mode || elements.assistantMode.value,
      replyStyle: testCase.reply_style || elements.replyStyle.value,
      answerEngine: testCase.answer_engine || elements.answerEngine.value,
      render: false
    });
    if (response) {
      renderTestResult(testCase, response);
    }
  }
}

async function loadTrace(traceId, options = {}) {
  if (!traceId) {
    if (!options.quiet) {
      elements.traceOutput.textContent = "No trace ID yet. Ask a question first.";
    }
    return;
  }
  if (state.busy && !options.allowWhileBusy) {
    return;
  }

  const managesBusyState = !state.busy;
  if (managesBusyState) {
    state.busy = true;
    setButtonsDisabled(true);
  }
  try {
    const traceResult = await fetchTraceResult(traceId, {
      traceHint: options.traceHint || state.lastTraceHint || elements.endpointMode.value
    });
    if (traceResult.unavailable) {
      if (options.debugSession) {
        options.debugSession.traceResult = safeClone(traceResult);
        options.debugSession.status = options.debugSession.error ? "failed" : "done";
        options.debugSession.completedAt = new Date().toISOString();
        syncDebugSession(options.debugSession);
      }
      if (!options.quiet) {
        setConnection("neutral", "Trace unavailable", traceResult.message);
        elements.traceOutput.textContent = traceResult.message;
      }
      return;
    }
    if (options.debugSession) {
      options.debugSession.traceResult = safeClone(traceResult);
      options.debugSession.status = options.debugSession.error ? "failed" : "done";
      options.debugSession.completedAt = new Date().toISOString();
      syncDebugSession(options.debugSession);
    }
    if (!options.quiet) {
      setConnection("good", "Trace loaded", `Loaded from ${traceResult.endpoint}.`);
    }
    elements.traceOutput.textContent = JSON.stringify(
      {
        loaded_from_endpoint: traceResult.endpoint,
        route_decision: state.lastRouteDecision,
        payload: traceResult.payload
      },
      null,
      2
    );
  } catch (error) {
    if (options.debugSession) {
      options.debugSession.traceResult = {
        unavailable: true,
        message: error instanceof Error ? error.message : String(error)
      };
      options.debugSession.status = options.debugSession.error ? "failed" : "done";
      options.debugSession.completedAt = new Date().toISOString();
      syncDebugSession(options.debugSession);
    }
    setConnection("bad", "Trace load failed", error instanceof Error ? error.message : String(error));
    if (!options.quiet) {
      elements.traceOutput.textContent = `Trace load failed: ${
        error instanceof Error ? error.message : String(error)
      }`;
    }
  } finally {
    if (managesBusyState) {
      state.busy = false;
      setButtonsDisabled(false);
    }
  }
}

async function fetchTraceResult(traceId, options = {}) {
  return await apiGetFirstAvailableTrace(
    traceId,
    options.traceHint || state.lastTraceHint || elements.endpointMode.value
  );
}

function renderTestResult(testCase, response) {
  const productIds = new Set([
    ...(response.recommended_product_ids || []),
    ...(response.cross_sell_product_ids || []),
    ...(response.hits || []).map((hit) => hit.product_id)
  ]);
  const expectedIds = testCase.expected_product_ids || [];
  const forbiddenIds = testCase.forbidden_product_ids || [];
  const expectedFound = expectedIds.length === 0 || expectedIds.some((id) => productIds.has(id));
  const forbiddenFound = forbiddenIds.some((id) => productIds.has(id));
  const noHitsOk = !testCase.expected_no_hits || (response.total_hits === 0 && (response.hits || []).length === 0);
  const textOk = (testCase.must_include_text || []).every((snippet) => (response.answer || "").includes(snippet));
  const passed = expectedFound && !forbiddenFound && noHitsOk && textOk;

  const card = document.createElement("article");
  card.className = `test-card ${passed ? "pass" : "fail"}`;
  card.innerHTML = `
    <strong>${passed ? "PASS" : "CHECK"} · ${escapeHtml(testCase.label)}</strong>
    <span>${escapeHtml(testCase.question)}</span>
    <small>Trace: ${response.trace_id ? shortId(response.trace_id) : "none"} · Engine: ${escapeHtml(
      response.answer_engine || "unknown"
    )} · Hits: ${response.total_hits ?? 0}</small>
    <small>Products: ${escapeHtml(Array.from(productIds).join(", ") || "none")}</small>
  `;
  elements.testResults.appendChild(card);
}

function createLiveMessage(role, text) {
  const message = document.createElement("article");
  message.className = `message ${role} pending`;

  const content = document.createElement("div");
  content.className = "message-content";

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;
  content.appendChild(body);

  const meta = document.createElement("div");
  meta.className = "message-meta";
  content.appendChild(meta);

  const extra = document.createElement("div");
  extra.className = "message-extras";
  content.appendChild(extra);

  message.appendChild(content);
  elements.messages.appendChild(message);
  elements.messages.scrollTop = elements.messages.scrollHeight;

  return {
    message,
    body,
    meta,
    extra,
    hasStreamed: false
  };
}

function addMessage(role, text, response = null) {
  const liveMessage = createLiveMessage(role, text);
  liveMessage.message.classList.remove("pending");

  if (response) {
    finalizeLiveMessage(liveMessage, response);
  }
}

function updateLiveMessageText(liveMessage, text) {
  liveMessage.body.textContent = text;
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function streamIntoLiveMessage(liveMessage, delta) {
  liveMessage.message.classList.add("streaming");
  if (!liveMessage.hasStreamed) {
    liveMessage.body.textContent = delta;
    liveMessage.hasStreamed = true;
  } else {
    liveMessage.body.textContent += delta;
  }
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function updateLiveMessageMeta(liveMessage, metadata, routeDecision) {
  const pills = [];
  if (metadata.answer_engine) {
    pills.push(metadata.answer_engine);
  }
  if (typeof metadata.confidence_score === "number") {
    pills.push(`confidence ${Math.round(metadata.confidence_score * 100)}%`);
  }
  if (routeDecision?.recommended_path) {
    pills.push(`route ${mapRoutePath(routeDecision.recommended_path) === "agentic" ? "agentic" : "normal"}`);
  }
  renderPills(liveMessage.meta, pills);
}

function finalizeLiveMessage(liveMessage, response) {
  liveMessage.message.classList.remove("pending", "streaming");
  liveMessage.body.textContent = response.answer || liveMessage.body.textContent;
  renderResponseDecorations(liveMessage, response);
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function failLiveMessage(liveMessage, message) {
  liveMessage.message.classList.remove("pending", "streaming");
  if (liveMessage.hasStreamed) {
    liveMessage.body.textContent = `${liveMessage.body.textContent}\n\n${message}`;
  } else {
    liveMessage.body.textContent = message;
  }
}

function renderResponseDecorations(liveMessage, response) {
  const pills = [];
  if (response.answer_engine) {
    pills.push(response.answer_engine);
  }
  if (typeof response.confidence_score === "number") {
    pills.push(`confidence ${Math.round(response.confidence_score * 100)}%`);
  }
  if (response.execution_path) {
    pills.push(response.execution_path);
  }
  if (response.retrieval_steps_used) {
    pills.push(`${response.retrieval_steps_used} steps`);
  }
  if (response.demo_scope?.focusedProductIds?.length) {
    pills.push(`scoped ${response.demo_scope.focusedProductIds.length} products`);
  }
  if (response.trace_id) {
    pills.push(`trace ${shortId(response.trace_id)}`);
  }
  if (response.abstained) {
    pills.push("abstained");
  }
  renderPills(liveMessage.meta, pills);

  liveMessage.extra.innerHTML = "";
  const diagnostics = buildDiagnostics(response);
  if (diagnostics.length) {
    const diagnosticsWrap = document.createElement("div");
    diagnosticsWrap.className = "message-diagnostics";
    diagnostics.forEach((block) => diagnosticsWrap.appendChild(block));
    liveMessage.extra.appendChild(diagnosticsWrap);
  }

  if ((response.hits || []).length) {
    const hits = document.createElement("div");
    hits.className = "hits";
    hits.append(...response.hits.slice(0, 6).map(renderHit));
    liveMessage.extra.appendChild(hits);
  }
}

function renderPills(container, values) {
  container.innerHTML = "";
  values
    .filter(Boolean)
    .forEach((value) => {
      const pill = document.createElement("span");
      pill.className = "pill";
      pill.textContent = value;
      container.appendChild(pill);
    });
}

function buildDiagnostics(response) {
  const blocks = [];

  if (response.demo_route) {
    const lines = [
      response.demo_route.reason_summary,
      `Recommended: ${response.demo_route.recommended_path} · Fallback: ${response.demo_route.fallback_path}`
    ];
    if ((response.demo_route.decision_factors || []).length) {
      lines.push(...response.demo_route.decision_factors.slice(0, 4));
    }
    blocks.push(buildDiagnosticBlock("Route Decision", lines));
  }

  if ((response.reasoning_summary || []).length) {
    blocks.push(buildDiagnosticBlock("Reasoning Summary", response.reasoning_summary));
  }

  if ((response.missing_facts || []).length) {
    blocks.push(buildDiagnosticBlock("Missing Facts", response.missing_facts));
  }

  if (response.answer_plan) {
    const lines = [];
    if (response.answer_plan.intent) {
      lines.push(`Intent: ${response.answer_plan.intent}`);
    }
    if (response.answer_plan.primary_product_id) {
      lines.push(`Primary product: ${response.answer_plan.primary_product_id}`);
    }
    if ((response.answer_plan.alternative_product_ids || []).length) {
      lines.push(`Alternatives: ${response.answer_plan.alternative_product_ids.join(", ")}`);
    }
    if ((response.answer_plan.cross_sell_product_ids || []).length) {
      lines.push(`Cross-sell: ${response.answer_plan.cross_sell_product_ids.join(", ")}`);
    }
    if (response.answer_plan.next_best_question) {
      lines.push(`Next question: ${response.answer_plan.next_best_question}`);
    }
    if (lines.length) {
      blocks.push(buildDiagnosticBlock("Answer Plan", lines));
    }
  }

  if (response.verification) {
    const lines = [];
    lines.push(response.verification.passed ? "Verification passed" : "Verification raised issues");
    lines.push(...(response.verification.issues || []));
    lines.push(...(response.verification.final_answer_issues || []));
    if (lines.length > 1 || !response.verification.passed) {
      blocks.push(buildDiagnosticBlock("Verification", lines));
    }
  }

  if (response.memory_resolution) {
    const lines = [];
    if (response.memory_resolution.used_memory) {
      lines.push(response.memory_resolution.reason || "Memory was used to resolve the question.");
    }
    if ((response.memory_resolution.resolved_product_ids || []).length) {
      lines.push(`Resolved products: ${response.memory_resolution.resolved_product_ids.join(", ")}`);
    }
    if (response.memory_resolution.ignored_memory_reason) {
      lines.push(`Ignored memory: ${response.memory_resolution.ignored_memory_reason}`);
    }
    if (lines.length) {
      blocks.push(buildDiagnosticBlock("Memory Resolution", lines));
    }
  }

  if (response.abstention_reason) {
    blocks.push(buildDiagnosticBlock("Abstention", [response.abstention_reason]));
  }

  return blocks;
}

function buildDiagnosticBlock(title, lines) {
  const block = document.createElement("article");
  block.className = "diagnostic-block";

  const heading = document.createElement("strong");
  heading.textContent = title;
  block.appendChild(heading);

  const list = document.createElement("ul");
  list.className = "diagnostic-list";
  lines
    .filter(Boolean)
    .forEach((line) => {
      const item = document.createElement("li");
      item.textContent = line;
      list.appendChild(item);
    });
  block.appendChild(list);

  return block;
}

function renderHit(hit) {
  const card = document.createElement("article");
  card.className = "hit-card";
  card.innerHTML = `
    <strong>${escapeHtml(hit.name)}</strong>
    <small>${escapeHtml(hit.sku)} · ${escapeHtml(hit.category || "No category")} · stock ${hit.stock ?? "?"}</small>
    <small>${escapeHtml(hit.currency || "USD")} ${Number(hit.price || 0).toFixed(2)} · match ${Math.round((hit.score || 0) * 100)}%</small>
  `;
  return card;
}

function renderRouteSummary(routeDecision, resolvedEndpoint) {
  if (!routeDecision) {
    resetRouteSummary();
    return;
  }

  elements.routeSummary.classList.remove("hidden");
  elements.routeSummary.innerHTML = `
    <strong>Route picked ${escapeHtml(resolvedEndpoint === "agentic" ? "Agentic" : "Normal RAG")}</strong>
    <small>${escapeHtml(routeDecision.reason_summary || "No reason summary provided.")}</small>
    <small>Confidence ${Math.round((routeDecision.decision_confidence || 0) * 100)}% · Required data: ${escapeHtml(
      (routeDecision.required_data_domains || []).join(", ") || "catalog"
    )}</small>
  `;
}

function resetRouteSummary() {
  elements.routeSummary.classList.add("hidden");
  elements.routeSummary.innerHTML = "";
  elements.lastRoutePath.textContent = "No route";
}

function startDebugSession({
  question,
  endpoint,
  assistantMode,
  replyStyle,
  answerEngine,
  requestContext
}) {
  const session = {
    id: createLocalId(),
    question,
    endpointMode: endpoint,
    assistantMode,
    replyStyle,
    answerEngine,
    audience: elements.audienceMode.value,
    deliveryMode: elements.streamMode.value,
    preferFastResponse: elements.preferFastResponse.checked,
    allowAgentic: elements.allowAgentic.checked,
    availableDataDomains: parseAvailableDomains(),
    requestContext: safeClone(requestContext),
    routeRequest: null,
    routeDecision: null,
    resolvedEndpoint: null,
    chatPath: null,
    chatRequest: null,
    streamStatuses: [],
    streamMetadata: null,
    streamDeltaCount: 0,
    response: null,
    traceHint: null,
    traceResult: null,
    error: null,
    startedAt: new Date().toISOString(),
    completedAt: null,
    status: "pending"
  };
  state.debugSessions = [session, ...state.debugSessions].slice(0, 12);
  syncDebugSession(session);
  return session;
}

function syncDebugSession(session) {
  if (!session) {
    return;
  }
  renderDebugSessions();
  elements.traceOutput.textContent = JSON.stringify(buildDebugSessionInspectorPayload(session), null, 2);
}

function clearDebugSessions() {
  state.debugSessions = [];
  renderDebugSessions();
  elements.traceOutput.textContent =
    "Trace details, route decisions, status snapshots, and runtime config will appear here.";
}

function renderDebugSessions() {
  elements.turnDebugSessions.innerHTML = "";
  if (!state.debugSessions.length) {
    const empty = document.createElement("article");
    empty.className = "debug-empty-state";
    empty.textContent =
      "Every chat turn will append the route decision, backend payload, response summary, and trace steps here.";
    elements.turnDebugSessions.appendChild(empty);
    return;
  }

  state.debugSessions.forEach((session) => {
    elements.turnDebugSessions.appendChild(renderDebugSession(session));
  });
}

function renderDebugSession(session) {
  const wrapper = document.createElement("article");
  wrapper.className = `debug-session ${session.status === "failed" ? "failed" : ""} ${
    session.status === "pending" || session.status === "routing" || session.status === "requesting"
      ? "pending"
      : ""
  }`;

  const header = document.createElement("div");
  header.className = "debug-session-header";

  const titleWrap = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = session.question;
  titleWrap.appendChild(title);

  const subtitle = document.createElement("small");
  subtitle.textContent = [
    `Started ${formatTimestamp(session.startedAt)}`,
    session.completedAt ? `Finished ${formatTimestamp(session.completedAt)}` : null,
    session.chatPath || null
  ]
    .filter(Boolean)
    .join(" · ");
  titleWrap.appendChild(subtitle);
  header.appendChild(titleWrap);

  const meta = document.createElement("div");
  meta.className = "debug-session-meta";
  const headerPills = [
    session.status.replaceAll("_", " "),
    session.resolvedEndpoint ? `path ${session.resolvedEndpoint}` : `mode ${session.endpointMode}`,
    session.response?.trace_id ? `trace ${shortId(session.response.trace_id)}` : null
  ].filter(Boolean);
  headerPills.forEach((value) => meta.appendChild(buildDebugPill(value)));
  header.appendChild(meta);
  wrapper.appendChild(header);

  const steps = document.createElement("div");
  steps.className = "debug-step-list";
  steps.appendChild(
    buildDebugStepCard({
      title: "Frontend Inputs",
      summary: "The exact controls and focus context used for this turn.",
      keyValues: {
        mode: session.assistantMode,
        reply: session.replyStyle,
        engine: session.answerEngine,
        delivery: session.deliveryMode,
        audience: session.audience,
        focused_products: (session.requestContext?.focusedProductIds || []).join(", ") || "none"
      },
      pills: [
        session.preferFastResponse ? "prefer fast" : "full depth",
        session.allowAgentic ? "agentic allowed" : "agentic blocked"
      ],
      raw: {
        endpoint_mode: session.endpointMode,
        available_data_domains: session.availableDataDomains,
        request_context: session.requestContext
      }
    })
  );

  if (session.routeRequest) {
    steps.appendChild(
      buildDebugStepCard({
        title: "Route Request",
        summary: "Payload sent to `/inventory/route` before the chat endpoint was chosen.",
        keyValues: {
          prefer_fast_response: String(session.routeRequest.prefer_fast_response),
          allow_agentic: String(session.routeRequest.allow_agentic),
          filters: formatCompactValue(session.routeRequest.filters),
          domains: (session.routeRequest.available_data_domains || []).join(", ") || "catalog"
        },
        raw: session.routeRequest
      })
    );
  }

  if (session.routeDecision) {
    steps.appendChild(
      buildDebugStepCard({
        title: "Route Decision",
        summary: session.routeDecision.reason_summary || "Backend route summary unavailable.",
        keyValues: {
          recommended_path: session.routeDecision.recommended_path,
          fallback_path: session.routeDecision.fallback_path,
          question_family: session.routeDecision.signals?.question_family || "unknown",
          confidence:
            typeof session.routeDecision.decision_confidence === "number"
              ? `${Math.round(session.routeDecision.decision_confidence * 100)}%`
              : "unknown",
          policy_version: session.routeDecision.policy_version || "unknown"
        },
        pills: [
          ...(session.routeDecision.required_data_domains || []).map((domain) => `needs ${domain}`),
          ...((session.routeDecision.missing_data_domains || []).map((domain) => `missing ${domain}`))
        ],
        lines: [
          ...(session.routeDecision.decision_factors || []),
          session.routeDecision.family_contract
            ? `Policy family: ${session.routeDecision.family_contract.family} (${session.routeDecision.family_contract.reasoning_mode})`
            : null
        ],
        raw: session.routeDecision
      })
    );
  }

  if (session.chatRequest) {
    steps.appendChild(
      buildDebugStepCard({
        title: "Chat Payload",
        summary: `Payload sent to ${session.chatPath || "the backend chat endpoint"}.`,
        keyValues: {
          top_k: String(session.chatRequest.top_k ?? 0),
          max_reasoning_steps: session.chatRequest.max_reasoning_steps
            ? String(session.chatRequest.max_reasoning_steps)
            : "n/a",
          filters: formatCompactValue(session.chatRequest.filters),
          conversation_turns: String((session.chatRequest.conversation_history || []).length)
        },
        raw: session.chatRequest
      })
    );
  }

  if ((session.streamStatuses || []).length || session.streamMetadata || session.streamDeltaCount) {
    steps.appendChild(
      buildDebugStepCard({
        title: "Streaming Events",
        summary: "SSE metadata emitted before the final response landed.",
        keyValues: {
          status_events: String((session.streamStatuses || []).length),
          delta_chunks: String(session.streamDeltaCount || 0),
          answer_engine: session.streamMetadata?.answer_engine || "unknown",
          retrieval_steps_used: session.streamMetadata?.retrieval_steps_used
            ? String(session.streamMetadata.retrieval_steps_used)
            : "n/a"
        },
        raw: {
          statuses: session.streamStatuses,
          metadata: session.streamMetadata
        }
      })
    );
  }

  if (session.response) {
    steps.appendChild(renderResponseDebugStep(session.response));
  }

  if (session.traceResult?.unavailable) {
    steps.appendChild(
      buildDebugStepCard({
        title: "Trace Load",
        summary: session.traceResult.message || "Trace endpoint was unavailable.",
        raw: session.traceResult
      })
    );
  } else if (session.traceResult?.payload) {
    steps.appendChild(renderTraceDebugStep(session.traceResult));
  }

  if (session.error) {
    steps.appendChild(
      buildDebugStepCard({
        title: "Error",
        summary: session.error,
        raw: { error: session.error }
      })
    );
  }

  wrapper.appendChild(steps);
  return wrapper;
}

function buildDebugStepCard({ title, summary, keyValues = null, pills = [], lines = [], raw = null }) {
  const card = document.createElement("article");
  card.className = "debug-step";

  const header = document.createElement("header");
  const heading = document.createElement("strong");
  heading.textContent = title;
  header.appendChild(heading);
  if (summary) {
    const sub = document.createElement("small");
    sub.textContent = summary;
    header.appendChild(sub);
  }
  card.appendChild(header);

  if (keyValues && Object.keys(keyValues).length) {
    const grid = document.createElement("div");
    grid.className = "debug-kv-grid";
    Object.entries(keyValues).forEach(([label, value]) => {
      const row = document.createElement("div");
      row.className = "debug-kv";
      const key = document.createElement("span");
      key.textContent = label.replaceAll("_", " ");
      const strong = document.createElement("strong");
      strong.textContent = value || "n/a";
      row.appendChild(key);
      row.appendChild(strong);
      grid.appendChild(row);
    });
    card.appendChild(grid);
  }

  if (pills.length) {
    const pillWrap = document.createElement("div");
    pillWrap.className = "debug-step-pills";
    pills.filter(Boolean).forEach((value) => pillWrap.appendChild(buildDebugPill(value)));
    card.appendChild(pillWrap);
  }

  if (lines.length) {
    const list = document.createElement("ul");
    lines.filter(Boolean).forEach((line) => {
      const item = document.createElement("li");
      item.textContent = line;
      list.appendChild(item);
    });
    card.appendChild(list);
  }

  if (raw) {
    const rawWrap = document.createElement("div");
    rawWrap.className = "debug-raw";
    const details = document.createElement("details");
    const summaryEl = document.createElement("summary");
    summaryEl.textContent = "Show raw JSON";
    const pre = document.createElement("pre");
    pre.className = "debug-json";
    pre.textContent = JSON.stringify(raw, null, 2);
    details.appendChild(summaryEl);
    details.appendChild(pre);
    rawWrap.appendChild(details);
    card.appendChild(rawWrap);
  }

  return card;
}

function renderResponseDebugStep(response) {
  const lines = [];
  if (response.reasoning_summary?.length) {
    lines.push(...response.reasoning_summary);
  }
  if (response.missing_facts?.length) {
    lines.push(...response.missing_facts.map((value) => `Missing fact: ${value}`));
  }
  if (response.abstention_reason) {
    lines.push(`Abstention: ${response.abstention_reason}`);
  }

  return buildDebugStepCard({
    title: "Final Response",
    summary: response.answer || "No answer returned.",
    keyValues: {
      answer_engine: response.answer_engine || "unknown",
      confidence:
        typeof response.confidence_score === "number"
          ? `${Math.round(response.confidence_score * 100)}%`
          : "unknown",
      hits: String(response.total_hits ?? 0),
      retrieval_steps_used: response.retrieval_steps_used
        ? String(response.retrieval_steps_used)
        : "n/a",
      primary_product: response.answer_plan?.primary_product_id || "none",
      abstained: response.abstained ? "yes" : "no"
    },
    pills: [
      ...(response.recommended_product_ids || []).map((value) => `recommended ${value}`),
      ...(response.cross_sell_product_ids || []).map((value) => `cross-sell ${value}`)
    ],
    lines,
    raw: response
  });
}

function renderTraceDebugStep(traceResult) {
  const trace = traceResult.payload || {};
  const card = buildDebugStepCard({
    title: "Trace Summary",
    summary: `Loaded from ${traceResult.endpoint}.`,
    keyValues: {
      execution_path: trace.execution_path || "unknown",
      trace_id: trace.trace_id || "unknown",
      retrieval_steps: String((trace.retrieval_steps || []).length),
      confidence:
        typeof trace.confidence_score === "number"
          ? `${Math.round(trace.confidence_score * 100)}%`
          : "unknown"
    },
    lines: [
      ...(trace.reasoning_summary || []),
      ...((trace.missing_facts || []).map((value) => `Missing fact: ${value}`))
    ],
    raw: {
      loaded_from_endpoint: traceResult.endpoint,
      trace_id: trace.trace_id,
      route_decision: trace.route_decision,
      retrieval_stage_counts: trace.retrieval_stage_counts
    }
  });

  if ((trace.retrieval_steps || []).length) {
    const traceSteps = document.createElement("div");
    traceSteps.className = "debug-trace-steps";
    trace.retrieval_steps.forEach((step) => {
      traceSteps.appendChild(renderTraceRetrievalStep(step));
    });
    card.appendChild(traceSteps);
  }

  return card;
}

function renderTraceRetrievalStep(step) {
  const card = document.createElement("article");
  card.className = "debug-trace-step";

  const heading = document.createElement("strong");
  heading.textContent = `Step ${step.step_number} · ${step.action}`;
  card.appendChild(heading);

  const pills = document.createElement("div");
  pills.className = "debug-trace-step-pills";
  [
    `hits ${step.total_hits ?? 0}`,
    step.query_text ? `query ${step.query_text}` : null,
    (step.selected_product_ids || []).length
      ? `selected ${(step.selected_product_ids || []).length}`
      : null,
    (step.rejected_candidates || []).length
      ? `rejected ${(step.rejected_candidates || []).length}`
      : null
  ]
    .filter(Boolean)
    .forEach((value) => pills.appendChild(buildDebugPill(value)));
  card.appendChild(pills);

  if (step.observation) {
    const observation = document.createElement("p");
    observation.textContent = step.observation;
    card.appendChild(observation);
  }

  if (step.selected_candidates?.length) {
    const selected = document.createElement("div");
    selected.className = "debug-candidate-list";
    step.selected_candidates.slice(0, 5).forEach((candidate) => {
      selected.appendChild(
        renderTraceCandidate(candidate, {
          fallbackTitle: "Selected candidate",
          showReasons: false
        })
      );
    });
    card.appendChild(selected);
  }

  if (step.rejected_candidates?.length) {
    const rejected = document.createElement("div");
    rejected.className = "debug-candidate-list";
    step.rejected_candidates.slice(0, 5).forEach((candidate) => {
      rejected.appendChild(
        renderTraceCandidate(candidate, {
          fallbackTitle: "Rejected candidate",
          showReasons: true
        })
      );
    });
    card.appendChild(rejected);
  }

  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Show step JSON";
  const pre = document.createElement("pre");
  pre.className = "debug-json";
  pre.textContent = JSON.stringify(step, null, 2);
  details.appendChild(summary);
  details.appendChild(pre);
  card.appendChild(details);

  return card;
}

function renderTraceCandidate(candidate, options = {}) {
  const card = document.createElement("article");
  card.className = "debug-candidate";
  const title = document.createElement("strong");
  title.textContent = candidate.name || candidate.product_id || options.fallbackTitle || "Candidate";
  card.appendChild(title);
  const meta = document.createElement("small");
  meta.textContent = [
    candidate.product_id || null,
    candidate.category || null,
    typeof candidate.score === "number" ? `score ${candidate.score}` : null
  ]
    .filter(Boolean)
    .join(" · ");
  card.appendChild(meta);
  if (options.showReasons && candidate.rejection_reasons?.length) {
    const reasons = document.createElement("small");
    reasons.textContent = candidate.rejection_reasons.join(" | ");
    card.appendChild(reasons);
  }
  return card;
}

function buildDebugPill(value) {
  const pill = document.createElement("span");
  pill.className = "debug-pill";
  pill.textContent = value;
  return pill;
}

function buildDebugSessionInspectorPayload(session) {
  return {
    session_id: session.id,
    question: session.question,
    status: session.status,
    started_at: session.startedAt,
    completed_at: session.completedAt,
    endpoint_mode: session.endpointMode,
    resolved_endpoint: session.resolvedEndpoint,
    route_request: session.routeRequest,
    route_decision: session.routeDecision,
    chat_path: session.chatPath,
    chat_request: session.chatRequest,
    stream_statuses: session.streamStatuses,
    stream_metadata: session.streamMetadata,
    stream_delta_count: session.streamDeltaCount,
    response: session.response,
    trace_result: session.traceResult,
    error: session.error
  };
}

function buildRequestContext(question) {
  const detectedProductIds = extractFocusedProductIds(question);
  const activeProductIds = state.activeFilters?.product_ids || [];
  const focusedProductIds = dedupe([
    ...detectedProductIds,
    ...state.focusedProductIds,
    ...activeProductIds
  ]).slice(0, 12);

  return {
    focusedProductIds,
    filters: focusedProductIds.length ? { product_ids: focusedProductIds } : null
  };
}

function extractFocusedProductIds(question) {
  const normalizedQuestion = normalizeSearchText(question);
  const matches = [];
  for (const candidate of buildCandidateIndex()) {
    if (candidateMatchesQuestion(candidate, normalizedQuestion)) {
      matches.push(candidate.product_id);
    }
  }
  if (!matches.length && looksLikeChoiceFollowUp(question)) {
    matches.push(...state.focusedProductIds);
  }
  return dedupe(matches).slice(0, 12);
}

function buildCandidateIndex() {
  const byId = new Map();
  for (const item of getCurrentCatalogItems()) {
    byId.set(item.product_id, normalizeCandidate(item));
  }
  for (const hit of state.recentHits) {
    byId.set(hit.product_id, normalizeCandidate(hit));
  }
  return Array.from(byId.values()).filter((candidate) => candidate.product_id);
}

function normalizeCandidate(item) {
  return {
    product_id: item.product_id,
    sku: item.sku || "",
    name: item.name || "",
    category: item.category || "",
    brand: item.brand || ""
  };
}

function candidateMatchesQuestion(candidate, normalizedQuestion) {
  const referenceValues = [candidate.product_id, candidate.sku, candidate.name, candidate.brand]
    .map(normalizeSearchText)
    .filter(Boolean);
  return referenceValues.some((value) => normalizedQuestion.includes(value));
}

function looksLikeChoiceFollowUp(question) {
  const normalized = normalizeSearchText(question);
  return [
    "which one",
    "which should i buy",
    "which one should i buy",
    "which is better",
    "which should i choose",
    "compare them",
    "between these",
    "tell me about this",
    "bundle this",
    "what goes with this"
  ].some((phrase) => normalized.includes(phrase));
}

function rememberConversation(question, response, requestContext) {
  state.conversationHistory.push({ role: "user", content: question });
  state.conversationHistory.push({ role: "assistant", content: response.answer || "" });
  state.conversationHistory = state.conversationHistory.slice(-8);
  state.lastAnswerPlan = response.answer_plan || null;
  state.activeFilters = response.applied_filters || requestContext.filters || null;
  state.recentHits = mergeRecentHits(state.recentHits, response.hits || []);

  const responseProductIds = [
    ...(response.recommended_product_ids || []),
    ...(response.cross_sell_product_ids || []),
    ...(response.hits || []).map((hit) => hit.product_id)
  ];
  state.focusedProductIds = dedupe(
    responseProductIds.length ? responseProductIds : requestContext.focusedProductIds
  ).slice(0, 12);
  renderProducts();
  renderFocusedProducts();
}

function mergeRecentHits(existingHits, newHits) {
  const byId = new Map();
  for (const hit of [...existingHits, ...newHits]) {
    if (hit?.product_id) {
      byId.set(hit.product_id, hit);
    }
  }
  return Array.from(byId.values()).slice(-30);
}

function getCurrentCatalogItems() {
  return state.liveCatalog.length ? state.liveCatalog : state.sampleData?.items || [];
}

function findProductById(productId) {
  return getCurrentCatalogItems().find((item) => item.product_id === productId) || null;
}

async function apiGet(path, options = {}) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    headers: buildHeaders(options)
  });
  return parseApiResponse(response);
}

async function apiPost(path, body) {
  const init = {
    method: "POST",
    headers: buildHeaders()
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }
  const response = await fetch(`${state.apiBaseUrl}${path}`, init);
  return parseApiResponse(response);
}

async function apiStream(path, body, handlers = {}) {
  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    method: "POST",
    headers: buildHeaders({ accept: "text/event-stream" }),
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    throw await buildApiError(response);
  }
  if (!response.body) {
    throw new Error("Streaming response body was unavailable.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let boundaryIndex = buffer.indexOf("\n\n");
    while (boundaryIndex >= 0) {
      const frame = buffer.slice(0, boundaryIndex);
      buffer = buffer.slice(boundaryIndex + 2);
      processSseFrame(frame, handlers);
      boundaryIndex = buffer.indexOf("\n\n");
    }

    if (done) {
      const trimmed = buffer.trim();
      if (trimmed) {
        processSseFrame(trimmed, handlers);
      }
      break;
    }
  }
}

function processSseFrame(frame, handlers) {
  if (!frame.trim()) {
    return;
  }

  let event = "message";
  const dataLines = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  const payloadText = dataLines.join("\n");
  const payload = payloadText ? JSON.parse(payloadText) : undefined;

  if (event === "status") {
    handlers.onStatus?.(payload);
    return;
  }
  if (event === "metadata") {
    handlers.onMetadata?.(payload);
    return;
  }
  if (event === "answer_delta") {
    handlers.onDelta?.(payload?.delta || "");
    return;
  }
  if (event === "final") {
    handlers.onFinal?.(payload);
    return;
  }
  if (event === "error") {
    throw new Error(payload?.message || "Streaming request failed.");
  }
}

async function buildApiError(response) {
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { message: text || response.statusText };
  }
  const message =
    data?.detail?.message ||
    data?.detail?.error ||
    data?.message ||
    response.statusText ||
    "Request failed";
  const error = new Error(`${response.status} ${message}`);
  error.status = response.status;
  error.payload = data;
  return error;
}

async function apiGetFirstAvailableTrace(traceId, traceHint) {
  const candidateEndpoints = buildTraceEndpointCandidates(traceId, traceHint);
  let lastUnavailable = null;
  for (const endpoint of candidateEndpoints) {
    const payload = await optionalApiGet(endpoint);
    if (!payload.unavailable) {
      return { endpoint, payload, unavailable: false };
    }
    lastUnavailable = payload;
  }
  return {
    unavailable: true,
    message:
      lastUnavailable?.message ||
      "This deployed server does not expose a compatible trace endpoint for this response yet."
  };
}

async function optionalApiGet(path) {
  try {
    return await apiGet(path);
  } catch (error) {
    if (error.status === 404) {
      return { status: "unavailable", unavailable: true, endpoint: path, message: error.message };
    }
    throw error;
  }
}

async function optionalApiPost(path, body) {
  try {
    return await apiPost(path, body);
  } catch (error) {
    if (error.status === 404) {
      return { status: "unavailable", unavailable: true, endpoint: path, message: error.message };
    }
    throw error;
  }
}

function buildTraceEndpointCandidates(traceId, traceHint) {
  const encodedTraceId = encodeURIComponent(traceId);
  const preferAgentic =
    String(traceHint || "").includes("inventory_agentic") ||
    String(traceHint || "").includes("agentic") ||
    traceHint === "agentic";
  const ordered = preferAgentic
    ? [`/inventory/agentic/trace/${encodedTraceId}`, `/inventory/chat/trace/${encodedTraceId}`]
    : [`/inventory/chat/trace/${encodedTraceId}`, `/inventory/agentic/trace/${encodedTraceId}`];
  return dedupe(ordered);
}

function buildHeaders(options = {}) {
  const headers = {
    Accept: options.accept || "application/json"
  };
  if (options.includeContentType !== false) {
    headers["Content-Type"] = "application/json";
  }
  if (options.includeApiKey !== false && state.apiKey) {
    headers["X-API-Key"] = state.apiKey;
  }
  return headers;
}

async function parseApiResponse(response) {
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = text ? { message: text } : {};
  }
  if (!response.ok) {
    const message = data?.detail?.message || data?.detail?.error || data?.message || response.statusText;
    const error = new Error(`${response.status} ${message}`);
    error.status = response.status;
    error.payload = data;
    throw error;
  }
  return data;
}

async function withBusy(task, errorPrefix, options = {}) {
  if (state.busy) {
    return null;
  }
  state.busy = true;
  setButtonsDisabled(true);
  try {
    return await task();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    setConnection("bad", errorPrefix, message);
    if (!options.quiet) {
      elements.traceOutput.textContent = `${errorPrefix}: ${message}`;
    }
    if (typeof options.onError === "function") {
      options.onError(error);
    }
    return null;
  } finally {
    state.busy = false;
    setButtonsDisabled(false);
  }
}

function setButtonsDisabled(disabled) {
  for (const button of document.querySelectorAll("button")) {
    button.disabled = disabled;
  }
  if (!disabled) {
    renderSyncCatalogButtonState();
  }
}

function setConnection(kind, label, detail) {
  elements.connectionDot.classList.toggle("good", kind === "good");
  elements.connectionDot.classList.toggle("bad", kind === "bad");
  elements.connectionDot.classList.toggle("neutral", kind === "neutral");
  elements.connectionLabel.textContent = label;
  elements.connectionDetail.textContent = detail;
}

function parseAvailableDomains() {
  return dedupe(
    String(state.dataDomains || "")
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean)
  ).length
    ? dedupe(
        String(state.dataDomains || "")
          .split(",")
          .map((item) => item.trim().toLowerCase())
          .filter(Boolean)
      )
    : [...DEFAULT_DATA_DOMAINS];
}

function getChatPath(resolvedEndpoint, options = {}) {
  const streamSuffix = options.stream ? "/stream" : "";
  return resolvedEndpoint === "agentic"
    ? `/inventory/agentic/ask${streamSuffix}`
    : `/inventory/ask${streamSuffix}`;
}

function mapRoutePath(value) {
  return value === "agentic" ? "agentic" : "ask";
}

function normalizeBaseUrl(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return defaultApiBaseUrl();
  }
  if (normalized === "." || normalized === "/" || normalized.toLowerCase() === "same-origin") {
    return normalizeBaseUrl(globalThis.location?.origin || DEFAULT_LOCAL_BACKEND_URL);
  }
  return normalized.replace(/\/+$/, "");
}

function defaultApiBaseUrl() {
  const origin = globalThis.location?.origin || "";
  const pathname = globalThis.location?.pathname || "";
  if (origin && pathname.startsWith("/frontend")) {
    return normalizeBaseUrl(origin);
  }
  return DEFAULT_LOCAL_BACKEND_URL;
}

function shortId(value) {
  return String(value).slice(0, 8);
}

function createLocalId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `debug-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function dedupe(values) {
  const output = [];
  const seen = new Set();
  for (const value of values) {
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    output.push(value);
  }
  return output;
}

function normalizeSearchText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeClone(value) {
  if (value === undefined) {
    return undefined;
  }
  return JSON.parse(JSON.stringify(value));
}

function formatTimestamp(value) {
  if (!value) {
    return "unknown time";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function formatCompactValue(value) {
  if (!value) {
    return "none";
  }
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "none";
  }
  if (typeof value === "object") {
    const entries = Object.entries(value)
      .filter(([, entryValue]) => {
        if (entryValue == null) {
          return false;
        }
        if (Array.isArray(entryValue)) {
          return entryValue.length > 0;
        }
        return String(entryValue).trim() !== "";
      })
      .map(([key, entryValue]) =>
        `${key}=${
          Array.isArray(entryValue) ? entryValue.join("|") : typeof entryValue === "object" ? JSON.stringify(entryValue) : entryValue
        }`
      );
    return entries.length ? entries.join(", ") : "none";
  }
  return String(value);
}
