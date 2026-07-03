const state = {
  files: [],
  tripType: "One Way",
  segments: [],
};

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

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const thumbs = document.getElementById("thumbs");
const extractBtn = document.getElementById("extractBtn");
const uploadError = document.getElementById("uploadError");

const panelUpload = document.getElementById("panel-upload");
const panelReview = document.getElementById("panel-review");
const panelGenerate = document.getElementById("panel-generate");
const stepsEl = document.getElementById("steps");

function setStep(n) {
  [...stepsEl.children].forEach((li) => {
    const s = Number(li.dataset.step);
    li.classList.toggle("is-active", s === n);
    li.classList.toggle("is-done", s < n);
  });
  panelUpload.classList.toggle("is-hidden", n !== 1);
  panelReview.classList.toggle("is-hidden", n !== 2);
  panelGenerate.classList.toggle("is-hidden", n !== 3);
}

// ---- Trip type ----
document.querySelectorAll('input[name="trip_type"]').forEach((el) => {
  el.addEventListener("change", (e) => (state.tripType = e.target.value));
});

// ---- File handling ----
// Note: dropzone is a <label for="fileInput">, so clicking it already opens
// the file picker natively — no extra JS click handler needed here (adding
// one caused the picker to double-fire and reopen on mobile).
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("is-dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("is-dragover");
  addFiles(e.dataTransfer.files);
});
fileInput.addEventListener("change", (e) => addFiles(e.target.files));

function addFiles(fileList) {
  [...fileList].forEach((f) => {
    if (/^image\/(png|jpe?g|webp)$/.test(f.type)) state.files.push(f);
  });
  renderThumbs();
}

function renderThumbs() {
  thumbs.innerHTML = "";
  state.files.forEach((f, i) => {
    const div = document.createElement("div");
    div.className = "thumb";
    const img = document.createElement("img");
    img.src = URL.createObjectURL(f);
    const btn = document.createElement("button");
    btn.className = "thumb__remove";
    btn.textContent = "✕";
    btn.onclick = (e) => {
      e.stopPropagation();
      state.files.splice(i, 1);
      renderThumbs();
    };
    div.appendChild(img);
    div.appendChild(btn);
    thumbs.appendChild(div);
  });
  extractBtn.disabled = state.files.length === 0;
}

// ---- Step 1 -> Extract ----
extractBtn.addEventListener("click", async () => {
  uploadError.textContent = "";
  extractBtn.disabled = true;
  extractBtn.textContent = "Reading images…";

  const formData = new FormData();
  formData.append("trip_type", state.tripType);
  state.files.forEach((f) => formData.append("images", f));

  try {
    const res = await fetch("/extract", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Extraction failed.");
    if (!data.segments || data.segments.length === 0) {
      throw new Error("No flight details could be read from those images. Try clearer screenshots.");
    }
    state.segments = data.segments;
    renderSegments();
    setStep(2);
  } catch (err) {
    uploadError.textContent = err.message;
  } finally {
    extractBtn.disabled = state.files.length === 0;
    extractBtn.textContent = "Read flight details";
  }
});

// ---- Step 2: Review ----
const segmentsList = document.getElementById("segmentsList");

function renderSegments() {
  segmentsList.innerHTML = "";
  state.segments.forEach((seg, idx) => {
    const card = document.createElement("div");
    card.className = "seg-card";

    const head = document.createElement("div");
    head.className = "seg-card__head";
    head.innerHTML = `
      <span class="seg-card__route">${seg.departure_airport_code || "---"} → ${seg.arrival_airport_code || "---"}</span>
      <span class="seg-card__idx">Leg ${idx + 1} of ${state.segments.length}</span>
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
        state.segments[idx][key] = e.target.value;
        if (key === "departure_airport_code" || key === "arrival_airport_code") {
          head.querySelector(".seg-card__route").textContent =
            `${state.segments[idx].departure_airport_code || "---"} → ${state.segments[idx].arrival_airport_code || "---"}`;
        }
      });
      field.appendChild(input);
      grid.appendChild(field);
    });
    card.appendChild(grid);
    segmentsList.appendChild(card);
  });
}

document.getElementById("backToUpload").addEventListener("click", () => setStep(1));
document.getElementById("toNameBtn").addEventListener("click", () => setStep(3));
document.getElementById("backToReview").addEventListener("click", () => {
  document.getElementById("msgOutput").classList.add("is-hidden");
  setStep(2);
});

// ---- Step 3: Generate ----
const passengerName = document.getElementById("passengerName");
const generateBtn = document.getElementById("generateBtn");
const generateError = document.getElementById("generateError");
const msgOutput = document.getElementById("msgOutput");
const msgText = document.getElementById("msgText");
const copyBtn = document.getElementById("copyBtn");
const whatsappBtn = document.getElementById("whatsappBtn");

generateBtn.addEventListener("click", async () => {
  generateError.textContent = "";
  const name = passengerName.value.trim();
  if (!name) {
    generateError.textContent = "Enter the passenger's name.";
    return;
  }

  generateBtn.disabled = true;
  generateBtn.textContent = "Building message…";

  try {
    const res = await fetch("/generate-text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        passenger_name: name,
        trip_type: state.tripType,
        segments: state.segments,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not generate message.");

    msgText.value = data.message;
    whatsappBtn.href = `https://wa.me/?text=${encodeURIComponent(data.message)}`;
    msgOutput.classList.remove("is-hidden");
  } catch (err) {
    generateError.textContent = err.message;
  } finally {
    generateBtn.disabled = false;
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
