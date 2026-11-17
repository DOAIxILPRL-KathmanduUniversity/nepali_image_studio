/**
 * AI Concept Studio & Saved Concept Library Component
 * Autonomous AI generation of Devanagari captions & English search terms,
 * persistent concept catalog management, and 1-click targeted iCrawler execution.
 */
const ConceptStudioComponent = {
  currentPreview: null,
  savedConcepts: [],

  init() {
    this.loadSaved();
  },

  useChip(topic) {
    const input = document.getElementById("studio-seed-topic");
    if (input) input.value = topic;
    this.generateFromInput();
  },

  async generateFromInput() {
    const input = document.getElementById("studio-seed-topic");
    const topic = input ? input.value.trim() : "";
    App.toast("Generating AI concept suggestions...", "info");

    try {
      const res = await API.suggestAiConcept(topic);
      this.renderPreview(res);
      App.toast("AI Concept proposed! Review and save to library.", "success");
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async generateBatch() {
    App.toast("Synthesizing batch of 5 diverse Nepali concepts...", "info");
    try {
      const list = await API.batchAiConcepts(5);
      if (list && list.length > 0) {
        // Show first one in preview
        this.renderPreview(list[0]);
        // Also automatically save the batch or let user browse
        App.toast(`Generated ${list.length} document concepts!`, "success");
      }
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  renderPreview(concept) {
    this.currentPreview = concept;
    const card = document.getElementById("studio-preview-card");
    if (!card) return;

    card.classList.remove("hidden");
    document.getElementById("prev-doc-type").innerText = concept.document_type || "DOCUMENT";
    document.getElementById("prev-topic").innerText = concept.topic;
    document.getElementById("prev-caption-ne").innerText = concept.caption_nepali;
    document.getElementById("prev-query-en").innerText = concept.search_query_en;

    const altContainer = document.getElementById("prev-alt-queries");
    if (altContainer) {
      altContainer.innerHTML = "";
      (concept.alternative_queries || []).forEach(q => {
        const pill = document.createElement("span");
        pill.className = "px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-mono-code text-[9px]";
        pill.innerText = q;
        altContainer.appendChild(pill);
      });
    }

    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  },

  async saveCurrentPreview() {
    if (!this.currentPreview) return;
    App.toast("Saving concept to library...", "info");

    try {
      await API.saveConcept({
        topic: this.currentPreview.topic,
        document_type: this.currentPreview.document_type || "other",
        caption_nepali: this.currentPreview.caption_nepali,
        search_query_en: this.currentPreview.search_query_en,
        alternative_queries: this.currentPreview.alternative_queries || [],
        tags: this.currentPreview.tags || [],
      });

      App.toast(`Saved "${this.currentPreview.topic}" to Concept Library!`, "success");
      this.loadSaved();
      // Clear input
      const input = document.getElementById("studio-seed-topic");
      if (input) input.value = "";
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async loadSaved() {
    const tableBody = document.getElementById("tbl-saved-concepts");
    if (!tableBody) return;

    const statusFilter = document.getElementById("studio-filter-status")?.value || "";
    const search = document.getElementById("studio-search-text")?.value.trim() || "";

    const params = {};
    if (statusFilter === "downloaded") params.is_downloaded = true;
    if (statusFilter === "pending") params.is_downloaded = false;
    if (search) params.search = search;

    try {
      const items = await API.getSavedConcepts(params);
      this.savedConcepts = items;
      tableBody.innerHTML = "";

      if (items.length === 0) {
        tableBody.innerHTML = `
          <tr>
            <td colspan="5" class="p-8 text-center text-slate-400 text-xs">
              <i data-lucide="bookmark" class="w-8 h-8 mx-auto mb-2 text-slate-300"></i>
              No saved concepts found. Use the AI Generator on the left to propose concepts.
            </td>
          </tr>
        `;
        lucide.createIcons();
        return;
      }

      items.forEach(c => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-50 transition-colors";

        const statusBadge = c.is_downloaded
          ? `<span class="px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-100 text-emerald-800">Ingested</span>`
          : `<span class="px-2 py-0.5 rounded-full text-[9px] font-bold bg-slate-100 text-slate-600">Pending</span>`;

        tr.innerHTML = `
          <td class="p-2.5 max-w-[200px]">
            <div class="font-bold text-slate-900 truncate">${c.topic}</div>
            <div class="devanagari text-[11px] text-slate-500 line-clamp-2 mt-0.5">${c.caption_nepali}</div>
          </td>
          <td class="p-2.5 whitespace-nowrap">
            <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 capitalize">
              ${c.document_type || "Document"}
            </span>
          </td>
          <td class="p-2.5 font-mono-code text-[11px] text-slate-700 max-w-[160px] truncate" title="${c.search_query_en}">
            ${c.search_query_en}
          </td>
          <td class="p-2.5 text-center whitespace-nowrap">
            <div class="font-bold text-slate-800">${c.images_downloaded_count || 0}</div>
            <div class="mt-0.5">${statusBadge}</div>
          </td>
          <td class="p-2.5 text-right whitespace-nowrap space-x-1">
            <button onclick="ConceptStudioComponent.runIngestion(${c.id})" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[11px] rounded-lg shadow-2xs transition-all inline-flex items-center gap-1" title="Download images matching this concept">
              <i data-lucide="play" class="w-3 h-3"></i> Ingest
            </button>
            <button onclick="ConceptStudioComponent.deleteConcept(${c.id})" class="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors" title="Delete concept">
              <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
            </button>
          </td>
        `;
        tableBody.appendChild(tr);
      });

      lucide.createIcons();
    } catch (err) {
      console.error(err);
    }
  },

  async runIngestion(conceptId) {
    const statusBox = document.getElementById("studio-run-status");
    const statusMsg = document.getElementById("studio-run-msg");

    if (statusBox) statusBox.classList.remove("hidden");
    if (statusMsg) statusMsg.innerText = "Targeted iCrawler searching and streaming WebP images...";
    App.toast("Launching targeted iCrawler for saved concept...", "info");

    try {
      const results = await API.runConceptIngestion(conceptId, 15);
      if (statusBox) statusBox.classList.add("hidden");

      App.toast(`Successfully ingested ${results.length} documents! Attached concept caption and tags.`, "success");
      App.refreshDashboardStats();
      this.loadSaved();
    } catch (err) {
      if (statusBox) statusBox.classList.add("hidden");
      App.toast(err.message, "error");
    }
  },

  async deleteConcept(id) {
    if (!confirm("Are you sure you want to delete this concept from your library?")) return;
    try {
      await API.deleteSavedConcept(id);
      App.toast("Concept deleted from library", "info");
      this.loadSaved();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },
};
