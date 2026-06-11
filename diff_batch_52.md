# Diff Reference for Batch 52

```diff
diff --git a/admin/index.html b/admin/index.html
index d5ce864..b525f53 100644
--- a/admin/index.html
+++ b/admin/index.html
@@ -2930,6 +2930,144 @@
 
     <!-- /Tab: Dynamics 365 -->
 
+    <!-- Tab: Settings (auto-generated from the config registry · V.3) -->
+    <div id="panel-settings" x-show="adminTab === 'settings'" x-cloak class="space-y-8" x-data="settingsPanel" x-init="init()">
+      <div class="border-b border-slate-200 pb-2.5 mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
+        <div>
+          <h2 class="text-xl font-bold font-hanken tracking-tight bg-gradient-to-r from-blue-700 via-indigo-600 to-purple-600 bg-clip-text text-transparent uppercase">System Settings</h2>
+          <p class="text-xs text-slate-500 mt-1">Auto-generated from the configuration registry · effective values + source &amp; reload-class badges · secrets are write-only</p>
+        </div>
+        <span class="self-start sm:self-auto text-[10px] font-mono text-slate-600 uppercase tracking-widest font-bold bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">CONFIG REGISTRY</span>
+      </div>
+
+      <!-- Toolbar: search / filter / refresh -->
+      <section class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
+        <div class="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-slate-100 bg-slate-50">
+          <div class="flex flex-wrap items-center gap-3">
+            <input type="search" x-model.debounce.300ms="search" placeholder="Search keys or descriptions…"
+                   class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-700 w-64 focus:outline-none focus:ring-2 focus:ring-indigo-200">
+            <label class="flex items-center gap-1.5 text-[11px] font-semibold text-slate-600 cursor-pointer">
+              <input type="checkbox" x-model="overridesOnly" class="rounded border-slate-300 text-indigo-600">
+              Changed from default only
+            </label>
+          </div>
+          <div class="flex gap-2">
+            <button type="button" @click="expandAll()"
+                    class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:border-slate-400 transition shadow-sm">Expand all</button>
+            <button type="button" @click="collapseAll()"
+                    class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:border-slate-400 transition shadow-sm">Collapse all</button>
+            <button type="button" @click="fetchSettings()"
+                    class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:border-slate-400 transition shadow-sm">Refresh</button>
+          </div>
+        </div>
+        <!-- Legend -->
+        <div class="px-5 py-2.5 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[10px] text-slate-500">
+          <span class="font-bold uppercase tracking-wider text-slate-400">Source:</span>
+          <span class="inline-flex items-center gap-1"><span class="px-1.5 py-0.5 rounded font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">store</span> DB override</span>
+          <span class="inline-flex items-center gap-1"><span class="px-1.5 py-0.5 rounded font-bold bg-sky-50 text-sky-700 border border-sky-200">env</span> environment</span>
+          <span class="inline-flex items-center gap-1"><span class="px-1.5 py-0.5 rounded font-bold bg-slate-100 text-slate-600 border border-slate-200">default</span> registry default</span>
+          <span class="font-bold uppercase tracking-wider text-slate-400 ml-2">Reload:</span>
+          <span class="inline-flex items-center gap-1"><span class="h-4 w-4 inline-flex items-center justify-center rounded font-bold bg-emerald-100 text-emerald-700">H</span> hot (live)</span>
+          <span class="inline-flex items-center gap-1"><span class="h-4 w-4 inline-flex items-center justify-center rounded font-bold bg-amber-100 text-amber-800">W</span> warm (reload)</span>
+          <span class="inline-flex items-center gap-1"><span class="h-4 w-4 inline-flex items-center justify-center rounded font-bold bg-slate-200 text-slate-600">C</span> cold (restart)</span>
+        </div>
+      </section>
+
+      <div x-show="loading" class="px-5 py-10 text-center text-xs text-slate-400">Loading settings registry…</div>
+      <div x-show="!loading && filteredSections.length === 0" class="px-5 py-10 text-center text-xs text-slate-400">No settings match the current filter.</div>
+
+      <!-- Section accordions -->
+      <template x-for="sec in filteredSections" :key="sec.section">
+        <section class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
+          <button type="button" @click="toggleSection(sec.section)"
+                  class="w-full flex items-center justify-between px-5 py-3 border-b border-slate-100 bg-slate-50 text-left hover:bg-slate-100 transition">
+            <div class="flex items-center gap-2.5">
+              <span class="text-slate-400 text-xs transition-transform" :class="isOpen(sec.section) ? 'rotate-90' : ''">▶</span>
+              <h3 class="text-[11px] font-bold uppercase tracking-widest text-slate-700" x-text="sec.section"></h3>
+            </div>
+            <span class="text-[10px] font-mono text-slate-400" x-text="sec.keys.length + (sec.keys.length === 1 ? ' key' : ' keys')"></span>
+          </button>
+
+          <div x-show="isOpen(sec.section)" x-cloak class="divide-y divide-slate-100">
+            <template x-for="field in sec.keys" :key="field.key">
+              <div class="px-5 py-4 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3 lg:gap-6">
+                <!-- Field meta -->
+                <div class="min-w-0">
+                  <div class="flex items-center flex-wrap gap-2">
+                    <span class="font-mono text-xs font-bold text-slate-800 break-all" x-text="field.key"></span>
+                    <!-- reload-class chip (H/W/C) -->
+                    <span class="h-4 w-4 inline-flex items-center justify-center rounded text-[10px] font-bold"
+                          :class="reloadChipClass(field.reload_class)"
+                          :title="reloadChipTitle(field.reload_class)"
+                          x-text="reloadChipLabel(field.reload_class)"></span>
+                    <!-- source badge -->
+                    <span class="px-1.5 py-0.5 rounded text-[10px] font-bold border"
+                          :class="sourceBadgeClass(field.source)"
+                          x-text="field.source"></span>
+                    <!-- prod-locked lock -->
+                    <span x-show="field.prod_locked"
+                          class="px-1.5 py-0.5 rounded text-[10px] font-bold border bg-rose-50 text-rose-700 border-rose-200"
+                          title="Forbidden in production — set via secret manager / restart">🔒 locked</span>
+                  </div>
+                  <p class="text-[11px] text-slate-500 mt-1" x-text="field.description"></p>
+                  <p class="text-[9px] font-mono text-slate-400 mt-1"
+                     x-show="field.updated_at"
+                     x-text="'updated by ' + (field.updated_by || '—') + ' · ' + fmtIsoShort(field.updated_at)"></p>
+                </div>
+
+                <!-- Type-aware input (basic edit affordance · full dirty-tracking deferred to Batch 53) -->
+                <div class="min-w-0 flex flex-col gap-1.5">
+                  <!-- bool toggle -->
+                  <template x-if="field.type === 'bool'">
+                    <label class="flex items-center gap-2 cursor-pointer">
+                      <input type="checkbox" :checked="!!field.effective_value" disabled
+                             class="rounded border-slate-300 text-indigo-600 opacity-70">
+                      <span class="text-xs font-mono text-slate-700" x-text="field.effective_value ? 'true' : 'false'"></span>
+                    </label>
+                  </template>
+                  <!-- number (int/float) -->
+                  <template x-if="field.type === 'int' || field.type === 'float'">
+                    <input type="number" :value="field.effective_value"
+                           :step="field.type === 'float' ? 'any' : '1'"
+                           :min="field.validation && field.validation.min !== undefined ? field.validation.min : null"
+                           :disabled="field.prod_locked"
+                           class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-800 disabled:bg-slate-50 disabled:text-slate-400">
+                  </template>
+                  <!-- secret · write-only -->
+                  <template x-if="field.type === 'secret'">
+                    <div class="flex items-center gap-2">
+                      <span class="text-xs font-mono text-slate-500" x-text="field.effective_value ? '•••• set (write-only)' : 'unset'"></span>
+                    </div>
+                  </template>
+                  <!-- list -->
+                  <template x-if="field.type === 'list'">
+                    <input type="text" :value="Array.isArray(field.effective_value) ? field.effective_value.join(', ') : (field.effective_value || '')"
+                           :disabled="field.prod_locked"
+                           class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-800 disabled:bg-slate-50 disabled:text-slate-400">
+                  </template>
+                  <!-- str (and any other type) · text -->
+                  <template x-if="field.type === 'str'">
+                    <input type="text" :value="field.effective_value === null ? '' : field.effective_value"
+                           :disabled="field.prod_locked"
+                           class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-800 disabled:bg-slate-50 disabled:text-slate-400">
+                  </template>
+                  <!-- validation hint -->
+                  <p class="text-[9px] font-mono text-slate-400"
+                     x-show="field.validation && field.validation.min !== undefined"
+                     x-text="'min: ' + (field.validation ? field.validation.min : '')"></p>
+                </div>
+              </div>
+            </template>
+          </div>
+        </section>
+      </template>
+
+      <p class="text-[10px] text-slate-400 text-center pt-2">
+        Read &amp; render only — dirty-tracking, batch apply (PATCH), reset and reload affordances are introduced in a later batch.
+      </p>
+    </div>
+    <!-- /Tab: Settings -->
+
     </div><!-- /inner max-width column -->
 
   </main>
@@ -3280,6 +3418,7 @@
           { slug: 'consolidation', label: 'Consolidation' },
           { slug: 'cognitive', label: 'Cognitive' },
           { slug: 'datastores', label: 'Datastores' },
+          { slug: 'settings', label: 'Settings' },
           { slug: 'tools', label: 'Tools' },
           { slug: 'glass-profile', label: 'Glass Profile' },
           { slug: 'maintenance', label: 'Maintenance' },
@@ -5230,6 +5369,111 @@
         }
       }));
 
+      /* ---------- System Settings · auto-generated config registry (Part V.3) ----------
+         Read & render only: loads /api/admin/settings (grouped by section), renders each
+         field with its effective value, source badge, and reload-class chip. Mirrors the
+         d365Panel pattern (signedFetch + section accordions). Dirty-tracking / batch PATCH
+         apply / reset / reload are introduced in a later batch. */
+      Alpine.data('settingsPanel', () => ({
+        sections: [],
+        loading: false,
+        search: '',
+        overridesOnly: false,
+        openSections: {},   // section name -> bool (collapsed/expanded)
+
+        async init() {
+          await this.fetchSettings();
+        },
+
+        async fetchSettings() {
+          this.loading = true;
+          try {
+            const resp = await signedFetch(undefined, '/api/admin/settings');
+            if (!resp.ok) throw new Error((await resp.json()).error || 'Failed to load settings');
+            const data = await resp.json();
+            this.sections = data.sections || [];
+            // Default: first section expanded, the rest collapsed.
+            this.sections.forEach((sec, i) => {
+              if (this.openSections[sec.section] === undefined) {
+                this.openSections[sec.section] = i === 0;
+              }
+            });
+          } catch (err) {
+            trimcpShellToast(err.message || String(err), 'error');
+          } finally {
+            this.loading = false;
+          }
+        },
+
+        get filteredSections() {
+          const q = this.search.trim().toLowerCase();
+          const out = [];
+          for (const sec of this.sections) {
+            let keys = sec.keys || [];
+            if (q) {
+              keys = keys.filter(f =>
+                (f.key && f.key.toLowerCase().includes(q)) ||
+                (f.description && f.description.toLowerCase().includes(q))
+              );
+            }
+            if (this.overridesOnly) {
+              keys = keys.filter(f => f.source === 'store');
+            }
+            if (keys.length) out.push({ section: sec.section, keys });
+          }
+          return out;
+        },
+
+        isOpen(section) {
+          // When searching, force-expand so matches are visible.
+          if (this.search.trim()) return true;
+          return !!this.openSections[section];
+        },
+        toggleSection(section) {
+          this.openSections[section] = !this.openSections[section];
+        },
+        expandAll() {
+          this.sections.forEach(sec => { this.openSections[sec.section] = true; });
+        },
+        collapseAll() {
+          this.sections.forEach(sec => { this.openSections[sec.section] = false; });
+        },
+
+        // --- badge / chip helpers -------------------------------------------------
+        reloadChipLabel(cls) {
+          return ({ HOT: 'H', WARM: 'W', COLD: 'C' })[cls] || '?';
+        },
+        reloadChipTitle(cls) {
+          return ({
+            HOT: 'HOT — applies immediately (read at use)',
+            WARM: 'WARM — needs a reload action to apply',
+            COLD: 'COLD — requires a restart to apply',
+          })[cls] || cls;
+        },
+        reloadChipClass(cls) {
+          return ({
+            HOT: 'bg-emerald-100 text-emerald-700',
+            WARM: 'bg-amber-100 text-amber-800',
+            COLD: 'bg-slate-200 text-slate-600',
+          })[cls] || 'bg-slate-100 text-slate-500';
+        },
+        sourceBadgeClass(source) {
+          return ({
+            store: 'bg-indigo-50 text-indigo-700 border-indigo-200',
+            env: 'bg-sky-50 text-sky-700 border-sky-200',
+            default: 'bg-slate-100 text-slate-600 border-slate-200',
+          })[source] || 'bg-slate-100 text-slate-600 border-slate-200';
+        },
+
+        fmtIsoShort(iso) {
+          if (!iso) return '—';
+          try {
+            const d = new Date(iso);
+            return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
+          } catch (_) { return iso; }
+        },
+      }));
+
       /* ---------- Glass Profile · Belief Timeline (Phase II.5) ---------- */
       Alpine.data('glassProfileTimeline', () => ({
         timeline: [],
```
