/**
 * Concept Search & iCrawler Component
 * Suggests cross-lingual search terms and executes targeted keyword acquisition.
 */
const SearchComponent = {
  init() {
    // bind enter key
    const inp = document.getElementById("concept-input");
    if (inp) {
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") this.suggest();
      });
    }
  },

  async suggest() {
    const val = document.getElementById("concept-input")?.value.trim();
    if (!val) return;

    try {
      const d = await API.suggestConcept(val);
      document.getElementById("sug-caption-ne").innerText = d.suggested_caption_nepali;
      document.getElementById("sug-doc-type").innerText = d.suggested_document_type.toUpperCase();

      const pillContainer = document.getElementById("sug-query-pills");
      pillContainer.innerHTML = "";

      d.suggested_english_search_queries.forEach((q) => {
        const pill = document.createElement("button");
        pill.className = "px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-md font-medium text-xs transition-all flex items-center gap-1";
        pill.innerHTML = `<span>${q}</span><i data-lucide="arrow-down-right" class="w-3 h-3 text-indigo-400"></i>`;
        pill.onclick = () => {
          const qInp = document.getElementById("icrawler-query");
          if (qInp) qInp.value = q;
        };
        pillContainer.appendChild(pill);
      });

      if (d.suggested_english_search_queries.length > 0) {
        const qInp = document.getElementById("icrawler-query");
        if (qInp) qInp.value = d.suggested_english_search_queries[0];
      }

      document.getElementById("concept-suggestion-box").classList.remove("hidden");
      lucide.createIcons();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async run() {
    const q = document.getElementById("icrawler-query")?.value.trim();
    const num = parseInt(document.getElementById("icrawler-max")?.value) || 15;
    if (!q) return;

    const msgEl = document.getElementById("icrawler-status-msg");
    if (msgEl) msgEl.innerText = `Fetching and processing up to ${num} images for '${q}'...`;

    try {
      const list = await API.runICrawler(q, num);
      if (msgEl) msgEl.innerText = `Success! Added ${list.length} new unique documents ready for annotation.`;
      App.toast(`Ingested ${list.length} new images!`, "success");
      App.refreshDashboardStats();
    } catch (err) {
      if (msgEl) msgEl.innerText = "Error executing iCrawler search.";
      App.toast(err.message, "error");
    }
  },
};
