/**
 * AI Approval Queue Component (Gated MCP Intermediate Protocol)
 * Manages human verification and inline editing for AI-generated annotations.
 */
const ReviewComponent = {
  pendingItems: [],

  init() {
    this.loadPending();
  },

  async loadPending() {
    const container = document.getElementById("ai-review-cards-container");
    if (!container) return;

    try {
      const list = await API.getPendingReviews(1, 24);
      this.pendingItems = list;

      const badgeNav = document.getElementById("ai-pending-badge");
      const badgeSb = document.getElementById("sb-ai-pending-badge");
      const badgeBtn = document.getElementById("btn-review-badge");
      const badgeMob = document.getElementById("mob-badge-review");
      if (badgeNav) {
        badgeNav.innerText = list.length;
        badgeNav.classList.toggle("hidden", list.length === 0);
      }
      if (badgeSb) {
        badgeSb.innerText = list.length;
        badgeSb.classList.toggle("hidden", list.length === 0);
      }
      if (badgeBtn) badgeBtn.innerText = list.length;
      if (badgeMob) {
        badgeMob.innerText = list.length;
        badgeMob.classList.toggle("hidden", list.length === 0);
      }

      container.innerHTML = "";

      if (list.length === 0) {
        container.innerHTML = `
          <div class="col-span-full text-center py-16 text-slate-400 text-xs">
            <i data-lucide="check-circle-2" class="w-10 h-10 mx-auto mb-2 text-emerald-500"></i>
            <p class="font-semibold text-slate-700">All AI annotations reviewed!</p>
            <p class="text-slate-400 mt-1">No items currently waiting in the gated approval queue.</p>
          </div>
        `;
        lucide.createIcons();
        return;
      }

      list.forEach(img => {
        const card = document.createElement("div");
        card.id = `review-card-${img.id}`;
        card.className = "bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between space-y-3";

        card.innerHTML = `
          <div>
            <div class="flex items-center justify-between text-xs mb-2">
              <span class="font-bold text-slate-900">Document #${img.id}</span>
              <div class="flex items-center gap-1.5">
                <span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold text-[10px] capitalize">${img.document_type || "Document"}</span>
                <span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-semibold text-[10px]">AI Pending</span>
              </div>
            </div>

            <!-- Thumbnail with Click to Zoom -->
            <div class="w-full h-44 sm:h-48 bg-slate-950 rounded-lg overflow-hidden flex items-center justify-center mb-3 cursor-pointer group relative" onclick="ReviewComponent.zoomImage(${img.id})">
              <img src="/api/images/${img.id}/file" onerror="this.onerror=null; this.src='/static/placeholder.svg'" class="max-h-full max-w-full object-contain group-hover:scale-105 transition-transform duration-150">
              <span class="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 rounded bg-black/60 text-white text-[9px] opacity-0 group-hover:opacity-100 transition-opacity">Zoom</span>
            </div>

            <!-- AI Output Reference (if available) -->
            ${img.ai_output ? `
            <div class="mb-2 p-2 bg-indigo-50/70 rounded border border-indigo-100 text-[11px] text-indigo-900 font-mono-code max-h-16 overflow-y-auto">
              <span class="font-bold text-indigo-700 block text-[10px] uppercase">AI Raw Output:</span>
              ${img.ai_output}
            </div>` : ''}

            <!-- Inline Editable Fields -->
            <div class="space-y-2 text-xs">
              <div>
                <label class="block font-semibold text-slate-600 mb-0.5">Devanagari OCR Text:</label>
                <textarea id="rev-ocr-${img.id}" rows="2" class="w-full devanagari text-xs bg-slate-50 border border-slate-200 rounded p-2 focus:ring-1 focus:ring-rose-500 focus:outline-none leading-relaxed">${img.ocr_text || ""}</textarea>
              </div>
              <div>
                <label class="block font-semibold text-slate-600 mb-0.5">Nepali Caption (VLM/CLIP):</label>
                <textarea id="rev-cap-ne-${img.id}" rows="1" class="w-full devanagari text-xs bg-slate-50 border border-slate-200 rounded p-2 focus:ring-1 focus:ring-rose-500 focus:outline-none leading-relaxed">${img.caption_nepali || ""}</textarea>
              </div>
              <div>
                <label class="block font-semibold text-slate-600 mb-0.5">English Caption:</label>
                <input id="rev-cap-en-${img.id}" type="text" value="${img.caption_english || ""}" class="w-full text-xs bg-slate-50 border border-slate-200 rounded p-2 focus:ring-1 focus:ring-rose-500 focus:outline-none">
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-2 pt-3 border-t border-slate-100">
            <button onclick="ReviewComponent.action(${img.id}, 'approve')" class="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-lg transition-all flex items-center justify-center gap-1">
              <i data-lucide="check" class="w-3.5 h-3.5"></i> Approve
            </button>
            <button onclick="ReviewComponent.action(${img.id}, 'edit')" class="px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-semibold text-xs rounded-lg transition-all flex items-center justify-center gap-1" title="Save human edits and approve">
              <i data-lucide="save" class="w-3.5 h-3.5"></i> Save Edit
            </button>
            <button onclick="ReviewComponent.action(${img.id}, 'reject')" class="px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 font-semibold text-xs rounded-lg transition-all" title="Reject AI draft">
              <i data-lucide="x" class="w-3.5 h-3.5"></i> Reject
            </button>
          </div>
        `;

        container.appendChild(card);
      });

      lucide.createIcons();
    } catch (err) {
      console.error(err);
    }
  },

  async action(id, actionType) {
    const edits = {};
    if (actionType === "edit") {
      edits.ocr_text = document.getElementById(`rev-ocr-${id}`)?.value.trim();
      edits.caption_nepali = document.getElementById(`rev-cap-ne-${id}`)?.value.trim();
      edits.caption_english = document.getElementById(`rev-cap-en-${id}`)?.value.trim();
    }

    try {
      await API.reviewAction(id, actionType, edits);
      App.toast(`Document #${id} ${actionType === 'edit' ? 'edited & approved' : actionType + 'd'}!`, "success");
      App.refreshDashboardStats();

      // Remove card smoothly
      const card = document.getElementById(`review-card-${id}`);
      if (card) {
        card.style.opacity = "0";
        setTimeout(() => {
          card.remove();
          this.loadPending();
        }, 150);
      }
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async bulkApproveAll() {
    const ids = this.pendingItems.map(i => i.id);
    if (ids.length === 0) return;

    try {
      const res = await API.bulkApprove(ids);
      App.toast(`Approved ${res.approved_count} annotations!`, "success");
      App.refreshDashboardStats();
      this.loadPending();
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  zoomImage(id) {
    const modal = document.getElementById("image-modal");
    const modalImg = document.getElementById("modal-img-el");
    if (modal && modalImg) {
      modalImg.src = `/api/images/${id}/file`;
      modal.classList.remove("hidden");
    }
  },
};
