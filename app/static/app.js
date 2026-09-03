let templateFile = null;
let parsedSoal = null;

function el(id) {
  return document.getElementById(id);
}

async function loadDefaults() {
  try {
    const res = await fetch("/api/defaults");
    const data = await res.json();
    el("nama").value = data.nama || "";
    el("npm").value = data.npm || "";
    el("kode_aslab").value = data.kode_aslab || "";
    el("tipe").value = data.tipe || "TP";
  } catch (err) {
    console.warn("Gagal memuat default:", err);
  }
}

function currentIdentity() {
  return {
    nama: el("nama").value.trim(),
    npm: el("npm").value.trim(),
    kode_aslab: el("kode_aslab").value.trim(),
    no_modul: el("no_modul").value.trim(),
    tipe: el("tipe").value,
  };
}

async function fetchClassify(questionText) {
  const form = new FormData();
  form.append("question_text", questionText);
  const res = await fetch("/api/classify", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Gagal mengklasifikasi soal");
  }
  return res.json();
}

// Runs Gemini's soal/perintah classifier on the raw parsed question text and
// updates the item's UI in place. This is the prompt-injection safeguard: the
// raw text (which may contain embedded instructions, as already found in one
// module's soal) is never used for AI reference/step lookups directly -- only
// the classifier's cleaned "soal" text is, once available. Any detected
// injected commands are surfaced to the student instead of silently dropped.
async function classifyItem(itemDiv, rawText) {
  itemDiv.dataset.cleanText = rawText; // safe default until classification finishes
  const statusEl = itemDiv.querySelector(".classify-status");
  const warningEl = itemDiv.querySelector(".injection-warning");
  statusEl.textContent = "Memeriksa soal dengan AI (deteksi prompt injection)...";
  try {
    const result = await fetchClassify(rawText);
    const cleanSoal = (result.soal || "").trim() || rawText;
    itemDiv.dataset.cleanText = cleanSoal;
    itemDiv.querySelector(".question-text").textContent = cleanSoal;
    const detected = result.perintah_terdeteksi || [];
    if (detected.length > 0) {
      warningEl.hidden = false;
      warningEl.innerHTML =
        "<strong>Terdeteksi kemungkinan prompt injection di file soal asli &mdash; disembunyikan dari tampilan pertanyaan:</strong>";
      const ul = document.createElement("ul");
      detected.forEach((line) => {
        const li = document.createElement("li");
        li.textContent = line;
        ul.appendChild(li);
      });
      warningEl.appendChild(ul);
      statusEl.textContent = "Diperiksa AI: bagian mencurigakan ditemukan dan dipisahkan (lihat di atas).";
    } else {
      statusEl.textContent = "Diperiksa AI: tidak ada indikasi prompt injection.";
    }
  } catch (err) {
    statusEl.textContent = `Pemeriksaan AI tidak tersedia (${err.message}). Menampilkan teks soal asli apa adanya -- periksa manual jika ada kalimat mencurigakan. `;
    const retryBtn = document.createElement("button");
    retryBtn.type = "button";
    retryBtn.textContent = "Coba lagi";
    retryBtn.className = "retry-classify-btn";
    retryBtn.addEventListener("click", () => classifyItem(itemDiv, rawText), { once: true });
    statusEl.appendChild(retryBtn);
  }
}

function buildItem(partNumber, item, opts) {
  const tmpl = el("question-item-template").content.cloneNode(true);
  const itemDiv = tmpl.querySelector(".item");
  itemDiv.dataset.part = partNumber;
  itemDiv.dataset.number = item.number;
  itemDiv.dataset.cleanText = item.text;

  tmpl.querySelector("h3").textContent = `Soal ${item.number}`;
  tmpl.querySelector(".question-text").textContent = item.text;

  if (opts.showSteps) {
    const stepsBlock = tmpl.querySelector(".steps-block");
    stepsBlock.hidden = false;
    stepsBlock.querySelector(".steps_btn").addEventListener("click", async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Mencari...";
      try {
        const steps = await fetchSteps(itemDiv.dataset.cleanText);
        stepsBlock.querySelector(".steps-area").value = steps.join("\n");
      } catch (err) {
        alert(err.message);
      } finally {
        e.target.disabled = false;
        e.target.textContent = "Cari Langkah (AI)";
      }
    });
  }

  if (opts.showScreenshot) {
    tmpl.querySelector(".screenshot-block").hidden = false;
  }

  if (opts.showQuotes) {
    const quotesBlock = tmpl.querySelector(".quotes-block");
    quotesBlock.hidden = false;
    quotesBlock.querySelector(".quotes_btn").addEventListener("click", async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Mencari...";
      try {
        const quotes = await fetchQuotes(itemDiv.dataset.cleanText);
        applyQuotes(itemDiv, quotes);
      } catch (err) {
        alert(err.message);
      } finally {
        e.target.disabled = false;
        e.target.textContent = "Cari Kutipan (AI)";
      }
    });
  }

  itemDiv.querySelector(".classify-status").textContent = "Menunggu giliran pemeriksaan AI...";

  return tmpl;
}

// Prefills the answer textarea with each quote (quoted, tagged with its source
// number) and renders one checkbox per source below it. The student is meant to
// edit the textarea down into their own words -- the quotes are never sent to
// the backend as-is, only whatever text remains in the textarea at generate time.
function applyQuotes(itemDiv, quotes) {
  if (!quotes.length) {
    alert("Tidak ada kutipan yang ditemukan. Coba lagi atau cari referensi secara manual.");
    return;
  }
  const answerArea = itemDiv.querySelector(".answer-area");
  const prefill = quotes
    .map((q, i) => `"${q.quote}" [Sumber ${i + 1}]`)
    .join("\n\n");
  if (answerArea.value.trim()) {
    const replace = confirm(
      "Kotak jawaban sudah berisi teks. Timpa dengan kutipan baru? (Klik Batal untuk membiarkan teks yang sudah ada.)"
    );
    if (!replace) return;
  }
  answerArea.value = prefill;
  itemDiv.querySelector(".quote-warning").hidden = false;

  const sourcesBlock = itemDiv.querySelector(".sources-block");
  const list = itemDiv.querySelector(".sources-list");
  list.innerHTML = "";
  quotes.forEach((q, i) => {
    const li = document.createElement("li");
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.dataset.source = q.source;
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(` [Sumber ${i + 1}] ${q.source}`));
    li.appendChild(label);
    list.appendChild(li);
  });
  sourcesBlock.hidden = false;
}

// Gemini's free tier allows only 5 requests/minute, and this app can have
// many items to auto-classify right after parsing. Firing them all at once
// reliably triggers a 429 (seen in practice), so they are run one at a time
// instead -- slower, but it actually completes instead of erroring out.
async function runClassificationQueue(entries) {
  for (const { itemDiv, rawText } of entries) {
    await classifyItem(itemDiv, rawText);
  }
}

async function fetchQuotes(questionText) {
  const form = new FormData();
  form.append("question_text", questionText);
  const res = await fetch("/api/quotes", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Gagal mencari kutipan");
  }
  const data = await res.json();
  return data.quotes || [];
}

async function fetchSteps(questionText) {
  const form = new FormData();
  form.append("question_text", questionText);
  const res = await fetch("/api/steps", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Gagal mencari langkah");
  }
  const data = await res.json();
  return data.steps || [];
}

function renderParsed(data) {
  parsedSoal = data;

  const preambleSection = el("preamble_section");
  const preambleList = el("preamble_list");
  preambleList.innerHTML = "";
  (data.preamble || []).forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    preambleList.appendChild(li);
  });
  preambleSection.hidden = (data.preamble || []).length === 0;

  const part1 = data.parts["1"];
  const part1Container = el("part1_items");
  part1Container.innerHTML = "";
  if (part1 && part1.items.length) {
    part1.items.forEach((item) => {
      part1Container.appendChild(
        buildItem("1", item, { showSteps: false, showScreenshot: false, showQuotes: true })
      );
    });
    el("part1_section").hidden = false;
  }

  const part2 = data.parts["2"];
  const part2Container = el("part2_items");
  part2Container.innerHTML = "";
  if (part2 && part2.items.length) {
    part2.items.forEach((item) => {
      part2Container.appendChild(buildItem("2", item, { showSteps: true, showScreenshot: true }));
    });
    el("part2_section").hidden = false;
  }

  el("generate_section").hidden = false;

  const entries = Array.from(document.querySelectorAll(".item")).map((itemDiv) => ({
    itemDiv,
    rawText: itemDiv.dataset.cleanText,
  }));
  runClassificationQueue(entries);
}

el("parse_btn").addEventListener("click", async () => {
  const fileInput = el("soal_file");
  if (!fileInput.files.length) {
    el("parse_status").textContent = "Pilih file soal .docx terlebih dahulu.";
    return;
  }
  const templateInput = el("template_file");
  templateFile = templateInput.files.length ? templateInput.files[0] : null;

  el("parse_status").textContent = "Membaca soal...";
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  try {
    const res = await fetch("/api/parse-soal", { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Gagal membaca soal");
    }
    const data = await res.json();
    renderParsed(data);
    el("parse_status").textContent = "Soal berhasil dibaca.";
  } catch (err) {
    el("parse_status").textContent = err.message;
  }
});

function collectPartsAnswers() {
  const result = { "1": [], "2": [] };
  document.querySelectorAll(".item").forEach((itemDiv) => {
    const part = itemDiv.dataset.part;
    const number = parseInt(itemDiv.dataset.number, 10);
    const answer = itemDiv.querySelector(".answer-area").value;
    const references = Array.from(
      itemDiv.querySelectorAll(".sources-list input[type=checkbox]:checked")
    ).map((cb) => cb.dataset.source);
    result[part].push({ number, answer, references });
  });
  return result;
}

function collectScreenshots() {
  const files = [];
  document.querySelectorAll(".item").forEach((itemDiv) => {
    const part = itemDiv.dataset.part;
    const number = itemDiv.dataset.number;
    const input = itemDiv.querySelector(".screenshot-input");
    if (!input) return;
    Array.from(input.files).forEach((file) => {
      const renamed = new File([file], `${part}-${number}__${file.name}`, { type: file.type });
      files.push(renamed);
    });
  });
  return files;
}

el("generate_btn").addEventListener("click", async () => {
  if (!parsedSoal) {
    el("generate_status").textContent = "Baca soal terlebih dahulu.";
    return;
  }
  const identity = currentIdentity();
  if (!identity.nama || !identity.npm || !identity.no_modul) {
    el("generate_status").textContent = "Isi Nama, NPM, dan No. Modul terlebih dahulu.";
    return;
  }

  el("generate_status").textContent = "Membuat dokumen...";
  const form = new FormData();
  form.append("identity", JSON.stringify(identity));
  form.append("parts_answers", JSON.stringify(collectPartsAnswers()));
  if (templateFile) {
    form.append("template_file", templateFile);
  }
  collectScreenshots().forEach((file) => form.append("screenshots", file));

  try {
    const res = await fetch("/api/generate", { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Gagal membuat dokumen");
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="(.+)"/);
    const filename = match ? match[1] : "jawaban.docx";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    el("generate_status").textContent = "Dokumen berhasil dibuat dan diunduh.";
  } catch (err) {
    el("generate_status").textContent = err.message;
  }
});

loadDefaults();
