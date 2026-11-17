/**
 * Crawler & Domain Harvester Component
 * Manages crawler lifecycle, multi-worker concurrency, and 2,000+ domain directory.
 */
const CrawlerComponent = {
  domainPage: 1,
  domainLimit: 25,
  currentTierFilter: "",
  searchQuery: "",

  init() {
    this.bindEvents();
    this.loadSeeds();
    this.loadDomains(1);
    this.refreshStatus();
  },

  bindEvents() {
    const rngWorkers = document.getElementById("rng-concurrency");
    if (rngWorkers) {
      rngWorkers.addEventListener("input", (e) => {
        document.getElementById("lbl-concurrency-val").innerText = `${e.target.value} Workers`;
      });
      rngWorkers.addEventListener("change", async (e) => {
        try {
          await API.setConcurrency(parseInt(e.target.value));
          App.toast(`Concurrency updated to ${e.target.value} workers`);
        } catch (err) {
          App.toast(err.message, "error");
        }
      });
    }

    const rngRate = document.getElementById("rng-rate");
    if (rngRate) {
      rngRate.addEventListener("input", (e) => {
        document.getElementById("lbl-rate-val").innerText = `${e.target.value} ms`;
      });
    }
  },

  async start() {
    const selected = Array.from(document.querySelectorAll("input[name='seed_url']:checked")).map(cb => cb.value);
    const workers = parseInt(document.getElementById("rng-concurrency").value) || 15;
    const depth = parseInt(document.getElementById("sel-max-depth").value) || 4;
    const rate = parseInt(document.getElementById("rng-rate").value) || 800;

    try {
      await API.startCrawler({
        seed_urls: selected,
        max_depth: depth,
        rate_limit_ms: rate,
        concurrency: workers,
      });
      App.toast(`Crawler launched with ${workers} workers!`, "success");
      this.refreshStatus();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async pause() {
    try {
      await API.pauseCrawler();
      App.toast("Crawler paused", "warning");
      this.refreshStatus();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async resume() {
    try {
      await API.resumeCrawler();
      App.toast("Crawler resumed", "info");
      this.refreshStatus();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async stop() {
    try {
      await API.stopCrawler();
      App.toast("Crawler stopped", "info");
      this.refreshStatus();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async setMode(mode) {
    try {
      await API.setCrawlerMode(mode);
      ["balanced", "media_backlog", "discovery"].forEach((m) => {
        const btn = document.getElementById(m === "media_backlog" ? "btn-mode-media" : `btn-mode-${m}`);
        if (btn) {
          if (m === mode) {
            btn.className = "px-3 py-1.5 rounded-lg bg-indigo-600 text-white font-bold flex items-center gap-1.5 transition-all shadow-xs";
          } else {
            btn.className = "px-3 py-1.5 rounded-lg text-slate-300 hover:text-white font-medium flex items-center gap-1.5 transition-all";
          }
        }
      });

      const topMode = document.getElementById("top-crawler-mode-lbl");
      const sbMode = document.getElementById("sb-crawler-mode-badge");
      if (topMode) topMode.innerText = mode.replace("_", " ");
      if (sbMode) sbMode.innerText = mode.replace("_", " ");

      App.toast(`Crawler Strategy set to: ${mode.toUpperCase()}`, "success");
      this.refreshStatus();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async retryFailedMedia() {
    try {
      const res = await API.retryFailedMediaJobs();
      App.toast(`Requeued ${res.retried_jobs} failed media jobs!`, "success");
      this.refreshStatus();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async resetCircuitBreaker() {
    try {
      const res = await API.resetCircuitBreaker();
      App.toast(`Restored ${res.cleared_domains} throttled domains!`, "info");
      this.refreshStatus();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async refreshStatus() {
    try {
      const d = await API.getCrawlerStatus();
      const statusLbl = document.getElementById("crawler-status-label");
      if (statusLbl) {
        statusLbl.innerText = d.is_running ? (d.is_paused ? "Paused" : "Running") : "Idle";
        statusLbl.className = d.is_running
          ? (d.is_paused ? "text-sm font-bold text-amber-600" : "text-sm font-bold text-emerald-600")
          : "text-sm font-bold text-slate-700";
      }

      const miniDot = document.getElementById("crawler-live-dot");
      const miniStatus = document.getElementById("crawler-mini-status");
      const sbDot = document.getElementById("sb-crawler-live-dot");
      const sbStatus = document.getElementById("sb-crawler-status");
      const topDot = document.getElementById("top-crawler-live-dot");
      const topMode = document.getElementById("top-crawler-mode-lbl");
      const sbMode = document.getElementById("sb-crawler-mode-badge");

      const modeText = (d.mode || "balanced").replace("_", " ");
      if (topMode) topMode.innerText = modeText;
      if (sbMode) sbMode.innerText = modeText;

      const isLive = d.is_running && !d.is_paused;
      const dotClass = isLive ? "w-2 h-2 rounded-full bg-emerald-500 animate-pulse" : (d.is_paused ? "w-2 h-2 rounded-full bg-amber-500" : "w-2 h-2 rounded-full bg-slate-400");
      const statusText = d.is_running ? (d.is_paused ? "Paused" : `Active (${d.active_workers}w)`) : "Idle";

      if (miniDot) miniDot.className = dotClass;
      if (miniStatus) miniStatus.innerText = statusText;
      if (sbDot) sbDot.className = dotClass;
      if (sbStatus) sbStatus.innerText = statusText;
      if (topDot) topDot.className = dotClass;

      const sbBadge = document.getElementById("sb-crawler-badge");
      if (sbBadge) sbBadge.innerText = `${d.active_workers}w`;

      document.getElementById("crawler-frontier-pending").innerText = `${d.frontier_pending.toLocaleString()} URLs`;
      document.getElementById("crawler-frontier-done").innerText = `${d.frontier_crawled.toLocaleString()} URLs`;
      document.getElementById("crawler-active-workers-lbl").innerText = `${d.active_workers} / ${d.worker_count}`;
      document.getElementById("crawler-domains-harvested").innerText = `${d.total_domains_harvested.toLocaleString()} .np`;

      // Media Backlog metrics
      const elMedPend = document.getElementById("crawler-media-pending");
      const elMedAct = document.getElementById("crawler-media-active");
      const elMedDone = document.getElementById("crawler-media-done");
      const elMedDead = document.getElementById("crawler-media-dead");
      const elCircuit = document.getElementById("circuit-breaker-count");
      const topMedia = document.getElementById("top-media-backlog-count");

      if (elMedPend && d.media_jobs_pending !== undefined) elMedPend.innerText = d.media_jobs_pending.toLocaleString();
      if (elMedAct && d.media_jobs_processing !== undefined) elMedAct.innerText = d.media_jobs_processing.toLocaleString();
      if (elMedDone && d.media_jobs_done !== undefined) elMedDone.innerText = d.media_jobs_done.toLocaleString();
      if (elMedDead && d.media_jobs_dead !== undefined) elMedDead.innerText = d.media_jobs_dead.toLocaleString();
      if (elCircuit && d.slow_domains_count !== undefined) elCircuit.innerText = `${d.slow_domains_count} throttled`;
      if (topMedia && d.media_backlog_total !== undefined) topMedia.innerText = d.media_backlog_total.toLocaleString();

      const qEl = document.getElementById("stat-queue-depth");
      if (qEl) qEl.innerText = (d.media_jobs_pending || 0).toLocaleString();
    } catch (e) {
      // quiet
    }
  },

  async loadSeeds() {
    try {
      const data = await API.getSeeds();
      const container = document.getElementById("seed-categories-container");
      if (!container) return;
      container.innerHTML = "";

      data.categories.forEach((cat) => {
        const catDiv = document.createElement("div");
        catDiv.className = "bg-slate-50 p-3 rounded-xl border border-slate-200";
        let html = `
          <div class="font-bold text-xs text-slate-800 mb-2 flex items-center justify-between">
            <span>${cat.name}</span>
            <span class="text-[10px] uppercase font-bold text-slate-500 bg-slate-200 px-1.5 py-0.5 rounded">${cat.tier}.np</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-1.5">
        `;

        cat.seeds.forEach(s => {
          html += `
            <label class="flex items-center gap-2 text-xs text-slate-700 hover:text-slate-900 cursor-pointer">
              <input type="checkbox" name="seed_url" value="${s.url}" checked class="rounded text-rose-600 focus:ring-rose-500">
              <span class="truncate" title="${s.name} (${s.url})">${s.name}</span>
            </label>
          `;
        });

        html += `</div>`;
        catDiv.innerHTML = html;
        container.appendChild(catDiv);
      });
    } catch (e) {
      console.error(e);
    }
  },

  selectAllSeeds(check) {
    document.querySelectorAll("input[name='seed_url']").forEach(cb => cb.checked = check);
  },

  // Page-by-page Harvested Domains Browser
  async loadDomains(page = 1) {
    this.domainPage = page;
    const tier = document.getElementById("sel-domain-tier-filter")?.value || "";
    const search = document.getElementById("inp-domain-search")?.value.trim() || "";
    const limit = parseInt(document.getElementById("sel-domain-limit")?.value) || 25;

    try {
      const data = await API.getHarvestedDomains(page, limit, tier, search);
      const tbody = document.getElementById("tbl-harvested-domains");
      if (!tbody) return;
      tbody.innerHTML = "";

      // Update counters
      const badgeGov = document.getElementById("badge-dom-gov");
      const badgeEdu = document.getElementById("badge-dom-edu");
      const badgeOrg = document.getElementById("badge-dom-org");
      const badgeTotal = document.getElementById("badge-dom-total");
      if (badgeGov) badgeGov.innerText = `Gov: ${data.gov_domains.toLocaleString()}`;
      if (badgeEdu) badgeEdu.innerText = `Edu: ${data.edu_domains.toLocaleString()}`;
      if (badgeOrg) badgeOrg.innerText = `Org: ${data.org_domains.toLocaleString()}`;
      if (badgeTotal) badgeTotal.innerText = `Total: ${data.total_domains.toLocaleString()}`;

      if (data.domains.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="p-4 text-center text-slate-400 text-xs">No matching domains found.</td></tr>`;
        return;
      }

      data.domains.forEach(item => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-50 transition-colors";
        const tierBadgeClass = {
          gov: "bg-emerald-50 text-emerald-700 border-emerald-200",
          edu: "bg-blue-50 text-blue-700 border-blue-200",
          org: "bg-purple-50 text-purple-700 border-purple-200",
          mil: "bg-red-50 text-red-700 border-red-200",
          com: "bg-amber-50 text-amber-700 border-amber-200",
        }[item.domain_tier] || "bg-slate-100 text-slate-600 border-slate-200";

        tr.innerHTML = `
          <td class="p-2.5 font-bold text-slate-800 flex items-center gap-1.5">
            <span class="w-1.5 h-1.5 rounded-full ${item.pages_crawled > 0 ? 'bg-emerald-500' : 'bg-slate-300'}"></span>
            <a href="https://${item.domain}" target="_blank" rel="noreferrer" class="hover:underline hover:text-rose-600">${item.domain}</a>
          </td>
          <td class="p-2.5">
            <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${tierBadgeClass}">
              ${item.domain_tier}.np
            </span>
          </td>
          <td class="p-2.5 font-semibold ${item.pages_crawled > 0 ? 'text-emerald-600' : 'text-slate-400'}">
            ${item.pages_crawled}
          </td>
          <td class="p-2.5">
            <span class="px-1.5 py-0.5 rounded text-[10px] font-medium ${item.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}">
              ${item.status}
            </span>
          </td>
          <td class="p-2.5 text-slate-400 text-[10px]">
            ${item.discovered_at ? new Date(item.discovered_at).toLocaleTimeString() : "--"}
          </td>
        `;
        tbody.appendChild(tr);
      });

      // Pagination controls
      this.renderDomainPagination(data.page, data.total_pages, data.total_filtered);
    } catch (err) {
      console.error(err);
    }
  },

  renderDomainPagination(current, totalPages, totalFiltered) {
    const info = document.getElementById("dom-pagination-info");
    const container = document.getElementById("dom-pagination-btns");
    if (!info || !container) return;

    info.innerText = `Page ${current} of ${totalPages} (${totalFiltered.toLocaleString()} domains)`;
    container.innerHTML = "";

    const prevBtn = document.createElement("button");
    prevBtn.className = `px-2.5 py-1 rounded border text-xs font-medium ${current > 1 ? 'hover:bg-slate-100 text-slate-700 border-slate-300' : 'text-slate-300 border-slate-200 cursor-not-allowed'}`;
    prevBtn.innerText = "Prev";
    if (current > 1) prevBtn.onclick = () => this.loadDomains(current - 1);
    container.appendChild(prevBtn);

    const maxDisplay = 5;
    let start = Math.max(1, current - 2);
    let end = Math.min(totalPages, start + maxDisplay - 1);
    if (end - start < maxDisplay - 1) start = Math.max(1, end - maxDisplay + 1);

    for (let p = start; p <= end; p++) {
      const btn = document.createElement("button");
      btn.className = `px-2.5 py-1 rounded text-xs font-semibold ${p === current ? 'bg-rose-600 text-white' : 'hover:bg-slate-100 text-slate-700'}`;
      btn.innerText = p;
      btn.onclick = () => this.loadDomains(p);
      container.appendChild(btn);
    }

    const nextBtn = document.createElement("button");
    nextBtn.className = `px-2.5 py-1 rounded border text-xs font-medium ${current < totalPages ? 'hover:bg-slate-100 text-slate-700 border-slate-300' : 'text-slate-300 border-slate-200 cursor-not-allowed'}`;
    nextBtn.innerText = "Next";
    if (current < totalPages) nextBtn.onclick = () => this.loadDomains(current + 1);
    container.appendChild(nextBtn);
  },

  async addDomainManual() {
    const inp = document.getElementById("inp-manual-domain");
    if (!inp) return;
    const val = inp.value.trim();
    if (!val) return;

    try {
      const res = await API.addCustomDomain(val);
      App.toast(res.message, "success");
      inp.value = "";
      this.loadDomains(1);
      this.refreshStatus();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async seedAllTopDomains() {
    try {
      App.toast("Seeding top 2,043 .np domains into database...", "info");
      const res = await API.seedTopDomains();
      App.toast(res.message, "success");
      this.loadDomains(1);
      this.refreshStatus();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },
};
