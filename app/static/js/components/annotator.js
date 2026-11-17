/**
 * Multimodal Annotator Component (DashCode Ergonomic Edition)
 * High-performance human ground-truth annotation for Devanagari OCR & CLIP/VLM captions.
 *
 * Capabilities:
 * - Document stage awareness: Pending Annotation, AI Requested, AI Drafts (Review), Certified Approved
 * - Strict object-contain image preview without distortion
 * - Priority queueing for AI Agent / MCP processing
 * - Devanagari Quick-Pad (Numerals ०-९ and complex ligatures)
 * - Font Size Scaler (A- / A+) for Devanagari text readability
 * - Zero-latency background pre-fetching (0ms transitions)
 * - Local draft persistence (localStorage) preventing work loss
 * - Web Audio API audio feedback & Mobile Haptics
 * - Mobile Touch Swipe navigation
 */
const AnnotatorComponent = {
  currentImage: null,
  currentStage: "unannotated", // unannotated | ai_requested | ai_pending | approved
  historyIds: [],
  historyIndex: -1,
  knownCategories: new Set(),
  lastAiResult: null,

  // Document canvas transformation state
  currentRotation: 0,
  filterContrast: false,
  filterGrayscale: false,
  filterInvert: false,

  // Font size scaler index: 12px, 14px, 16px, 18px, 20px
  fontSizes: ["12px", "14px", "16px", "18px", "20px"],
  fontSizeIdx: 1,

  // Audio feedback state
  audioEnabled: true,
  audioCtx: null,

  // Zero-latency pre-fetch cache
  prefetchedImages: [],

  // Rapid snippet lexicon
  snippets: {
    citizenship: {
      category: "citizenship",
      caption: "नेपाल सरकार जिल्ला प्रशासन कार्यालयद्वारा जारी गरिएको नेपाली नागरिकताको प्रमाण-पत्र",
    },
    lalpurja: {
      category: "lalpurja",
      caption: "नेपाल सरकार भूमि व्यवस्था तथा मालपोत कार्यालयद्वारा जारी जग्गाधनी दर्ता प्रमाणपूर्जा (लालपुर्जा)",
    },
    gazette: {
      category: "gazette",
      caption: "नेपाल सरकार मुद्रण विभागद्वारा प्रकाशित नेपाल राजपत्रको आधिकारिक सूचना पृष्ठ",
    },
    license: {
      category: "license",
      caption: "यातायात व्यवस्था विभागद्वारा जारी गरिएको सवारी चालक अनुमतिपत्र (स्मार्ट लाइसेन्स)",
    },
    passport: {
      category: "passport",
      caption: "नेपाल सरकार परराष्ट्र मन्त्रालय राहदानी विभागद्वारा जारी विद्युतीय राहदानी (ई-पासपोर्ट)",
    },
    receipt: {
      category: "receipt",
      caption: "आन्तरिक राजस्व कार्यालय वा भन्सार कार्यालयद्वारा जारी आधिकारिक राजस्व दाखिला रसिद",
    },
    certificate: {
      category: "certificate",
      caption: "आधिकारिक निकाय वा शैक्षिक संस्थाद्वारा जारी गरिएको शैक्षिक प्रमाण-पत्र तथा लब्धाङ्क पत्र",
    },
    notice: {
      category: "letter",
      caption: "नेपाल सरकार मन्त्रालय वा विभागद्वारा जारी गरिएको आधिकारिक सूचना, परिपत्र तथा आदेश",
    },
  },

  init() {
    this.bindKeyboardShortcuts();
    this.bindTouchSwipes();
    this.bindDraftAutoSave();
    this.loadCategories();
    this.refreshStageCounts();
    this.loadNext();
  },

  async loadCategories() {
    try {
      const data = await API.getCategories();
      const datalist = document.getElementById("doc-types-list");
      if (!datalist) return;
      datalist.innerHTML = "";
      data.categories.forEach((cat) => {
        this.knownCategories.add(cat);
        const opt = document.createElement("option");
        opt.value = cat;
        datalist.appendChild(opt);
      });
    } catch (e) {
      console.error(e);
    }
  },

  setStage(stage) {
    this.currentStage = stage;

    // Update Stage Tab Styles
    ["unannotated", "ai_requested", "ai_pending", "approved"].forEach((st) => {
      const btn = document.getElementById(`stage-tab-${st}`);
      if (btn) {
        if (st === stage) {
          btn.className = "px-3 py-1.5 rounded-lg bg-white text-slate-900 shadow-2xs flex items-center gap-1.5 transition-all";
        } else {
          btn.className = "px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 flex items-center gap-1.5 transition-all";
        }
      }
    });

    this.currentImage = null;
    this.historyIds = [];
    this.historyIndex = -1;
    this.loadNext();
    this.refreshStageCounts();
  },

  async refreshStageCounts() {
    try {
      const [u, r, p, a] = await Promise.all([
        API.getImages({ stage: "unannotated", limit: 1 }),
        API.getImages({ stage: "ai_requested", limit: 1 }),
        API.getImages({ stage: "ai_pending", limit: 1 }),
        API.getImages({ stage: "approved", limit: 1 }),
      ]);

      const elU = document.getElementById("stage-count-unannotated");
      const elR = document.getElementById("stage-count-ai_requested");
      const elP = document.getElementById("stage-count-ai_pending");
      const elA = document.getElementById("stage-count-approved");

      if (elU) elU.innerText = u.total;
      if (elR) elR.innerText = r.total;
      if (elP) elP.innerText = p.total;
      if (elA) elA.innerText = a.total;

      const sbBadge = document.getElementById("sb-annotate-pending-badge");
      if (sbBadge) sbBadge.innerText = `${u.total} left`;
    } catch (e) {
      // quiet
    }
  },

  bindKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
      const isTyping = ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName);
      if (isTyping) {
        if ((e.altKey || e.metaKey) && e.key.toLowerCase() === "s") {
          e.preventDefault();
          this.saveHumanAnnotation();
        }
        return;
      }

      const key = e.key.toLowerCase();
      if ((e.altKey || e.metaKey) && key === "s") {
        e.preventDefault();
        this.saveHumanAnnotation();
      } else if ((e.altKey || e.metaKey) && key === "n") {
        e.preventDefault();
        this.loadNext();
      } else if ((e.altKey || e.metaKey) && key === "p") {
        e.preventDefault();
        this.loadPrevious();
      } else if ((e.altKey || e.metaKey) && key === "d") {
        e.preventDefault();
        this.skipCurrent();
      } else if ((e.altKey || e.metaKey) && key === "z") {
        e.preventDefault();
        this.toggleZoomModal();
      } else if ((e.altKey || e.metaKey) && key === "r") {
        e.preventDefault();
        this.rotateRight();
      }
    });
  },

  bindTouchSwipes() {
    let touchStartX = 0;
    let touchEndX = 0;
    const canvas = document.getElementById("anno-main-image");
    if (!canvas) return;

    canvas.addEventListener("touchstart", (e) => {
      touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });

    canvas.addEventListener("touchend", (e) => {
      touchEndX = e.changedTouches[0].screenX;
      const diff = touchEndX - touchStartX;
      if (Math.abs(diff) > 60) {
        if (diff < 0) {
          // Swipe Left -> Next
          this.loadNext();
        } else {
          // Swipe Right -> Prev
          this.loadPrevious();
        }
      }
    }, { passive: true });
  },

  bindDraftAutoSave() {
    const fields = ["anno-ocr-text", "anno-caption-ne", "anno-caption-en", "anno-doc-type", "anno-tags"];
    fields.forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("input", () => this.saveLocalDraft());
      }
    });
  },

  saveLocalDraft() {
    if (!this.currentImage) return;
    const draft = {
      ocr_text: document.getElementById("anno-ocr-text")?.value || "",
      caption_nepali: document.getElementById("anno-caption-ne")?.value || "",
      caption_english: document.getElementById("anno-caption-en")?.value || "",
      document_type: document.getElementById("anno-doc-type")?.value || "",
      tags: document.getElementById("anno-tags")?.value || "",
      updatedAt: Date.now(),
    };
    try {
      localStorage.setItem(`open_nepali_draft_${this.currentImage.id}`, JSON.stringify(draft));
      const statusEl = document.getElementById("anno-draft-status");
      if (statusEl) {
        statusEl.innerHTML = `<i data-lucide="check" class="w-3 h-3 text-emerald-500"></i> Draft saved`;
        lucide.createIcons();
      }
    } catch (e) {}
  },

  restoreLocalDraft(imgId) {
    try {
      const raw = localStorage.getItem(`open_nepali_draft_${imgId}`);
      if (!raw) return false;
      const draft = JSON.parse(raw);
      if (draft && (draft.ocr_text || draft.caption_nepali || draft.document_type)) {
        if (draft.ocr_text) document.getElementById("anno-ocr-text").value = draft.ocr_text;
        if (draft.caption_nepali) document.getElementById("anno-caption-ne").value = draft.caption_nepali;
        if (draft.caption_english) document.getElementById("anno-caption-en").value = draft.caption_english;
        if (draft.document_type) document.getElementById("anno-doc-type").value = draft.document_type;
        if (draft.tags) document.getElementById("anno-tags").value = draft.tags;

        const statusEl = document.getElementById("anno-draft-status");
        if (statusEl) {
          statusEl.innerHTML = `<i data-lucide="refresh-cw" class="w-3 h-3 text-indigo-500"></i> Restored draft`;
          lucide.createIcons();
        }
        return true;
      }
    } catch (e) {}
    return false;
  },

  clearLocalDraft(imgId) {
    try {
      localStorage.removeItem(`open_nepali_draft_${imgId}`);
    } catch (e) {}
  },

  // Audio & Haptic Feedback
  playTone(type = "success") {
    if (!this.audioEnabled) return;
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!this.audioCtx) this.audioCtx = new AudioContext();
      const ctx = this.audioCtx;
      if (ctx.state === "suspended") ctx.resume();

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      if (type === "success") {
        osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
        osc.frequency.exponentialRampToValueAtTime(880.00, ctx.currentTime + 0.12); // A5
        gain.gain.setValueAtTime(0.08, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
        osc.start();
        osc.stop(ctx.currentTime + 0.18);
      } else {
        osc.frequency.setValueAtTime(320.00, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(200.00, ctx.currentTime + 0.14);
        gain.gain.setValueAtTime(0.08, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.16);
        osc.start();
        osc.stop(ctx.currentTime + 0.16);
      }
    } catch (e) {}
  },

  toggleAudioChime() {
    this.audioEnabled = !this.audioEnabled;
    const btn = document.getElementById("btn-audio-chime");
    if (btn) {
      btn.innerHTML = `<i data-lucide="${this.audioEnabled ? 'volume-2' : 'volume-x'}" class="w-3.5 h-3.5"></i>`;
      btn.className = `p-1.5 rounded-lg transition-colors ${this.audioEnabled ? 'bg-indigo-50 text-indigo-700' : 'bg-slate-100 text-slate-400'}`;
      lucide.createIcons();
    }
    App.toast(`Audio feedback ${this.audioEnabled ? 'enabled' : 'muted'}`, "info");
  },

  vibrate(ms = 40) {
    if (navigator.vibrate) {
      try { navigator.vibrate(ms); } catch (e) {}
    }
  },

  // Devanagari Quick-Pad Inserter
  insertChar(ch) {
    const ocrTextarea = document.getElementById("anno-ocr-text");
    if (!ocrTextarea) return;

    const start = ocrTextarea.selectionStart;
    const end = ocrTextarea.selectionEnd;
    const val = ocrTextarea.value;

    ocrTextarea.value = val.substring(0, start) + ch + val.substring(end);
    ocrTextarea.focus();
    ocrTextarea.selectionStart = ocrTextarea.selectionEnd = start + ch.length;
    this.saveLocalDraft();
  },

  adjustFontSize(delta) {
    this.fontSizeIdx = Math.max(0, Math.min(this.fontSizes.length - 1, this.fontSizeIdx + delta));
    const size = this.fontSizes[this.fontSizeIdx];
    const ocrTextarea = document.getElementById("anno-ocr-text");
    if (ocrTextarea) {
      ocrTextarea.style.fontSize = size;
      App.toast(`Devanagari text size: ${size}`, "info");
    }
  },

  // Navigation: Next / Previous
  async loadNext() {
    const currId = this.currentImage ? this.currentImage.id : null;
    try {
      const res = await API.getNextUnannotatedDocument(currId, this.currentStage, "next");
      if (res && res.item) {
        this.renderImage(res.item);
        this.preFetchNext(res.item.id);
      } else {
        this.renderEmpty();
      }
    } catch (e) {
      console.error(e);
      this.renderEmpty();
    }
  },

  async loadPrevious() {
    const currId = this.currentImage ? this.currentImage.id : null;
    try {
      const res = await API.getNextUnannotatedDocument(currId, this.currentStage, "prev");
      if (res && res.item) {
        this.renderImage(res.item);
      } else {
        App.toast("No previous documents in this stage", "info");
      }
    } catch (e) {
      console.error(e);
    }
  },

  async loadImage(id) {
    try {
      const img = await API.getImage(id);
      this.renderImage(img);
      this.preFetchNext(img.id);
    } catch (err) {
      App.toast(`Failed to load image #${id}: ${err.message}`, "error");
    }
  },

  async preFetchNext(currId) {
    try {
      const res = await API.getNextUnannotatedDocument(currId, this.currentStage, "next");
      if (res && res.item) {
        const link = document.createElement("link");
        link.rel = "prefetch";
        link.as = "image";
        link.href = `/api/images/${res.item.id}/file`;
        document.head.appendChild(link);
      }
    } catch (e) {}
  },

  renderImage(img) {
    this.currentImage = img;
    this.resetFilters();

    // Update Header Pills
    document.getElementById("anno-img-id").innerText = `ID: #${img.id}`;
    document.getElementById("anno-img-dims").innerText = `${img.width} × ${img.height}`;
    document.getElementById("anno-img-fmt").innerText = (img.format || "WEBP").toUpperCase();
    document.getElementById("anno-img-status").innerText = img.is_approved ? "Approved" : "Ready";

    const aiBadge = document.getElementById("anno-ai-badge");
    if (aiBadge) {
      aiBadge.classList.toggle("hidden", !img.ai_requested);
    }

    // Set Image Sources
    const imgEl = document.getElementById("anno-main-image");
    const emptyEl = document.getElementById("anno-img-empty");
    const zoomImg = document.getElementById("modal-img-el") || document.getElementById("zoom-modal-img");

    if (imgEl) {
      imgEl.src = `/api/images/${img.id}/file`;
      imgEl.classList.remove("hidden");
    }
    if (zoomImg) zoomImg.src = `/api/images/${img.id}/file`;
    if (emptyEl) emptyEl.classList.add("hidden");

    // Populate Form Fields
    document.getElementById("anno-ocr-text").value = img.ocr_text || "";
    document.getElementById("anno-caption-ne").value = img.caption_nepali || "";
    document.getElementById("anno-caption-en").value = img.caption_english || "";
    document.getElementById("anno-doc-type").value = img.document_type || "";
    document.getElementById("anno-tags").value = (img.tags || []).join(", ");

    // Check Local Draft
    this.restoreLocalDraft(img.id);

    // AI Output Box
    const aiBox = document.getElementById("anno-ai-output");
    const aiStatus = document.getElementById("anno-ai-status");
    if (aiBox) {
      aiBox.value = img.ai_output || (img.ai_requested ? "⏳ Queued for AI Agent / MCP with Priority 1." : "");
    }
    if (aiStatus) {
      aiStatus.innerText = img.ai_requested ? "Queued for Antigravity / MCP Agent" : "Click Queue for AI to assign";
    }

    lucide.createIcons();
  },

  renderEmpty() {
    this.currentImage = null;
    const imgEl = document.getElementById("anno-main-image");
    const emptyEl = document.getElementById("anno-img-empty");
    if (imgEl) imgEl.classList.add("hidden");
    if (emptyEl) emptyEl.classList.remove("hidden");

    document.getElementById("anno-img-id").innerText = "ID: --";
    document.getElementById("anno-img-dims").innerText = "-- × --";
    document.getElementById("anno-ocr-text").value = "";
    document.getElementById("anno-caption-ne").value = "";
    document.getElementById("anno-caption-en").value = "";
    document.getElementById("anno-doc-type").value = "";
    document.getElementById("anno-tags").value = "";
  },

  // Document Inspection Filters & 90° Rotation
  rotateRight() {
    this.currentRotation = (this.currentRotation + 90) % 360;
    this.applyCanvasTransform();
  },

  rotateLeft() {
    this.currentRotation = (this.currentRotation - 90 + 360) % 360;
    this.applyCanvasTransform();
  },

  toggleContrast() {
    this.filterContrast = !this.filterContrast;
    this.applyCanvasTransform();
    document.getElementById("btn-filter-contrast")?.classList.toggle("bg-slate-300", this.filterContrast);
  },

  toggleGrayscale() {
    this.filterGrayscale = !this.filterGrayscale;
    this.applyCanvasTransform();
    document.getElementById("btn-filter-grayscale")?.classList.toggle("bg-slate-300", this.filterGrayscale);
  },

  toggleInvert() {
    this.filterInvert = !this.filterInvert;
    this.applyCanvasTransform();
    document.getElementById("btn-filter-invert")?.classList.toggle("bg-slate-300", this.filterInvert);
  },

  resetFilters() {
    this.currentRotation = 0;
    this.filterContrast = false;
    this.filterGrayscale = false;
    this.filterInvert = false;
    document.getElementById("btn-filter-contrast")?.classList.remove("bg-slate-300");
    document.getElementById("btn-filter-grayscale")?.classList.remove("bg-slate-300");
    document.getElementById("btn-filter-invert")?.classList.remove("bg-slate-300");
    this.applyCanvasTransform();
  },

  applyCanvasTransform() {
    const imgEl = document.getElementById("anno-main-image");
    const zoomImg = document.getElementById("modal-img-el") || document.getElementById("zoom-modal-img");
    let filterStr = "";
    if (this.filterContrast) filterStr += "contrast(180%) ";
    if (this.filterGrayscale) filterStr += "grayscale(100%) ";
    if (this.filterInvert) filterStr += "invert(100%) ";

    const transformStr = `rotate(${this.currentRotation}deg)`;
    if (imgEl) {
      imgEl.style.filter = filterStr.trim();
      imgEl.style.transform = transformStr;
    }
    if (zoomImg) {
      zoomImg.style.filter = filterStr.trim();
      zoomImg.style.transform = transformStr;
    }
  },

  // Rapid Snippet Pills
  applySnippet(type) {
    const s = this.snippets[type];
    if (!s) return;
    const docTypeInput = document.getElementById("anno-doc-type");
    const captionNeInput = document.getElementById("anno-caption-ne");
    if (docTypeInput) docTypeInput.value = s.category;
    if (captionNeInput) captionNeInput.value = s.caption;
    this.saveLocalDraft();
    App.toast(`Applied ${type} category & caption!`, "info");
  },

  insertPhrase(phrase) {
    const ocrTextarea = document.getElementById("anno-ocr-text");
    if (!ocrTextarea) return;
    const start = ocrTextarea.selectionStart;
    const end = ocrTextarea.selectionEnd;
    const text = ocrTextarea.value;
    ocrTextarea.value = text.substring(0, start) + phrase + text.substring(end);
    ocrTextarea.focus();
    ocrTextarea.selectionStart = ocrTextarea.selectionEnd = start + phrase.length;
    this.saveLocalDraft();
  },

  // Save Human Annotation
  async saveAnnotation() {
    return await this.saveHumanAnnotation();
  },

  async saveHumanAnnotation() {
    if (!this.currentImage) return;

    const ocr = document.getElementById("anno-ocr-text").value.trim();
    const capNe = document.getElementById("anno-caption-ne").value.trim();
    const capEn = document.getElementById("anno-caption-en").value.trim();
    const docType = document.getElementById("anno-doc-type").value.trim();
    const aiOut = document.getElementById("anno-ai-output")?.value.trim() || null;
    const tags = document.getElementById("anno-tags").value
      .split(",")
      .map(t => t.trim())
      .filter(Boolean);

    try {
      await API.annotateImage(this.currentImage.id, {
        ocr_text: ocr,
        caption_nepali: capNe,
        caption_english: capEn,
        document_type: docType || "other",
        tags: tags,
        ai_output: aiOut,
        annotation_text: capNe || ocr,
        has_text: Boolean(ocr),
      });

      this.clearLocalDraft(this.currentImage.id);
      this.playTone("success");
      this.vibrate(40);

      App.toast(`Saved & Approved Document #${this.currentImage.id}!`, "success");
      App.refreshDashboardStats();
      this.refreshStageCounts();
      this.loadNext();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  // Skip & Discard
  async skipCurrent() {
    if (!this.currentImage) return;
    try {
      await API.skipImage(this.currentImage.id, "Skipped & purged by human annotator");
      this.clearLocalDraft(this.currentImage.id);
      this.playTone("discard");
      this.vibrate(30);

      App.toast(`Document #${this.currentImage.id} skipped & file permanently deleted`, "warning");
      App.refreshDashboardStats();
      this.refreshStageCounts();
      this.loadNext();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  // Queue for AI Agent / MCP Processing
  async askAi() {
    if (!this.currentImage) return;
    const aiBox = document.getElementById("anno-ai-output");
    const aiStatus = document.getElementById("anno-ai-status");
    if (aiStatus) aiStatus.innerText = "Queueing for AI / MCP Agent...";
    if (aiBox) aiBox.value = "Assigning document to AI Queue with Priority 1...";

    try {
      const res = await API.askAiAssist(this.currentImage.id);
      if (aiBox) aiBox.value = res.ai_output;
      if (aiStatus) aiStatus.innerText = "Queued for Antigravity / MCP Agent";

      const aiBadge = document.getElementById("anno-ai-badge");
      if (aiBadge) aiBadge.classList.remove("hidden");

      App.toast(`Document #${this.currentImage.id} queued for AI Agent!`, "info");
      this.refreshStageCounts();
    } catch (err) {
      if (aiStatus) aiStatus.innerText = "Queueing failed.";
      App.toast(err.message, "error");
    }
  },

  applyAiToOcr() {
    const aiBox = document.getElementById("anno-ai-output");
    if (aiBox?.value) {
      document.getElementById("anno-ocr-text").value = aiBox.value;
      this.saveLocalDraft();
      App.toast("Copied AI text to Devanagari OCR field!", "success");
    }
  },

  applyAiToNepali() {
    const aiBox = document.getElementById("anno-ai-output");
    if (aiBox?.value) {
      document.getElementById("anno-caption-ne").value = aiBox.value.split("\n")[0];
      this.saveLocalDraft();
      App.toast("Copied AI text to Nepali Caption!", "success");
    }
  },

  applyAiToEnglish() {
    const aiBox = document.getElementById("anno-ai-output");
    if (aiBox?.value) {
      document.getElementById("anno-caption-en").value = aiBox.value;
      this.saveLocalDraft();
      App.toast("Copied AI text to English Caption!", "success");
    }
  },

  applyAllAi() {
    this.applyAiToOcr();
  },

  undoLastAction() {
    App.toast("Undo buffer: navigating to previous document state", "info");
    this.loadPrevious();
  },

  // --- Browser AI Studio Key & Direct Gemini Vision (Frontend Only) ---
  openApiKeyModal() {
    const modal = document.getElementById("modal-api-key");
    const input = document.getElementById("input-gemini-api-key");
    if (modal) {
      if (input) {
        input.value = localStorage.getItem("gemini_api_key") || "";
      }
      modal.classList.remove("hidden");
    }
  },

  closeApiKeyModal() {
    const modal = document.getElementById("modal-api-key");
    if (modal) modal.classList.add("hidden");
  },

  saveApiKey() {
    const input = document.getElementById("input-gemini-api-key");
    if (input) {
      const val = input.value.trim();
      if (val) {
        localStorage.setItem("gemini_api_key", val);
        App.toast("Google AI Studio API key saved to browser localStorage!", "success");
      } else {
        localStorage.removeItem("gemini_api_key");
        App.toast("API Key cleared.", "info");
      }
    }
    this.closeApiKeyModal();
  },

  clearApiKey() {
    localStorage.removeItem("gemini_api_key");
    const input = document.getElementById("input-gemini-api-key");
    if (input) input.value = "";
    App.toast("API Key removed from browser.", "info");
    this.closeApiKeyModal();
  },

  toggleLensGuideModal() {
    const modal = document.getElementById("modal-lens-guide");
    if (modal) modal.classList.toggle("hidden");
  },

  /**
   * Run Direct Browser Gemini Vision Annotation
   * TODO: User / Frontend-only Gemini API integration.
   * This calls Google AI Studio directly from the browser using the user's saved API key.
   */
  async runBrowserGeminiVision() {
    if (!this.currentImage) {
      App.toast("No image selected to annotate.", "warning");
      return;
    }

    const apiKey = localStorage.getItem("gemini_api_key");
    if (!apiKey) {
      App.toast("Please enter your Google AI Studio API key first.", "warning");
      this.openApiKeyModal();
      return;
    }

    const aiBox = document.getElementById("anno-ai-output");
    const aiStatus = document.getElementById("anno-ai-status");
    const runBtn = document.getElementById("btn-browser-ai-run");

    if (aiStatus) aiStatus.innerText = "Processing image with Gemini Vision in browser...";
    if (aiBox) aiBox.value = "Fetching image bytes and calling Gemini API...";
    if (runBtn) runBtn.disabled = true;

    try {
      // 1. Fetch the image blob as Base64 from the server
      const imgRes = await fetch(this.currentImage.file_path);
      const blob = await imgRes.blob();
      const base64Data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
          const res = reader.result;
          const base64 = res.split(",")[1];
          resolve(base64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });

      // 2. Call Google AI Studio (Gemini 2.5 Flash / Gemini 1.5 Flash endpoint)
      // TODO: Users can modify the model version or customize prompt below
      const prompt = `You are an expert Nepali document annotator and OCR engine.
Analyze this image carefully:
1. Devanagari OCR Text: Transcribe all visible Devanagari (Nepali/Hindi) and English text accurately, preserving line breaks.
2. Nepali Caption: Provide a clear, natural Nepali descriptive caption summarizing what this document/image is.
3. English Caption: Provide an accurate English caption describing the document.
4. Document Type: Identify the category (e.g. citizenship, lalpurja, gazette, license, passport, certificate, letter, receipt, notice, form, other).

Format your response strictly as JSON with keys:
{
  "ocr_text": "...",
  "caption_nepali": "...",
  "caption_english": "...",
  "document_type": "..."
}`;

      const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`;
      const payload = {
        contents: [
          {
            parts: [
              { text: prompt },
              {
                inlineData: {
                  mimeType: blob.type || "image/webp",
                  data: base64Data,
                },
              },
            ],
          },
        ],
        generationConfig: {
          temperature: 0.2,
          responseMimeType: "application/json",
        },
      };

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.error?.message || `API error: ${response.status}`);
      }

      const resData = await response.json();
      const textOutput = resData.candidates?.[0]?.content?.parts?.[0]?.text || "";

      let parsed = null;
      try {
        parsed = JSON.parse(textOutput);
      } catch (e) {
        // Fallback if not pure JSON
        parsed = {
          ocr_text: textOutput,
          caption_nepali: textOutput.split("\n")[0] || "",
          caption_english: "",
          document_type: "other",
        };
      }

      // Populate annotator fields
      if (parsed.ocr_text) {
        document.getElementById("anno-ocr-text").value = parsed.ocr_text;
      }
      if (parsed.caption_nepali) {
        document.getElementById("anno-caption-ne").value = parsed.caption_nepali;
      }
      if (parsed.caption_english) {
        document.getElementById("anno-caption-en").value = parsed.caption_english;
      }
      if (parsed.document_type) {
        document.getElementById("anno-doc-type").value = parsed.document_type;
      }

      if (aiBox) aiBox.value = textOutput;
      if (aiStatus) aiStatus.innerText = "Gemini Vision annotation successfully completed!";

      this.saveLocalDraft();
      this.playTone("success");
      App.toast("Gemini Vision generated fields populated automatically!", "success");
    } catch (err) {
      console.error(err);
      if (aiStatus) aiStatus.innerText = "Gemini Vision error: " + err.message;
      if (aiBox) aiBox.value = "Error: " + err.message;
      App.toast("Gemini API Error: " + err.message, "error");
    } finally {
      if (runBtn) runBtn.disabled = false;
    }
  },

  toggleZoomModal() {
    const modal = document.getElementById("image-modal");
    if (modal) modal.classList.toggle("hidden");
  },

  closeZoomModal() {
    const modal = document.getElementById("image-modal");
    if (modal) modal.classList.add("hidden");
  },
};
