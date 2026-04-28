"use strict";

// ---------------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------------
const uploadCard      = document.getElementById("upload-card");
const uploadForm      = document.getElementById("upload-form");
const dropZone        = document.getElementById("drop-zone");
const fileInput       = document.getElementById("pdf-file-input");
const fileNameEl      = document.getElementById("file-name");
const uploadBtn       = document.getElementById("upload-btn");
const uploadError     = document.getElementById("upload-error");
const uploadProgress  = document.getElementById("upload-progress");
const uploadBar       = document.getElementById("upload-progress-bar");
const uploadPctLabel  = document.getElementById("upload-pct-label");
const uploadAgentName = document.getElementById("upload-agent-name");
const pipelineInfo    = document.getElementById("pipeline-info");

const scenarioCard       = document.getElementById("scenario-card");
const docReadyLabel      = document.getElementById("doc-ready-label");
const docReadySub        = document.getElementById("doc-ready-sub");
const newUploadBtn       = document.getElementById("new-upload-btn");
const extractedFieldsGrid = document.getElementById("extracted-fields-grid");

const analyzeForm        = document.getElementById("analyze-form");
const loanAmountInput    = document.getElementById("loan-amount");
const monthlyDebtInput   = document.getElementById("monthly-debt");
const loanAmountError    = document.getElementById("loan-amount-error");
const monthlyDebtError   = document.getElementById("monthly-debt-error");
const analyzeError       = document.getElementById("analyze-error");
const analyzeBtn         = document.getElementById("analyze-btn");
const decisionProgress   = document.getElementById("decision-progress");
const decisionBar        = document.getElementById("decision-progress-bar");
const decisionPctLabel   = document.getElementById("decision-pct-label");
const decisionAgentName  = document.getElementById("decision-agent-name");

const resultsHistory  = document.getElementById("results-history");
const demoBtn         = document.getElementById("demo-btn");

// Chat panel
const chatPanel    = document.getElementById("chat-panel");
const chatMessages = document.getElementById("chat-messages");
const chatInput    = document.getElementById("chat-input");
const chatSend     = document.getElementById("chat-send");

// Grounding popup elements
const groundingPopup      = document.getElementById("grounding-popup");
const groundingPopupImg   = document.getElementById("grounding-popup-img");
const groundingPopupLabel = document.getElementById("grounding-popup-label");
const groundingPopupMeta  = document.getElementById("grounding-popup-meta");
const groundingPopupClose = document.getElementById("grounding-popup-close");

const stageEls = {
  parsing:    document.getElementById("stage-parsing"),
  extracting: document.getElementById("stage-extracting"),
};

const decisionStageEls = {
  deciding:  document.getElementById("stage-deciding"),
  reviewing: document.getElementById("stage-reviewing"),
};

// ---------------------------------------------------------------------------
// Session state
// ---------------------------------------------------------------------------
let selectedFile     = null;
let currentDocId     = null;   // set once extract is done; persists across analyses
let uploadPollTimer  = null;
let analyzePollTimer = null;
let runCount         = 0;      // counts how many analyses have been run
let isDemoMode       = false;  // true when loaded via /demo
let chatHistory      = [];     // [{role, content}] for the chat agent
let runResults       = [];     // accumulates analysis results for chat context

// ---------------------------------------------------------------------------
// Drag & drop / file selection
// ---------------------------------------------------------------------------
dropZone.addEventListener("dragover",  e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
});
dropZone.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") fileInput.click(); });
dropZone.addEventListener("click",   e => { if (!e.target.closest("label")) fileInput.click(); });
fileInput.addEventListener("change", () => { if (fileInput.files[0]) setFile(fileInput.files[0]); });

function setFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    uploadError.textContent = "Only PDF files are supported.";
    return;
  }
  selectedFile = file;
  fileNameEl.textContent = file.name;
  uploadError.textContent = "";
}

// ---------------------------------------------------------------------------
// Demo button — skips upload, loads pre-cached loan_packet extractions
// ---------------------------------------------------------------------------
demoBtn.addEventListener("click", async () => {
  demoBtn.disabled = true;
  demoBtn.textContent = "Loading demo...";
  uploadError.textContent = "";

  try {
    const res = await fetch("/demo");
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Demo failed." }));
      uploadError.textContent = err.detail || "Demo failed.";
      demoBtn.disabled = false;
      demoBtn.textContent = "⚡ Demo — load loan_packet.pdf instantly";
      return;
    }
    const data = await res.json();
    currentDocId = data.doc_id;

    const extractions = data.document_extractions || {};
    const docTypes = Object.values(extractions).map(d => d.doc_type.replace(/_/g, " "));
    docReadyLabel.textContent = data.filename || "loan_packet.pdf (demo)";
    docReadySub.textContent   = `${Object.keys(extractions).length} document(s) extracted: ${docTypes.join(", ")}`;

    extractedFieldsGrid.innerHTML = "";
    Object.entries(extractions).forEach(([name, doc]) => {
      extractedFieldsGrid.appendChild(buildFieldCard(name, {
        doc_type: doc.doc_type,
        fields: doc.extraction,
        field_info: doc.field_info || {},   // confidence + grounding flags
      }, name));
    });

    isDemoMode = true;
    chatPanel.style.display = "block";
    uploadCard.style.display   = "none";
    scenarioCard.style.display = "block";
  } catch (e) {
    uploadError.textContent = "Network error. Is the server running?";
    demoBtn.disabled = false;
    demoBtn.textContent = "⚡ Demo — load loan_packet.pdf instantly";
  }
});

// ---------------------------------------------------------------------------
// Phase 1: Upload → Extract
// ---------------------------------------------------------------------------
uploadForm.addEventListener("submit", async e => {
  e.preventDefault();
  if (!selectedFile) { uploadError.textContent = "Please select a PDF file."; return; }

  uploadBtn.disabled = true;
  uploadBtn.textContent = "Uploading...";
  uploadError.textContent = "";
  uploadProgress.style.display = "block";
  pipelineInfo.style.display = "none";
  setUploadProgress(0, "Uploading file...");

  const fd = new FormData();
  fd.append("pdf_file", selectedFile);

  try {
    const res = await fetch("/upload", { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed." }));
      showUploadError(err.detail || "Upload failed.");
      return;
    }
    const { doc_id } = await res.json();
    pollUploadStatus(doc_id);
  } catch {
    showUploadError("Network error. Is the server running?");
  }
});

function pollUploadStatus(docId) {
  resetUploadStages();
  uploadPollTimer = setInterval(async () => {
    try {
      const res  = await fetch(`/upload-status/${docId}`);
      const data = await res.json();

      setUploadProgress(data.progress_pct, data.current_agent || "Processing...");
      highlightUploadStage(data.status);

      if (data.status === "ready") {
        clearInterval(uploadPollTimer);
        currentDocId = docId;
        onDocumentReady(data);
      } else if (data.status === "error") {
        clearInterval(uploadPollTimer);
        showUploadError("Extraction error: " + (data.error || "Unknown error"));
      }
    } catch { /* network blip, keep polling */ }
  }, 1500);
}

function onDocumentReady(data) {
  // Hide upload progress, show success state
  uploadProgress.style.display = "none";
  uploadBtn.disabled = false;
  uploadBtn.textContent = "Extract Fields";

  // Populate and show scenario card
  const extractions = data.document_extractions || {};
  const docTypes = Object.values(extractions).map(d => d.doc_type.replace(/_/g, " "));
  docReadyLabel.textContent = selectedFile ? selectedFile.name : "Document ready";
  docReadySub.textContent   = `${Object.keys(extractions).length} document(s) extracted: ${docTypes.join(", ")}`;

  extractedFieldsGrid.innerHTML = "";
  Object.entries(extractions).forEach(([name, doc]) => {
    extractedFieldsGrid.appendChild(buildFieldCard(name, {
      doc_type: doc.doc_type,
      fields: doc.extraction,
    }));
  });

  uploadCard.style.display  = "none";
  scenarioCard.style.display = "block";
}

function setUploadProgress(pct, agentName) {
  uploadBar.style.width     = pct + "%";
  uploadPctLabel.textContent = pct + "%";
  if (agentName) uploadAgentName.textContent = agentName;
}

function resetUploadStages() {
  Object.values(stageEls).forEach(el => el && el.classList.remove("active", "done"));
}

const UPLOAD_STATUS_STAGE = { parsing: "parsing", extracting: "extracting", ready: "extracting" };

function highlightUploadStage(status) {
  const order = ["parsing", "extracting"];
  const currentIdx = order.indexOf(UPLOAD_STATUS_STAGE[status] || "parsing");
  order.forEach((key, idx) => {
    const el = stageEls[key];
    if (!el) return;
    el.classList.toggle("done",   idx < currentIdx);
    el.classList.toggle("active", idx === currentIdx);
    if (idx > currentIdx) el.classList.remove("active", "done");
  });
}

function showUploadError(msg) {
  uploadProgress.style.display = "none";
  pipelineInfo.style.display   = "block";
  uploadBtn.disabled = false;
  uploadBtn.textContent = "Extract Fields";
  uploadError.textContent = msg;
}

// ---------------------------------------------------------------------------
// "Upload new document" button — resets to upload view, keeps history
// ---------------------------------------------------------------------------
newUploadBtn.addEventListener("click", () => {
  currentDocId   = null;
  selectedFile   = null;
  fileNameEl.textContent = "";
  fileInput.value = "";
  uploadError.textContent = "";
  pipelineInfo.style.display = "block";
  uploadProgress.style.display = "none";
  uploadBtn.disabled = false;
  uploadBtn.textContent = "Extract Fields";
  demoBtn.disabled = false;
  demoBtn.textContent = "⚡ Demo — load loan_packet.pdf instantly";
  isDemoMode = false;
  chatHistory = [];
  runResults  = [];
  chatPanel.style.display = "none";
  chatMessages.innerHTML = `<div class="chat-bubble assistant">
    Hi! I'm your loan advisor. The borrower's monthly income is <strong>$980/mo</strong> (bi-weekly gross $452.43). I've pre-computed the approval range scenarios above — click any chip to run one, or ask me anything about the decision logic, DTI limits, or risk scoring.
  </div>`;
  resetUploadStages();

  scenarioCard.style.display = "none";
  uploadCard.style.display   = "block";
});

// ---------------------------------------------------------------------------
// Phase 2: Scenario Analysis
// ---------------------------------------------------------------------------
analyzeForm.addEventListener("submit", async e => {
  e.preventDefault();
  if (!validateAnalyzeForm()) return;
  if (!currentDocId) { analyzeError.textContent = "No document loaded."; return; }

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analyzing...";
  analyzeError.textContent = "";
  decisionProgress.style.display = "block";
  setDecisionProgress(0, "Starting decision agent...");

  const fd = new FormData();
  fd.append("doc_id",       currentDocId);
  fd.append("loan_amount",  loanAmountInput.value);
  fd.append("monthly_debt", monthlyDebtInput.value);

  try {
    const res = await fetch("/analyze", { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Analysis failed." }));
      showAnalyzeError(err.detail || "Analysis failed.");
      return;
    }
    const { job_id } = await res.json();
    pollAnalysisStatus(job_id, parseFloat(loanAmountInput.value), parseFloat(monthlyDebtInput.value));
  } catch {
    showAnalyzeError("Network error. Is the server running?");
  }
});

function pollAnalysisStatus(jobId, loanAmount, monthlyDebt) {
  analyzePollTimer = setInterval(async () => {
    try {
      const status = await fetch(`/status/${jobId}`).then(r => r.json());
      setDecisionProgress(status.progress_pct, status.current_agent || "Deciding...");
      highlightDecisionStage(status.status);

      if (status.status === "done") {
        clearInterval(analyzePollTimer);
        const result = await fetch(`/result/${jobId}`).then(r => r.json());
        decisionProgress.style.display = "none";
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = "Run Analysis";
        appendResultCard(result, loanAmount, monthlyDebt);
      } else if (status.status === "error") {
        clearInterval(analyzePollTimer);
        showAnalyzeError("Decision error: " + (status.error || "Unknown error"));
      }
    } catch { /* keep polling */ }
  }, 1000);
}

function highlightDecisionStage(status) {
  const order = ["deciding", "reviewing"];
  const statusToIdx = { deciding: 0, reviewing: 1, done: 1 };
  const currentIdx = statusToIdx[status] ?? -1;
  order.forEach((key, idx) => {
    const el = decisionStageEls[key];
    if (!el) return;
    el.classList.toggle("done",   idx < currentIdx);
    el.classList.toggle("active", idx === currentIdx);
    if (idx > currentIdx) el.classList.remove("active", "done");
  });
}

function setDecisionProgress(pct, agentName) {
  decisionBar.style.width      = pct + "%";
  decisionPctLabel.textContent  = pct + "%";
  if (agentName) decisionAgentName.textContent = agentName;
}

function showAnalyzeError(msg) {
  decisionProgress.style.display = "none";
  analyzeBtn.disabled = false;
  analyzeBtn.textContent = "Run Analysis";
  analyzeError.textContent = msg;
}

function validateAnalyzeForm() {
  let ok = true;
  const loan = parseFloat(loanAmountInput.value);
  if (!loanAmountInput.value || isNaN(loan) || loan <= 0) {
    loanAmountError.textContent = "Enter a valid loan amount greater than $0.";
    loanAmountInput.classList.add("input-error");
    ok = false;
  } else {
    loanAmountError.textContent = "";
    loanAmountInput.classList.remove("input-error");
  }
  const debt = parseFloat(monthlyDebtInput.value);
  if (monthlyDebtInput.value === "" || isNaN(debt) || debt < 0) {
    monthlyDebtError.textContent = "Enter a valid amount (0 or more).";
    monthlyDebtInput.classList.add("input-error");
    ok = false;
  } else {
    monthlyDebtError.textContent = "";
    monthlyDebtInput.classList.remove("input-error");
  }
  return ok;
}

// ---------------------------------------------------------------------------
// Append a result card to the history
// ---------------------------------------------------------------------------
function appendResultCard(result, loanAmount, monthlyDebt) {
  runCount++;
  // Accumulate for chat context
  runResults.push({ loan_amount: loanAmount, monthly_debt: monthlyDebt, ...result });

  const d = result.decision;
  if (!d) return;

  // Use manager's final word if available
  const finalDecision = d.final_decision || d.decision;
  const approved = finalDecision === "APPROVED";
  const wasOverridden = d.manager_review && !d.manager_review.upheld;

  const card = document.createElement("div");
  card.className = "result-card";

  // Header row: run label + final decision badge
  const header = document.createElement("div");
  header.className = "result-card-header";
  header.innerHTML = `
    <span class="result-run-label">Run #${runCount}</span>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      ${wasOverridden ? `<span style="font-size:0.75rem;color:var(--denied);font-weight:600">Agent 3: ${d.decision}</span><span style="color:var(--text-muted)">→</span>` : ""}
      <div class="decision-badge ${approved ? "badge-approved" : "badge-denied"}" style="font-size:1.3rem;padding:12px 24px;">
        ${approved ? "✓ APPROVED" : "✗ DENIED"}${wasOverridden ? " (overridden)" : ""}
      </div>
    </div>
  `;
  card.appendChild(header);

  // Params line
  const params = document.createElement("p");
  params.className = "result-params";
  params.textContent =
    `Loan: $${loanAmount.toLocaleString()}  ·  Monthly debt: $${monthlyDebt.toLocaleString()}` +
    (d.dti_ratio != null ? `  ·  DTI: ${(d.dti_ratio * 100).toFixed(1)}%` : "");
  card.appendChild(params);

  // Fraud flags
  if (d.flags && d.flags.length > 0) {
    const flagsDiv = document.createElement("div");
    flagsDiv.className = "flags-section";
    flagsDiv.innerHTML = `<h3 class="flags-title">Fraud / Anomaly Flags</h3>`;
    const ul = document.createElement("ul");
    ul.className = "flags-list";
    d.flags.forEach(f => { const li = document.createElement("li"); li.textContent = f; ul.appendChild(li); });
    flagsDiv.appendChild(ul);
    card.appendChild(flagsDiv);
  }

  // Agent 3 reasoning
  const reasonsDiv = document.createElement("div");
  reasonsDiv.className = "reasons-section";
  reasonsDiv.innerHTML = `<h3 class="section-title">Loan Decision Agent — Reasoning</h3>`;
  const ul = document.createElement("ul");
  ul.className = "reasons-list";
  (d.reasons || []).forEach(r => { const li = document.createElement("li"); li.textContent = r; ul.appendChild(li); });
  reasonsDiv.appendChild(ul);
  card.appendChild(reasonsDiv);

  // Manager review panel
  if (d.manager_review) {
    const mr = d.manager_review;
    const riskClass = `risk-${mr.risk_level}`;
    const verdictText = mr.upheld
      ? `Upheld — ${d.decision}`
      : `Overridden: ${d.decision} → ${d.final_decision}`;

    const managerDiv = document.createElement("div");
    managerDiv.className = "manager-section";
    managerDiv.innerHTML = `
      <div class="manager-header">
        <div class="manager-header-left">
          <span class="manager-label">Manager Agent</span>
          <span class="manager-verdict">${verdictText}</span>
        </div>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <span class="risk-badge ${riskClass}">Risk: ${mr.risk_level}</span>
          ${mr.escalate ? `<span class="escalation-badge">⚑ Escalate to human</span>` : ""}
        </div>
      </div>
      <ul class="manager-notes">
        ${mr.review_notes.map((note, i) =>
          `<li class="${i === 0 && !mr.upheld ? "override-note" : ""}">${note}</li>`
        ).join("")}
      </ul>
    `;
    card.appendChild(managerDiv);
  }

  resultsHistory.prepend(card);
}

// ---------------------------------------------------------------------------
// Shared: build extracted field card
// docName is passed as the second positional arg when called from demo flow
// ---------------------------------------------------------------------------
function buildFieldCard(docName, docData, groundingDocName) {
  const card = document.createElement("div");
  card.className = "field-card";

  const title = document.createElement("p");
  title.className = "field-card-title";
  title.textContent = docName.replace(/_/g, " ");
  card.appendChild(title);

  const typePill = document.createElement("span");
  typePill.className = "field-card-type";
  typePill.textContent = (docData.doc_type || "").replace(/_/g, " ");
  card.appendChild(typePill);

  const fields = docData.fields || {};
  const fieldInfo = docData.field_info || {};

  if (Object.keys(fields).length === 0) {
    const empty = document.createElement("p");
    empty.style.cssText = "font-size:0.8rem;color:var(--text-muted)";
    empty.textContent = "No fields";
    card.appendChild(empty);
    return card;
  }

  Object.entries(fields).forEach(([key, val]) => {
    const row = document.createElement("div");
    row.className = "field-row";

    const keyEl = document.createElement("span");
    keyEl.className = "field-key";
    keyEl.textContent = key.replace(/_/g, " ");
    row.appendChild(keyEl);

    // Value + optional confidence badge + grounding chip
    const rightGroup = document.createElement("span");
    rightGroup.style.cssText = "display:inline-flex;align-items:center;flex-wrap:wrap;gap:2px;";

    const valEl = document.createElement("span");
    valEl.className = "field-val";
    valEl.textContent = formatFieldValue(key, val);
    rightGroup.appendChild(valEl);

    const info = fieldInfo[key];
    if (info) {
      // Confidence badge
      const conf = info.confidence;
      const confClass = conf >= 0.9 ? "confidence-high" : conf >= 0.7 ? "confidence-med" : "confidence-low";
      const confBadge = document.createElement("span");
      confBadge.className = `confidence-badge ${confClass}`;
      confBadge.title = `Extraction confidence: ${Math.round(conf * 100)}%`;
      confBadge.textContent = `${Math.round(conf * 100)}%`;
      rightGroup.appendChild(confBadge);

      // Grounding chip (only if grounding available)
      if (info.has_grounding && groundingDocName) {
        const chip = document.createElement("button");
        chip.className = "grounding-chip";
        chip.title = "View source location in document";
        chip.innerHTML = "&#128065; source";
        chip.addEventListener("click", (e) => {
          e.stopPropagation();
          showGroundingPopup(groundingDocName, key, chip, val, key);
        });
        rightGroup.appendChild(chip);
      }
    }

    row.appendChild(rightGroup);
    card.appendChild(row);
  });

  return card;
}

// ---------------------------------------------------------------------------
// Chat Agent
// ---------------------------------------------------------------------------

// Scenario chip clicks — fill form and run analysis
document.getElementById("scenario-chips").addEventListener("click", e => {
  const chip = e.target.closest(".scenario-chip");
  if (!chip) return;
  const loan = chip.dataset.loan;
  const debt = chip.dataset.debt;
  const label = chip.dataset.label;
  fillAndRunScenario(parseFloat(loan), parseFloat(debt), label);
});

function fillAndRunScenario(loan, debt, label) {
  loanAmountInput.value  = loan;
  monthlyDebtInput.value = debt;
  loanAmountInput.classList.remove("input-error");
  monthlyDebtInput.classList.remove("input-error");
  loanAmountError.textContent  = "";
  monthlyDebtError.textContent = "";
  // Scroll form into view then submit
  analyzeBtn.scrollIntoView({ behavior: "smooth", block: "center" });
  setTimeout(() => analyzeForm.requestSubmit(), 300);
}

function addChatBubble(role, html, isHtml = false) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  if (isHtml) bubble.innerHTML = html;
  else bubble.textContent = html;
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

function parseScenarioFromReply(text) {
  // Extract ```scenario {...} ``` block from assistant reply
  const match = text.match(/```scenario\s*(\{[\s\S]*?\})\s*```/);
  if (!match) return null;
  try { return JSON.parse(match[1]); } catch { return null; }
}

function renderAssistantMessage(text) {
  // Strip the scenario code block from display text
  const displayText = text.replace(/```scenario[\s\S]*?```/g, "").trim();
  const scenario = parseScenarioFromReply(text);

  // Convert basic markdown: **bold**, newlines
  const html = displayText
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");

  let fullHtml = html;
  if (scenario) {
    fullHtml += `<br><button class="chat-run-scenario"
      data-loan="${scenario.loan_amount}"
      data-debt="${scenario.monthly_debt}"
      data-label="${scenario.label || ""}">
      ▶ Run: ${scenario.label || `$${Number(scenario.loan_amount).toLocaleString()}`}
    </button>`;
  }

  const bubble = addChatBubble("assistant", fullHtml, true);

  // Wire up the run button if present
  const btn = bubble.querySelector(".chat-run-scenario");
  if (btn) {
    btn.addEventListener("click", () => {
      fillAndRunScenario(
        parseFloat(btn.dataset.loan),
        parseFloat(btn.dataset.debt),
        btn.dataset.label
      );
    });
  }
}

async function sendChatMessage(userText) {
  if (!userText.trim()) return;

  // Add user message to history and UI
  chatHistory.push({ role: "user", content: userText });
  addChatBubble("user", userText);
  chatInput.value = "";
  chatSend.disabled = true;

  const thinking = addChatBubble("thinking", "Thinking…");

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: chatHistory,
        doc_id: currentDocId,
        run_results: runResults,
      }),
    });

    chatMessages.removeChild(thinking);

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      addChatBubble("assistant", `Error: ${err.detail || "Chat unavailable."}`);
      chatHistory.pop();
      return;
    }

    const { reply } = await res.json();
    chatHistory.push({ role: "assistant", content: reply });
    renderAssistantMessage(reply);

  } catch {
    chatMessages.removeChild(thinking);
    addChatBubble("assistant", "Network error. Is the server running?");
    chatHistory.pop();
  } finally {
    chatSend.disabled = false;
    chatInput.focus();
  }
}

chatSend.addEventListener("click", () => sendChatMessage(chatInput.value));
chatInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatMessage(chatInput.value); }
});

// ---------------------------------------------------------------------------
// Grounding popup logic
// ---------------------------------------------------------------------------
let groundingCache = {};   // key: "docName/field" -> img_b64 data

async function showGroundingPopup(docName, field, anchorEl, fieldVal, fieldKey) {
  const cacheKey = `${docName}/${field}`;

  groundingPopupLabel.textContent = `${field.replace(/_/g, " ")} — visual grounding`;
  groundingPopupImg.src = "";
  groundingPopupMeta.textContent = "Loading...";
  groundingPopup.style.display = "block";
  positionPopup(anchorEl);

  if (groundingCache[cacheKey]) {
    renderGroundingData(groundingCache[cacheKey], fieldVal, fieldKey);
    return;
  }

  try {
    const res = await fetch(`/grounding/${encodeURIComponent(docName)}/${encodeURIComponent(field)}`);
    if (!res.ok) { groundingPopupMeta.textContent = "Grounding data unavailable."; return; }
    const data = await res.json();
    groundingCache[cacheKey] = data;
    renderGroundingData(data, fieldVal, fieldKey);
  } catch {
    groundingPopupMeta.textContent = "Failed to load grounding image.";
  }
}

function renderGroundingData(data, fieldVal, fieldKey) {
  groundingPopupImg.src = `data:image/png;base64,${data.img_b64}`;
  groundingPopupMeta.textContent =
    `Page ${data.page + 1} · ${fieldKey.replace(/_/g, " ")}: ${fieldVal}`;
}

function positionPopup(anchorEl) {
  const rect = anchorEl.getBoundingClientRect();
  const popupW = 380;
  let left = rect.right + 10;
  if (left + popupW > window.innerWidth - 10) {
    left = rect.left - popupW - 10;
  }
  if (left < 10) left = 10;
  let top = rect.top + window.scrollY - 10;
  groundingPopup.style.left = `${left}px`;
  groundingPopup.style.top  = `${top}px`;
  groundingPopup.style.width = `${popupW}px`;
}

groundingPopupClose.addEventListener("click", () => {
  groundingPopup.style.display = "none";
});

document.addEventListener("click", (e) => {
  if (!groundingPopup.contains(e.target) && !e.target.closest(".grounding-chip")) {
    groundingPopup.style.display = "none";
  }
});

function formatFieldValue(key, val) {
  if (val === null || val === undefined) return "—";
  const moneyKeys = ["gross_pay", "net_pay", "balance", "total_investment", "changes_in_value"];
  if (moneyKeys.includes(key) && typeof val === "number") {
    return "$" + val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return String(val);
}
