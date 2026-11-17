/**
 * Open Nepali Image — Unified API Service Module
 * Handles all REST endpoints with error handling.
 */
const API = {
  // Stats & Network Info
  async getDashboardStats() {
    const res = await fetch("/api/stats/dashboard");
    if (!res.ok) throw new Error("Failed to fetch dashboard stats");
    return await res.json();
  },

  async getNetworkInfo() {
    const res = await fetch("/api/stats/network");
    if (!res.ok) throw new Error("Failed to fetch network info");
    return await res.json();
  },

  // Crawler Controls
  async getCrawlerStatus() {
    const res = await fetch("/api/crawler/status");
    if (!res.ok) throw new Error("Failed to fetch crawler status");
    return await res.json();
  },

  async startCrawler(payload) {
    const res = await fetch("/api/crawler/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to start crawler");
    }
    return await res.json();
  },

  async pauseCrawler() {
    const res = await fetch("/api/crawler/pause", { method: "POST" });
    return await res.json();
  },

  async resumeCrawler() {
    const res = await fetch("/api/crawler/resume", { method: "POST" });
    return await res.json();
  },

  async stopCrawler() {
    const res = await fetch("/api/crawler/stop", { method: "POST" });
    return await res.json();
  },

  async setConcurrency(workers) {
    const res = await fetch("/api/crawler/concurrency", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workers }),
    });
    return await res.json();
  },

  async setCrawlerMode(mode) {
    const res = await fetch("/api/crawler/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    if (!res.ok) throw new Error("Failed to set crawler mode");
    return await res.json();
  },

  async retryFailedMediaJobs() {
    const res = await fetch("/api/crawler/media/retry-failed", { method: "POST" });
    if (!res.ok) throw new Error("Failed to retry media jobs");
    return await res.json();
  },

  async resetCircuitBreaker() {
    const res = await fetch("/api/crawler/circuit-breaker/reset", { method: "POST" });
    if (!res.ok) throw new Error("Failed to reset circuit breaker");
    return await res.json();
  },

  async getSeeds() {
    const res = await fetch("/api/crawler/seeds");
    return await res.json();
  },

  async getHarvestedDomains(page = 1, limit = 25, tier = "", search = "") {
    let url = `/api/crawler/domains?page=${page}&limit=${limit}`;
    if (tier) url += `&tier=${encodeURIComponent(tier)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to fetch harvested domains");
    return await res.json();
  },

  async addCustomDomain(domainOrUrl) {
    const res = await fetch("/api/crawler/domains/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain_or_url: domainOrUrl }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to add domain");
    }
    return await res.json();
  },

  async seedTopDomains(tiers = null, batchSize = 100) {
    const res = await fetch("/api/crawler/seed-top-domains", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tiers, batch_size: batchSize }),
    });
    if (!res.ok) throw new Error("Failed to seed top domains");
    return await res.json();
  },

  // Images & Gallery
  async getImages(params = {}) {
    const query = new URLSearchParams();
    if (params.page) query.set("page", params.page);
    if (params.limit) query.set("limit", params.limit);
    if (params.status) query.set("status", params.status);
    if (params.stage) query.set("stage", params.stage);
    if (params.is_approved !== undefined && params.is_approved !== "") query.set("is_approved", params.is_approved);
    if (params.document_type) query.set("document_type", params.document_type);
    if (params.search) query.set("search", params.search);
    if (params.sort_by) query.set("sort_by", params.sort_by);

    const res = await fetch(`/api/images?${query.toString()}`);
    if (!res.ok) throw new Error("Failed to fetch images");
    return await res.json();
  },

  async getNextUnannotatedDocument(currentId = null, stage = "unannotated", direction = "next") {
    let url = `/api/images/next-unannotated?stage=${encodeURIComponent(stage)}&direction=${encodeURIComponent(direction)}`;
    if (currentId) url += `&current_id=${currentId}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to fetch next document");
    return await res.json();
  },

  async batchImageAction(action, imageIds, category = null) {
    const res = await fetch("/api/images/batch-action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, image_ids: imageIds, category }),
    });
    if (!res.ok) throw new Error("Failed to execute batch action");
    return await res.json();
  },

  async getCategories() {
    const res = await fetch("/api/images/categories");
    if (!res.ok) throw new Error("Failed to fetch document categories");
    return await res.json();
  },

  async askAiAssist(id, prompt = "") {
    const res = await fetch(`/api/images/${id}/ai-assist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    if (!res.ok) throw new Error("Failed to generate AI vision suggestions");
    return await res.json();
  },

  async getImage(id) {
    const res = await fetch(`/api/images/${id}`);
    if (!res.ok) throw new Error(`Failed to fetch image #${id}`);
    return await res.json();
  },

  async annotateImage(id, data) {
    const res = await fetch(`/api/images/${id}/annotate`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to save annotation");
    return await res.json();
  },

  async skipImage(id, reason = "Skipped by user") {
    const res = await fetch(`/api/images/${id}/skip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) throw new Error("Failed to skip image");
    return await res.json();
  },

  // Review & Approval Queue
  async getPendingReviews(page = 1, limit = 20) {
    const res = await fetch(`/api/review/pending?page=${page}&limit=${limit}`);
    if (!res.ok) throw new Error("Failed to fetch pending reviews");
    return await res.json();
  },

  async reviewAction(id, action, edits = {}) {
    const res = await fetch(`/api/review/${id}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        edited_text: edits.ocr_text,
        edited_caption_nepali: edits.caption_nepali,
        edited_caption_english: edits.caption_english,
      }),
    });
    if (!res.ok) throw new Error(`Failed to submit ${action} action`);
    return await res.json();
  },

  async bulkApprove(ids) {
    const res = await fetch("/api/review/bulk-approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ids),
    });
    if (!res.ok) throw new Error("Failed to bulk approve");
    return await res.json();
  },

  // Concept & iCrawler Search
  async suggestConcept(conceptNepali) {
    const res = await fetch("/api/search/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concept_nepali: conceptNepali }),
    });
    if (!res.ok) throw new Error("Failed to generate concept suggestions");
    return await res.json();
  },

  async runICrawler(query, maxImages = 15) {
    const res = await fetch("/api/search/icrawler", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query_nepali: query,
        query_english: query,
        max_images: maxImages,
      }),
    });
    if (!res.ok) throw new Error("Failed to execute iCrawler search");
    return await res.json();
  },

  // Dataset Export
  async exportDataset(format = "jsonl", approvedOnly = true) {
    const res = await fetch(`/api/images/export?approved_only=${approvedOnly}&format_type=${format}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("Failed to export dataset");
    return await res.json();
  },

  // AI Concept Studio & Saved Concept Library
  async getSavedConcepts(params = {}) {
    const q = new URLSearchParams();
    if (params.search) q.append("search", params.search);
    if (params.is_downloaded !== undefined && params.is_downloaded !== "") {
      q.append("is_downloaded", params.is_downloaded);
    }
    const res = await fetch(`/api/concepts?${q.toString()}`);
    if (!res.ok) throw new Error("Failed to load saved concepts");
    return await res.json();
  },

  async suggestAiConcept(topic = "") {
    const res = await fetch("/api/concepts/ai-suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: topic || null }),
    });
    if (!res.ok) throw new Error("Failed to generate AI concept suggestion");
    return await res.json();
  },

  async batchAiConcepts(count = 5) {
    const res = await fetch(`/api/concepts/ai-batch?count=${count}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("Failed to generate batch concepts");
    return await res.json();
  },

  async saveConcept(conceptData) {
    const res = await fetch("/api/concepts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(conceptData),
    });
    if (!res.ok) throw new Error("Failed to save concept to library");
    return await res.json();
  },

  async deleteSavedConcept(id) {
    const res = await fetch(`/api/concepts/${id}`, {
      method: "DELETE",
    });
    if (!res.ok && res.status !== 204) throw new Error("Failed to delete concept");
    return true;
  },

  async runConceptIngestion(conceptId, maxImages = 15) {
    const res = await fetch(`/api/concepts/${conceptId}/run?max_images=${maxImages}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("Failed to run concept ingestion");
    return await res.json();
  },
};
