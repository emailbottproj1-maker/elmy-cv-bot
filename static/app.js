/* Elmy CV Bot — single-file frontend (vanilla JS).
 * Renders templates into #app, calls /api/* endpoints, never touches Supabase directly.
 */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const app = $("#app");

const DEFAULT_AR = `فريق التوظيف الكريم في {company_name}،

يسعدني التقدّم بطلب للانضمام إلى فريق {company_name}. أرفق لكم سيرتي الذاتية للاطلاع عليها.

أعتقد أن مهاراتي وخبرتي ستكون إضافة قيّمة لفريقكم.

مع خالص التقدير،
{sender_name}`;

const DEFAULT_EN = `Dear {company_name} Hiring Team,

I am writing to express my strong interest in joining {company_name}. Please find my CV attached for your review.

I believe my skills and experience would be a valuable addition to your team.

Best regards,
{sender_name}`;

// ---------- tiny router ----------
async function init() {
  $("#logoutBtn").addEventListener("click", logout);
  const authed = await checkAuth();
  if (!authed) return renderLogin();
  renderCampaigns();
}

async function checkAuth() {
  try {
    const r = await fetch("/api/me");
    if (r.ok) { $("#logoutBtn").classList.remove("hidden"); return true; }
  } catch {}
  $("#logoutBtn").classList.add("hidden");
  return false;
}

async function logout() {
  await fetch("/api/login", { method: "DELETE" });
  $("#logoutBtn").classList.add("hidden");
  renderLogin();
}

function tplInto(id) {
  app.innerHTML = "";
  const tpl = $("#" + id);
  app.appendChild(tpl.content.cloneNode(true));
}

// ---------- login ----------
function renderLogin() {
  tplInto("tpl-login");
  $("#loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const errBox = $("#loginErr");
    errBox.textContent = "";
    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: fd.get("password") }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        errBox.textContent = d.error || "كلمة المرور خاطئة.";
        return;
      }
      $("#logoutBtn").classList.remove("hidden");
      renderCampaigns();
    } catch (err) {
      errBox.textContent = "تعذّر الاتصال بالخادم.";
    }
  });
}

// ---------- campaigns list ----------
async function renderCampaigns() {
  tplInto("tpl-campaigns");
  $("#newCampaignBtn").addEventListener("click", renderNewCampaign);

  // Excel import button — asks for sector first, then opens file picker
  $("#importBtn").addEventListener("click", () => {
    const res = $("#importResult");
    // Show inline sector selector
    res.innerHTML = `
      <div style="margin-top:8px;padding:10px;background:var(--surface2);border-radius:8px;">
        <label style="font-size:.85rem;font-weight:600;">القطاع الذي ستُسند إليه الشركات:</label>
        <select id="importSector" style="width:100%;margin:6px 0 8px;padding:6px;">
          <option value="Engineering">هندسة ومقاولات</option>
          <option value="Healthcare">صحة وطب</option>
          <option value="Marketing">تسويق وإعلان</option>
          <option value="Technology">تقنية وبرمجة</option>
          <option value="Finance">مالية وبنوك</option>
          <option value="Legal">قانون</option>
          <option value="Retail">تجزئة وتجارة</option>
          <option value="Education">تعليم</option>
          <option value="HR">موارد بشرية</option>
          <option value="Hospitality">ضيافة وفنادق</option>
          <option value="Logistics">لوجستيك وشحن</option>
        </select>
        <button class="primary" id="importPickFile" style="width:100%">📂 اختر ملف Excel</button>
      </div>`;
    $("#importPickFile").addEventListener("click", () => {
      const sector = $("#importSector").value;
      const inp = document.createElement("input");
      inp.type = "file"; inp.accept = ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
      inp.onchange = async () => {
        const file = inp.files[0]; if (!file) return;
        res.textContent = "جاري الاستيراد...";
        try {
          const r = await fetch("/api/import", {
            method: "POST",
            headers: {
              "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              "X-Filename": file.name,
              "X-Sector": sector,
            },
            body: file,
          });
          const d = await r.json();
          if (!r.ok) { res.textContent = "خطأ: " + (d.error || "فشل الاستيراد"); return; }
          res.textContent = `✅ تم استيراد ${d.imported} شركة في قطاع "${sector}"${d.skipped ? ` · تخطي ${d.skipped}` : ""}`;
        } catch { res.textContent = "تعذّر الاتصال بالخادم."; }
      };
      inp.click();
    });
  });

  const list = $("#campaignList");
  list.textContent = "جاري التحميل...";
  try {
    const r = await fetch("/api/campaigns");
    if (r.status === 401) return renderLogin();
    const data = await r.json();
    if (!data.campaigns || data.campaigns.length === 0) {
      list.innerHTML = '<div class="muted small">لا توجد حملات بعد. ابدأ بإنشاء حملة جديدة.</div>';
      return;
    }
    list.innerHTML = "";
    for (const c of data.campaigns) list.appendChild(campCard(c));
  } catch (e) {
    list.textContent = "تعذّر تحميل الحملات.";
  }
}

function campCard(c) {
  const div = document.createElement("div");
  div.className = "camp-card";
  const counts = c.counts || {};
  const sent = counts.sent || 0;
  const total = counts.total || 0;
  const pkg = c.package_size ? `باقة ${c.package_size}` : "القائمة الكاملة";
  const sector = c.target_sector ? `<span class="tag">${esc(sectorLabel(c.target_sector))}</span>` : "";
  const overlap = c.overlap_count
    ? ` · <span style="color:var(--warn)">⚠ ${c.overlap_count} مُعاد</span>`
    : "";
  div.innerHTML = `
    <div class="top">
      <span class="name">${esc(c.customer_label)} ${sector}</span>
      <span class="pill ${c.status}">${statusAr(c.status)}</span>
    </div>
    <div class="muted small">
      ${pkg} · المرسِل: ${esc(c.sender_name)} · أُرسل ${sent} من ${total}${counts.failed ? ` · فشل ${counts.failed}` : ""}${overlap}
    </div>
  `;
  div.addEventListener("click", () => renderCampaignDetail(c.id));
  return div;
}

function statusAr(s) {
  return { draft: "مسودة", active: "يعمل", paused: "متوقف مؤقتًا",
           stopped: "متوقف", done: "اكتملت" }[s] || s;
}

const SECTOR_AR = {
  Healthcare: "صحة", Marketing: "تسويق وإعلان", Technology: "تقنية وبرمجة",
  Finance: "مالية وبنوك", Engineering: "هندسة ومقاولات", Legal: "قانون",
  Retail: "تجزئة وتجارة", Education: "تعليم", HR: "موارد بشرية",
  Hospitality: "ضيافة وفنادق", Logistics: "لوجستيك وشحن",
};
function sectorLabel(code) { return SECTOR_AR[code] || code; }

// ---------- new campaign ----------
function renderNewCampaign() {
  tplInto("tpl-new-campaign");
  $("#backBtn").addEventListener("click", renderCampaigns);
  $("textarea[name=cover_letter_ar]").value = DEFAULT_AR;
  $("textarea[name=cover_letter_en]").value = DEFAULT_EN;
  // Load sectors from /api/sectors and populate dropdown
  (async () => {
    const sel = $("#sectorSelect");
    try {
      const r = await fetch("/api/sectors");
      if (!r.ok) throw new Error("sectors fetch failed");
      const { sectors } = await r.json();
      sel.innerHTML = "";
      for (const s of sectors) {
        const opt = document.createElement("option");
        opt.value = s.code;
        opt.textContent = `${s.label_ar} (${s.count} شركة)`;
        if (s.count === 0) opt.disabled = true;
        sel.appendChild(opt);
      }
      if (!sectors.length) {
        sel.innerHTML = '<option value="">لا توجد تخصصات. أضف شركات أولاً.</option>';
      }
    } catch (e) {
      sel.innerHTML = '<option value="">تعذّر تحميل التخصصات</option>';
    }
  })();

  $("#newCampForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const errBox = $("#newErr");
    const prog = $("#newProgress");
    errBox.textContent = ""; prog.classList.remove("hidden");
    $("#createBtn").disabled = true;

    const cv = fd.get("cv");
    if (!cv || !cv.size) { errBox.textContent = "اختر ملف CV."; reset(); return; }
    if (cv.size > 10 * 1024 * 1024) { errBox.textContent = "الملف كبير جدًا (10MB حد أقصى)."; reset(); return; }

    try {
      // 1) upload CV
      prog.textContent = "جاري رفع الـ CV...";
      const up = await fetch("/api/upload", {
        method: "POST",
        headers: { "Content-Type": "application/pdf", "X-Filename": cv.name },
        body: cv,
      });
      if (up.status === 401) return renderLogin();
      const upData = await up.json();
      if (!up.ok) throw new Error(upData.error || "فشل رفع CV");

      // 2) create campaign
      prog.textContent = "جاري إنشاء الحملة وتجهيز الشركات...";
      const body = {
        customer_label: fd.get("customer_label"),
        cv_storage_path: upData.path,
        sender_name: fd.get("sender_name"),
        subject_ar: fd.get("subject_ar"),
        subject_en: fd.get("subject_en"),
        cover_letter_ar: fd.get("cover_letter_ar"),
        cover_letter_en: fd.get("cover_letter_en"),
        use_ai: !!fd.get("use_ai"),
        package_size: fd.get("package_size") === "0" ? "all" : fd.get("package_size"),
        target_sector: fd.get("target_sector") || "any",
      };
      const cr = await fetch("/api/campaigns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const crData = await cr.json();
      if (!cr.ok) throw new Error(crData.error || "فشل إنشاء الحملة");

      // Show overlap warning briefly if the pool was exhausted.
      if (crData.overlap && crData.overlap > 0) {
        alert(
          `تنبيه: تم اختيار ${crData.targeted} شركة، منها ${crData.overlap} ` +
          `شركة مُعاد استخدامها (كانت ضمن حملات سابقة). الشركات الجديدة لم تكفِ الباقة.`
        );
      }
      renderCampaignDetail(crData.campaign.id);
    } catch (err) {
      errBox.textContent = err.message || "حدث خطأ.";
      reset();
    }
    function reset() { prog.classList.add("hidden"); $("#createBtn").disabled = false; }
  });
}

// ---------- campaign detail ----------
async function renderCampaignDetail(id) {
  tplInto("tpl-campaign-detail");
  $("#backBtn").addEventListener("click", renderCampaigns);
  $$(".status-row [data-act]").forEach(btn => {
    btn.addEventListener("click", () => changeStatus(id, btn.dataset.act));
  });
  $("#refreshStats").addEventListener("click", () => loadDetail(id));
  await loadDetail(id);
}

async function loadDetail(id) {
  try {
    // get campaign meta
    const r = await fetch("/api/campaigns");
    if (r.status === 401) return renderLogin();
    const data = await r.json();
    const c = (data.campaigns || []).find(x => x.id === id);
    if (!c) { app.innerHTML = '<div class="card">الحملة غير موجودة.</div>'; return; }
    $("#cdTitle").textContent = c.customer_label;
    const st = $("#cdStatus");
    st.className = "pill " + c.status; st.textContent = statusAr(c.status);

    // stats
    const sr = await fetch(`/api/stats?campaign_id=${id}`);
    const sd = await sr.json();
    const counts = sd.counts || {};
    const sent = counts.sent || 0, failed = counts.failed || 0;
    const pending = counts.pending || 0, total = counts.total || 0;
    $("#cdCounts").innerHTML = `
      ${cell("الإجمالي", total)}
      ${cell("مُرسَل", sent)}
      ${cell("فشل", failed)}
      ${cell("متبقٍ", pending)}
    `;
    const pct = total ? Math.round(((sent + failed) / total) * 100) : 0;
    $("#cdBar").style.width = pct + "%";
  } catch (e) {
    console.error(e);
  }
}

async function changeStatus(id, status) {
  await fetch(`/api/campaigns?id=${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  loadDetail(id);
}

// ---------- utils ----------
const cell = (l, v) => `<div class="count-cell"><div class="v">${v}</div><div class="l">${l}</div></div>`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, m => ({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const shortDate = (iso) => iso ? new Date(iso).toLocaleString("ar") : "—";

init();
