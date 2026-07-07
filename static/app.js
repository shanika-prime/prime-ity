// =====================================================================
// Shared helpers
// =====================================================================
const ACCEPTED_IMG_EXT = ["png", "jpg", "jpeg", "webp"];

function getExt(filename) {
  const m = (filename || "").toLowerCase().match(/\.([a-z0-9]+)$/);
  return m ? m[1] : "";
}

/** Filters a FileList into accepted images, reports rejects via errorEl. */
function filterImageFiles(fileList, errorEl) {
  const accepted = [];
  const rejected = [];
  [...fileList].forEach((f) => {
    const typeOk = /^image\/(png|jpe?g|webp)$/i.test(f.type || "");
    const extOk = ACCEPTED_IMG_EXT.includes(getExt(f.name));
    // Mobile browsers/cloud photo pickers often report an empty or generic
    // f.type, so fall back to the file extension rather than rejecting it.
    if (typeOk || extOk) accepted.push(f);
    else rejected.push(f.name || "unnamed file");
  });
  errorEl.textContent = rejected.length
    ? `Skipped ${rejected.length} file(s) — only PNG, JPG, and WEBP are supported: ${rejected.join(", ")}`
    : "";
  return accepted;
}

/** Filters a FileList into accepted PDFs, reports rejects via errorEl. */
function filterPdfFiles(fileList, errorEl) {
  const accepted = [];
  const rejected = [];
  [...fileList].forEach((f) => {
    const typeOk = /^application\/pdf$/i.test(f.type || "");
    const extOk = getExt(f.name) === "pdf";
    if (typeOk || extOk) accepted.push(f);
    else rejected.push(f.name || "unnamed file");
  });
  errorEl.textContent = rejected.length
    ? `Skipped ${rejected.length} file(s) — only PDF is supported: ${rejected.join(", ")}`
    : "";
  return accepted;
}

/** Renders image thumbnails for a list of File objects into a container. */
function renderThumbs(container, files, onChange) {
  container.innerHTML = "";
  files.forEach((f, i) => {
    const div = document.createElement("div");
    div.className = "thumb";
    const img = document.createElement("img");
    img.src = URL.createObjectURL(f);
    const btn = document.createElement("button");
    btn.className = "thumb__remove";
    btn.textContent = "✕";
    btn.onclick = (e) => {
      e.stopPropagation();
      files.splice(i, 1);
      onChange();
    };
    div.appendChild(img);
    div.appendChild(btn);
    container.appendChild(div);
  });
}

/** Renders filename chips for a list of (non-image) File objects, e.g. PDFs. */
function renderFileChips(container, files, onChange) {
  container.innerHTML = "";
  files.forEach((f, i) => {
    const chip = document.createElement("div");
    chip.className = "file-chip";

    const icon = document.createElement("span");
    icon.className = "file-chip__icon";
    icon.textContent = "📄";

    const name = document.createElement("span");
    name.className = "file-chip__name";
    name.textContent = f.name;

    const btn = document.createElement("button");
    btn.className = "file-chip__remove";
    btn.type = "button";
    btn.textContent = "✕";
    btn.onclick = (e) => {
      e.stopPropagation();
      files.splice(i, 1);
      onChange();
    };

    chip.appendChild(icon);
    chip.appendChild(name);
    chip.appendChild(btn);
    container.appendChild(chip);
  });
}

/** Safely parses a fetch Response as JSON, throwing a readable error instead
 * of a cryptic "Unexpected token '<'" if the server returned an HTML error
 * page (e.g. a 413 Payload Too Large or an unhandled 500). */
async function parseJsonResponse(res) {
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    if (res.status === 413) {
      throw new Error("Upload too large — try fewer or smaller files.");
    }
    throw new Error(`Server error (status ${res.status}). Please try again.`);
  }
  return res.json();
}

function wireDropzone(dropzone, fileInput, onFiles) {
  // Note: dropzone is a <label for="..."> pointing at fileInput, so clicking
  // it already opens the file picker natively — no extra JS click handler
  // needed (adding one caused the picker to double-fire and reopen on mobile).
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("is-dragover");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-dragover");
    onFiles(e.dataTransfer.files);
  });
  fileInput.addEventListener("change", (e) => onFiles(e.target.files));
}

const SEGMENT_FIELDS = [
  ["airline", "Airline"],
  ["flight_number", "Flight #"],
  ["cabin_class", "Class"],
  ["departure_airport_code", "From"],
  ["departure_city", "Dep. City"],
  ["departure_date", "Dep. Date"],
  ["departure_time", "Dep. Time"],
  ["departure_terminal", "Dep. Terminal"],
  ["arrival_airport_code", "To"],
  ["arrival_city", "Arr. City"],
  ["arrival_date", "Arr. Date"],
  ["arrival_time", "Arr. Time"],
  ["arrival_terminal", "Arr. Terminal"],
  ["duration", "Duration"],
  ["stops", "Stops"],
  ["baggage", "Baggage"],
  ["pnr", "PNR"],
  ["seat", "Seat"],
];

/** Renders editable flight segment cards into listEl, mutating `segments`
 * in place as the user edits fields. Shared by both PDF-generating tabs. */
function renderSegmentCards(listEl, segments) {
  listEl.innerHTML = "";
  segments.forEach((seg, idx) => {
    const card = document.createElement("div");
    card.className = "seg-card";

    const head = document.createElement("div");
    head.className = "seg-card__head";
    head.innerHTML = `
      <span class="seg-card__route">${seg.departure_airport_code || "---"} → ${seg.arrival_airport_code || "---"}</span>
      <span class="seg-card__idx">Flight ${idx + 1} of ${segments.length}</span>
    `;
    card.appendChild(head);

    const grid = document.createElement("div");
    grid.className = "seg-grid";
    SEGMENT_FIELDS.forEach(([key, label]) => {
      const field = document.createElement("div");
      field.className = "seg-field";
      field.innerHTML = `<label>${label}</label>`;
      const input = document.createElement("input");
      input.type = "text";
      input.value = seg[key] || "";
      input.addEventListener("input", (e) => {
        segments[idx][key] = e.target.value;
        if (key === "departure_airport_code" || key === "arrival_airport_code") {
          head.querySelector(".seg-card__route").textContent =
            `${segments[idx].departure_airport_code || "---"} → ${segments[idx].arrival_airport_code || "---"}`;
        }
      });
      field.appendChild(input);
      grid.appendChild(field);
    });
    card.appendChild(grid);
    listEl.appendChild(card);
  });
}

/** Wires up a dynamic multi-passenger-name list (add/remove rows). Returns
 * a getNames() function that collects the current non-empty names. */
function createPassengerList(listEl, addBtnEl) {
  function addRow(prefill) {
    const row = document.createElement("div");
    row.className = "pax-row";

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Passenger";
    input.value = prefill !== undefined ? prefill : (listEl.children.length === 0 ? "Passenger" : "");
    row.appendChild(input);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "pax-row__remove";
    removeBtn.textContent = "✕";
    removeBtn.title = "Remove passenger";
    removeBtn.addEventListener("click", () => {
      // Always keep at least one row so there's somewhere to type a name.
      if (listEl.children.length > 1) {
        row.remove();
      } else {
        input.value = "";
      }
    });
    row.appendChild(removeBtn);

    listEl.appendChild(row);
  }

  addBtnEl.addEventListener("click", () => addRow(""));
  addRow("Passenger");

  return {
    getNames: () =>
      [...listEl.querySelectorAll("input")].map((el) => el.value.trim()).filter((v) => v),
  };
}

/** Posts to /generate-pdf and triggers a browser download of the resulting
 * file. Shared by both PDF-generating tabs. */
async function downloadItineraryPdf({ tripType, segments, getPassengerNames }) {
  const res = await fetch("/generate-pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      passenger_names: getPassengerNames(),
      trip_type: tripType,
      segments,
    }),
  });
  if (!res.ok) {
    const data = await parseJsonResponse(res);
    throw new Error(data.error || "Could not generate PDF.");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "itinerary.pdf";

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// =====================================================================
// Tabs
// =====================================================================
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("is-active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("is-hidden"));
    btn.classList.add("is-active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove("is-hidden");
  });
});

// =====================================================================
// WhatsApp tab — one click: upload -> extract -> message
// =====================================================================
(() => {
  const state = { files: [], tripType: "One Way" };

  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const thumbs = document.getElementById("thumbs");
  const generateBtn = document.getElementById("generateBtn");
  const uploadError = document.getElementById("uploadError");
  const msgOutput = document.getElementById("msgOutput");
  const msgText = document.getElementById("msgText");
  const copyBtn = document.getElementById("copyBtn");
  const whatsappBtn = document.getElementById("whatsappBtn");

  document.querySelectorAll('input[name="trip_type"]').forEach((el) => {
    el.addEventListener("change", (e) => (state.tripType = e.target.value));
  });

  function refreshThumbs() {
    renderThumbs(thumbs, state.files, refreshThumbs);
    generateBtn.disabled = state.files.length === 0;
  }

  wireDropzone(dropzone, fileInput, (fileList) => {
    state.files.push(...filterImageFiles(fileList, uploadError));
    refreshThumbs();
  });

  generateBtn.addEventListener("click", async () => {
    uploadError.textContent = "";
    msgOutput.classList.add("is-hidden");
    generateBtn.disabled = true;
    generateBtn.textContent = "Reading images…";

    const formData = new FormData();
    formData.append("trip_type", state.tripType);
    state.files.forEach((f) => formData.append("images", f));

    try {
      const res = await fetch("/generate", { method: "POST", body: formData });
      const data = await parseJsonResponse(res);
      if (!res.ok) throw new Error(data.error || "Could not generate message.");

      msgText.value = data.message;
      whatsappBtn.href = `https://wa.me/?text=${encodeURIComponent(data.message)}`;
      msgOutput.classList.remove("is-hidden");
    } catch (err) {
      uploadError.textContent = err.message;
    } finally {
      generateBtn.disabled = state.files.length === 0;
      generateBtn.textContent = "Generate WhatsApp message";
    }
  });

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(msgText.value);
      const original = copyBtn.textContent;
      copyBtn.textContent = "Copied ✓";
      setTimeout(() => (copyBtn.textContent = original), 1500);
    } catch {
      msgText.select();
      document.execCommand("copy");
    }
  });
})();

// =====================================================================
// Screenshot -> PDF tab — upload -> extract -> review/edit -> generate PDF
// =====================================================================
(() => {
  const state = { files: [], tripType: "One Way", segments: [] };

  const dropzone = document.getElementById("pdfDropzone");
  const fileInput = document.getElementById("pdfFileInput");
  const thumbs = document.getElementById("pdfThumbs");
  const extractBtn = document.getElementById("pdfExtractBtn");
  const uploadError = document.getElementById("pdfUploadError");
  const review = document.getElementById("pdfReview");
  const segmentsList = document.getElementById("pdfSegmentsList");
  const generateBtn = document.getElementById("pdfGenerateBtn");
  const generateError = document.getElementById("pdfGenerateError");

  const { getNames: getPassengerNames } = createPassengerList(
    document.getElementById("pdfPassengerList"),
    document.getElementById("pdfAddPassengerBtn")
  );

  document.querySelectorAll('input[name="pdf_trip_type"]').forEach((el) => {
    el.addEventListener("change", (e) => (state.tripType = e.target.value));
  });

  function refreshThumbs() {
    renderThumbs(thumbs, state.files, refreshThumbs);
    extractBtn.disabled = state.files.length === 0;
  }

  wireDropzone(dropzone, fileInput, (fileList) => {
    state.files.push(...filterImageFiles(fileList, uploadError));
    refreshThumbs();
  });

  extractBtn.addEventListener("click", async () => {
    uploadError.textContent = "";
    review.classList.add("is-hidden");
    extractBtn.disabled = true;
    extractBtn.textContent = "Reading images…";

    const formData = new FormData();
    formData.append("trip_type", state.tripType);
    state.files.forEach((f) => formData.append("images", f));

    try {
      const res = await fetch("/extract", { method: "POST", body: formData });
      const data = await parseJsonResponse(res);
      if (!res.ok) throw new Error(data.error || "Extraction failed.");

      state.segments = data.segments;
      renderSegmentCards(segmentsList, state.segments);
      review.classList.remove("is-hidden");
    } catch (err) {
      uploadError.textContent = err.message;
    } finally {
      extractBtn.disabled = state.files.length === 0;
      extractBtn.textContent = "Read flight details";
    }
  });

  generateBtn.addEventListener("click", async () => {
    generateError.textContent = "";
    generateBtn.disabled = true;
    generateBtn.textContent = "Building PDF…";
    try {
      await downloadItineraryPdf({
        tripType: state.tripType,
        segments: state.segments,
        getPassengerNames,
      });
    } catch (err) {
      generateError.textContent = err.message;
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate itinerary PDF";
    }
  });
})();

// =====================================================================
// PDF -> PDF tab — upload booking PDF(s) -> extract -> review/edit -> generate PDF
// =====================================================================
(() => {
  const state = { files: [], tripType: "One Way", segments: [] };

  const dropzone = document.getElementById("pdf2pdfDropzone");
  const fileInput = document.getElementById("pdf2pdfFileInput");
  const fileChips = document.getElementById("pdf2pdfFiles");
  const extractBtn = document.getElementById("pdf2pdfExtractBtn");
  const uploadError = document.getElementById("pdf2pdfUploadError");
  const review = document.getElementById("pdf2pdfReview");
  const segmentsList = document.getElementById("pdf2pdfSegmentsList");
  const generateBtn = document.getElementById("pdf2pdfGenerateBtn");
  const generateError = document.getElementById("pdf2pdfGenerateError");

  const { getNames: getPassengerNames } = createPassengerList(
    document.getElementById("pdf2pdfPassengerList"),
    document.getElementById("pdf2pdfAddPassengerBtn")
  );

  document.querySelectorAll('input[name="pdf2pdf_trip_type"]').forEach((el) => {
    el.addEventListener("change", (e) => (state.tripType = e.target.value));
  });

  function refreshChips() {
    renderFileChips(fileChips, state.files, refreshChips);
    extractBtn.disabled = state.files.length === 0;
  }

  wireDropzone(dropzone, fileInput, (fileList) => {
    state.files.push(...filterPdfFiles(fileList, uploadError));
    refreshChips();
  });

  extractBtn.addEventListener("click", async () => {
    uploadError.textContent = "";
    review.classList.add("is-hidden");
    extractBtn.disabled = true;
    extractBtn.textContent = "Reading PDFs…";

    const formData = new FormData();
    formData.append("trip_type", state.tripType);
    state.files.forEach((f) => formData.append("pdfs", f));

    try {
      const res = await fetch("/extract-pdf", { method: "POST", body: formData });
      const data = await parseJsonResponse(res);
      if (!res.ok) throw new Error(data.error || "Extraction failed.");

      state.segments = data.segments;
      renderSegmentCards(segmentsList, state.segments);
      review.classList.remove("is-hidden");
    } catch (err) {
      uploadError.textContent = err.message;
    } finally {
      extractBtn.disabled = state.files.length === 0;
      extractBtn.textContent = "Read flight details";
    }
  });

  generateBtn.addEventListener("click", async () => {
    generateError.textContent = "";
    generateBtn.disabled = true;
    generateBtn.textContent = "Building PDF…";
    try {
      await downloadItineraryPdf({
        tripType: state.tripType,
        segments: state.segments,
        getPassengerNames,
      });
    } catch (err) {
      generateError.textContent = err.message;
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate itinerary PDF";
    }
  });
})();
