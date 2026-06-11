# Diff Reference for Batch 53

```diff
diff --git a/admin/index.html b/admin/index.html
index b525f53..3fec420 100644
--- a/admin/index.html
+++ b/admin/index.html
@@ -2940,6 +2940,21 @@
         <span class="self-start sm:self-auto text-[10px] font-mono text-slate-600 uppercase tracking-widest font-bold bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">CONFIG REGISTRY</span>
       </div>
 
+      <!-- Restart-required banner (fed by GET /api/admin/settings/pending) -->
+      <div x-show="pendingRestartKeys.length > 0" x-cloak
+           class="rounded-xl border border-slate-300 bg-slate-100 px-5 py-3 flex flex-wrap items-center justify-between gap-3">
+        <div class="flex items-center gap-2.5 min-w-0">
+          <span class="text-slate-500 text-lg">🔒</span>
+          <div class="min-w-0">
+            <p class="text-xs font-bold text-slate-700"
+               x-text="'Restart required to apply ' + pendingRestartKeys.length + (pendingRestartKeys.length === 1 ? ' setting' : ' settings')"></p>
+            <p class="text-[10px] font-mono text-slate-500 break-all" x-text="pendingRestartKeys.join(', ')"></p>
+          </div>
+        </div>
+        <button type="button" @click="fetchPending()"
+                class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:border-slate-400 transition shadow-sm">Re-check</button>
+      </div>
+
       <!-- Toolbar: search / filter / refresh -->
       <section class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
         <div class="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-slate-100 bg-slate-50">
@@ -2958,6 +2973,8 @@
                     class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:border-slate-400 transition shadow-sm">Collapse all</button>
             <button type="button" @click="fetchSettings()"
                     class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:border-slate-400 transition shadow-sm">Refresh</button>
+            <button type="button" @click="exportEffective()"
+                    class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:border-slate-400 transition shadow-sm">Export effective config</button>
           </div>
         </div>
         <!-- Legend -->
@@ -2979,21 +2996,31 @@
       <!-- Section accordions -->
       <template x-for="sec in filteredSections" :key="sec.section">
         <section class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
-          <button type="button" @click="toggleSection(sec.section)"
-                  class="w-full flex items-center justify-between px-5 py-3 border-b border-slate-100 bg-slate-50 text-left hover:bg-slate-100 transition">
-            <div class="flex items-center gap-2.5">
+          <div class="w-full flex items-center justify-between px-5 py-3 border-b border-slate-100 bg-slate-50 hover:bg-slate-100 transition">
+            <button type="button" @click="toggleSection(sec.section)" class="flex items-center gap-2.5 text-left min-w-0">
               <span class="text-slate-400 text-xs transition-transform" :class="isOpen(sec.section) ? 'rotate-90' : ''">▶</span>
               <h3 class="text-[11px] font-bold uppercase tracking-widest text-slate-700" x-text="sec.section"></h3>
+            </button>
+            <div class="flex items-center gap-3">
+              <!-- per-domain reload affordance: shown when this section has pending_reload keys -->
+              <template x-for="dom in pendingReloadDomainsForSection(sec)" :key="dom">
+                <button type="button" @click="reloadDomain(dom)" :disabled="reloadingDomains[dom]"
+                        class="rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1 text-[10px] font-bold text-amber-800 hover:bg-amber-100 transition shadow-sm disabled:opacity-50"
+                        x-text="(reloadingDomains[dom] ? 'Reloading ' : 'Apply (reload ') + dom + (reloadingDomains[dom] ? '…' : ')')"></button>
+              </template>
+              <span class="text-[10px] font-mono text-slate-400" x-text="sec.keys.length + (sec.keys.length === 1 ? ' key' : ' keys')"></span>
             </div>
-            <span class="text-[10px] font-mono text-slate-400" x-text="sec.keys.length + (sec.keys.length === 1 ? ' key' : ' keys')"></span>
-          </button>
+          </div>
 
           <div x-show="isOpen(sec.section)" x-cloak class="divide-y divide-slate-100">
             <template x-for="field in sec.keys" :key="field.key">
-              <div class="px-5 py-4 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3 lg:gap-6">
+              <div class="px-5 py-4 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3 lg:gap-6"
+                   :class="isDirty(field.key) ? 'bg-indigo-50/40' : ''">
                 <!-- Field meta -->
                 <div class="min-w-0">
                   <div class="flex items-center flex-wrap gap-2">
+                    <!-- modified dot -->
+                    <span x-show="isDirty(field.key)" class="h-2 w-2 rounded-full bg-indigo-500 shrink-0" title="Modified — pending apply"></span>
                     <span class="font-mono text-xs font-bold text-slate-800 break-all" x-text="field.key"></span>
                     <!-- reload-class chip (H/W/C) -->
                     <span class="h-4 w-4 inline-flex items-center justify-center rounded text-[10px] font-bold"
@@ -3008,53 +3035,107 @@
                     <span x-show="field.prod_locked"
                           class="px-1.5 py-0.5 rounded text-[10px] font-bold border bg-rose-50 text-rose-700 border-rose-200"
                           title="Forbidden in production — set via secret manager / restart">🔒 locked</span>
+                    <!-- per-key apply result chip (from the 207 response) -->
+                    <template x-if="resultFor(field.key)">
+                      <span class="px-1.5 py-0.5 rounded text-[10px] font-bold border inline-flex items-center gap-1"
+                            :class="resultChipClass(resultFor(field.key).status)"
+                            :title="resultFor(field.key).error || ''">
+                        <span x-text="resultChipLabel(resultFor(field.key).status)"></span>
+                      </span>
+                    </template>
+                    <!-- revert-this-field -->
+                    <button type="button" x-show="isDirty(field.key)" @click="revertField(field.key)"
+                            class="text-[10px] font-bold text-slate-500 hover:text-rose-600 underline decoration-dotted">revert</button>
                   </div>
                   <p class="text-[11px] text-slate-500 mt-1" x-text="field.description"></p>
                   <p class="text-[9px] font-mono text-slate-400 mt-1"
                      x-show="field.updated_at"
                      x-text="'updated by ' + (field.updated_by || '—') + ' · ' + fmtIsoShort(field.updated_at)"></p>
+                  <!-- rejected inline error (code/message) -->
+                  <template x-if="resultFor(field.key) && resultFor(field.key).status === 'rejected'">
+                    <p class="text-[10px] font-semibold text-rose-600 mt-1"
+                       x-text="'✕ ' + (resultFor(field.key).status_code ? '[' + resultFor(field.key).status_code + '] ' : '') + (resultFor(field.key).error || 'rejected')"></p>
+                  </template>
+                  <!-- 409 optimistic-lock conflict resolution -->
+                  <template x-if="hasConflict(field.key)">
+                    <div class="mt-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2">
+                      <p class="text-[10px] font-bold text-amber-800">Changed by someone else since you loaded it.</p>
+                      <p class="text-[10px] text-amber-700 mt-0.5" x-text="'now: updated by ' + (field.updated_by || '—') + ' · ' + fmtIsoShort(field.updated_at)"></p>
+                      <div class="flex gap-2 mt-1.5">
+                        <button type="button" @click="reloadField(field.key)"
+                                class="rounded border border-amber-400 bg-white px-2 py-0.5 text-[10px] font-bold text-amber-800 hover:bg-amber-100">Reload field</button>
+                        <button type="button" @click="overwriteField(field.key)"
+                                class="rounded border border-rose-300 bg-white px-2 py-0.5 text-[10px] font-bold text-rose-700 hover:bg-rose-50">Overwrite anyway</button>
+                      </div>
+                    </div>
+                  </template>
                 </div>
 
-                <!-- Type-aware input (basic edit affordance · full dirty-tracking deferred to Batch 53) -->
+                <!-- Type-aware input · dirty-tracked via pending[] -->
                 <div class="min-w-0 flex flex-col gap-1.5">
                   <!-- bool toggle -->
                   <template x-if="field.type === 'bool'">
                     <label class="flex items-center gap-2 cursor-pointer">
-                      <input type="checkbox" :checked="!!field.effective_value" disabled
-                             class="rounded border-slate-300 text-indigo-600 opacity-70">
-                      <span class="text-xs font-mono text-slate-700" x-text="field.effective_value ? 'true' : 'false'"></span>
+                      <input type="checkbox" :checked="!!editValue(field)" :disabled="field.prod_locked"
+                             @change="setPending(field, $event.target.checked)"
+                             class="rounded border-slate-300 text-indigo-600 disabled:opacity-50">
+                      <span class="text-xs font-mono text-slate-700" x-text="editValue(field) ? 'true' : 'false'"></span>
                     </label>
                   </template>
                   <!-- number (int/float) -->
                   <template x-if="field.type === 'int' || field.type === 'float'">
-                    <input type="number" :value="field.effective_value"
+                    <input type="number" :value="editValue(field)"
                            :step="field.type === 'float' ? 'any' : '1'"
                            :min="field.validation && field.validation.min !== undefined ? field.validation.min : null"
                            :disabled="field.prod_locked"
+                           @input="setPending(field, $event.target.value === '' ? null : Number($event.target.value))"
                            class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-800 disabled:bg-slate-50 disabled:text-slate-400">
                   </template>
-                  <!-- secret · write-only -->
+                  <!-- secret · write-only (Rotate reveals an input; Clear calls reset) -->
                   <template x-if="field.type === 'secret'">
-                    <div class="flex items-center gap-2">
-                      <span class="text-xs font-mono text-slate-500" x-text="field.effective_value ? '•••• set (write-only)' : 'unset'"></span>
+                    <div class="flex flex-col gap-1.5">
+                      <div class="flex items-center gap-2 flex-wrap">
+                        <span class="text-xs font-mono text-slate-500" x-text="field.effective_value ? '•••• set (write-only)' : 'unset'"></span>
+                        <template x-if="!field.prod_locked">
+                          <div class="flex items-center gap-2">
+                            <button type="button" x-show="!isSecretRotating(field.key)" @click="startRotate(field.key)"
+                                    class="rounded border border-slate-300 bg-white px-2 py-0.5 text-[10px] font-bold text-slate-700 hover:border-slate-400">Rotate</button>
+                            <button type="button" x-show="field.effective_value && field.source === 'store'" @click="clearSecret(field.key)"
+                                    class="rounded border border-rose-300 bg-white px-2 py-0.5 text-[10px] font-bold text-rose-700 hover:bg-rose-50">Clear</button>
+                          </div>
+                        </template>
+                      </div>
+                      <template x-if="isSecretRotating(field.key)">
+                        <div class="flex items-center gap-2">
+                          <input type="password" autocomplete="new-password" placeholder="Enter new secret value"
+                                 :value="editValue(field) === '••••set' ? '' : (editValue(field) || '')"
+                                 @input="setPending(field, $event.target.value)"
+                                 class="rounded-lg border border-indigo-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-800 flex-1">
+                          <button type="button" @click="cancelRotate(field.key)"
+                                  class="text-[10px] font-bold text-slate-500 hover:text-slate-700">cancel</button>
+                        </div>
+                      </template>
                     </div>
                   </template>
                   <!-- list -->
                   <template x-if="field.type === 'list'">
-                    <input type="text" :value="Array.isArray(field.effective_value) ? field.effective_value.join(', ') : (field.effective_value || '')"
+                    <input type="text" :value="Array.isArray(editValue(field)) ? editValue(field).join(', ') : (editValue(field) || '')"
                            :disabled="field.prod_locked"
+                           @input="setPending(field, $event.target.value.split(',').map(s => s.trim()).filter(s => s.length))"
                            class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-800 disabled:bg-slate-50 disabled:text-slate-400">
                   </template>
                   <!-- str (and any other type) · text -->
                   <template x-if="field.type === 'str'">
-                    <input type="text" :value="field.effective_value === null ? '' : field.effective_value"
+                    <input type="text" :value="editValue(field) === null ? '' : editValue(field)"
                            :disabled="field.prod_locked"
+                           @input="setPending(field, $event.target.value)"
                            class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-mono text-slate-800 disabled:bg-slate-50 disabled:text-slate-400">
                   </template>
                   <!-- validation hint -->
                   <p class="text-[9px] font-mono text-slate-400"
                      x-show="field.validation && field.validation.min !== undefined"
                      x-text="'min: ' + (field.validation ? field.validation.min : '')"></p>
+                  <p class="text-[9px] font-mono text-slate-400" x-show="field.reload_class === 'COLD' && isDirty(field.key)">takes effect after restart</p>
                 </div>
               </div>
             </template>
@@ -3062,8 +3143,61 @@
         </section>
       </template>
 
+      <!-- Sticky "Review N changes" footer -->
+      <div x-show="dirtyCount > 0" x-cloak
+           class="sticky bottom-4 z-20 mx-auto max-w-3xl rounded-xl border border-indigo-300 bg-white shadow-lg px-5 py-3 flex items-center justify-between gap-4">
+        <span class="text-xs font-bold text-slate-700"
+              x-text="dirtyCount + (dirtyCount === 1 ? ' pending change' : ' pending changes')"></span>
+        <div class="flex gap-2">
+          <button type="button" @click="discardAll()"
+                  class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[11px] font-bold text-slate-600 hover:border-slate-400 transition">Discard</button>
+          <button type="button" @click="openConfirm()"
+                  class="rounded-lg bg-indigo-600 px-4 py-1.5 text-[11px] font-bold text-white hover:bg-indigo-700 transition shadow-sm"
+                  x-text="'Review ' + dirtyCount + ' change' + (dirtyCount === 1 ? '' : 's')"></button>
+        </div>
+      </div>
+
+      <!-- Confirm-diff modal -->
+      <div x-show="confirmOpen" x-cloak
+           class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" @keydown.escape.window="confirmOpen = false">
+        <div class="w-full max-w-2xl rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden" @click.away="confirmOpen = false">
+          <div class="px-6 py-4 border-b border-slate-100 bg-slate-50">
+            <h3 class="text-sm font-bold text-slate-800">Review configuration changes</h3>
+            <p class="text-[11px] text-slate-500 mt-0.5" x-text="diffRows.length + ' key(s) · single PATCH /api/admin/settings'"></p>
+          </div>
+          <div class="px-6 py-4 max-h-[50vh] overflow-y-auto space-y-2.5">
+            <template x-for="row in diffRows" :key="row.key">
+              <div class="rounded-lg border border-slate-200 px-3 py-2">
+                <div class="flex items-center gap-2">
+                  <span class="font-mono text-xs font-bold text-slate-800 break-all" x-text="row.key"></span>
+                  <span class="h-4 w-4 inline-flex items-center justify-center rounded text-[10px] font-bold"
+                        :class="reloadChipClass(row.reload_class)" x-text="reloadChipLabel(row.reload_class)"></span>
+                </div>
+                <div class="flex items-center gap-2 mt-1 text-[11px] font-mono">
+                  <span class="text-rose-600 break-all" x-text="row.oldDisplay"></span>
+                  <span class="text-slate-400">→</span>
+                  <span class="text-emerald-700 break-all" x-text="row.newDisplay"></span>
+                </div>
+              </div>
+            </template>
+            <div>
+              <label class="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Reason (optional)</label>
+              <textarea x-model="reason" rows="2" placeholder="Why are you making this change?"
+                        class="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-200"></textarea>
+            </div>
+          </div>
+          <div class="px-6 py-3 border-t border-slate-100 bg-slate-50 flex justify-end gap-2">
+            <button type="button" @click="confirmOpen = false"
+                    class="rounded-lg border border-slate-300 bg-white px-4 py-1.5 text-[11px] font-bold text-slate-600 hover:border-slate-400 transition">Cancel</button>
+            <button type="button" @click="applyChanges()" :disabled="applying"
+                    class="rounded-lg bg-indigo-600 px-4 py-1.5 text-[11px] font-bold text-white hover:bg-indigo-700 transition shadow-sm disabled:opacity-50"
+                    x-text="applying ? 'Applying…' : 'Confirm &amp; apply'"></button>
+          </div>
+        </div>
+      </div>
+
       <p class="text-[10px] text-slate-400 text-center pt-2">
-        Read &amp; render only — dirty-tracking, batch apply (PATCH), reset and reload affordances are introduced in a later batch.
+        Edits accumulate into a pending set · review the diff before a single batch PATCH · per-key results render straight from the 207 response.
       </p>
     </div>
     <!-- /Tab: Settings -->
@@ -5381,8 +5515,29 @@
         overridesOnly: false,
         openSections: {},   // section name -> bool (collapsed/expanded)
 
+        // --- V.3a interaction state ---------------------------------------------
+        pending: {},            // key -> { value, expected_updated_at, reload_class, is_secret, type, oldValue }
+        results: {},            // key -> { status, error?, status_code? } from the 207 response
+        secretRotating: {},     // key -> bool (Rotate revealed an input)
+        pendingRestartKeys: [], // from GET /api/admin/settings/pending
+        reloadingDomains: {},   // domain -> bool (reload in flight)
+        confirmOpen: false,
+        applying: false,
+        reason: '',
+
+        // Map a registry section name to its WARM reload domain (see /reload VALID_DOMAINS).
+        SECTION_DOMAIN: {
+          'Cron intervals': 'cron',
+          'LLM / Cognitive': 'llm',
+          'Embeddings & edge': 'llm',
+          'Re-embedding worker': 'llm',
+          'Observability': 'observability',
+          'A2A / JWT': 'a2a',
+        },
+
         async init() {
           await this.fetchSettings();
+          await this.fetchPending();
         },
 
         async fetchSettings() {
@@ -5405,6 +5560,63 @@
           }
         },
 
+        async fetchPending() {
+          try {
+            const resp = await signedFetch(undefined, '/api/admin/settings/pending');
+            if (!resp.ok) return;
+            const data = await resp.json();
+            this.pendingRestartKeys = data.keys || [];
+          } catch (_) { /* non-fatal */ }
+        },
+
+        // --- find a field across all loaded sections -----------------------------
+        findField(key) {
+          for (const sec of this.sections) {
+            for (const f of (sec.keys || [])) {
+              if (f.key === key) return f;
+            }
+          }
+          return null;
+        },
+
+        // --- dirty-tracking -------------------------------------------------------
+        isDirty(key) { return Object.prototype.hasOwnProperty.call(this.pending, key); },
+        get dirtyCount() { return Object.keys(this.pending).length; },
+
+        // The value to render in the input: pending edit if dirty, else the effective value.
+        editValue(field) {
+          if (this.isDirty(field.key)) return this.pending[field.key].value;
+          return field.effective_value;
+        },
+
+        setPending(field, value) {
+          // Clearing back to the original value drops it from the pending set.
+          const original = field.effective_value;
+          if (!field.is_secret && JSON.stringify(value) === JSON.stringify(original)) {
+            delete this.pending[field.key];
+            return;
+          }
+          this.pending[field.key] = {
+            value,
+            expected_updated_at: field.updated_at || null,
+            reload_class: field.reload_class,
+            is_secret: !!field.is_secret,
+            type: field.type,
+            oldValue: original,
+          };
+          // A fresh edit supersedes any stale per-key result for that field.
+          delete this.results[field.key];
+        },
+
+        revertField(key) {
+          delete this.pending[key];
+          delete this.secretRotating[key];
+        },
+        discardAll() {
+          this.pending = {};
+          this.secretRotating = {};
+        },
+
         get filteredSections() {
           const q = this.search.trim().toLowerCase();
           const out = [];
@@ -5439,6 +5651,220 @@
           this.sections.forEach(sec => { this.openSections[sec.section] = false; });
         },
 
+        // --- confirm-diff modal ---------------------------------------------------
+        openConfirm() {
+          if (this.dirtyCount === 0) return;
+          this.confirmOpen = true;
+        },
+
+        // Render `key: old → new` rows; secrets shown as set → •••• / ••••→ rotated.
+        get diffRows() {
+          const rows = [];
+          for (const key of Object.keys(this.pending)) {
+            const p = this.pending[key];
+            let oldDisplay, newDisplay;
+            if (p.is_secret) {
+              oldDisplay = p.oldValue ? 'set' : '••••';
+              newDisplay = (p.value === null || p.value === '') ? '••••' : 'rotated';
+            } else {
+              oldDisplay = this.fmtValue(p.oldValue);
+              newDisplay = this.fmtValue(p.value);
+            }
+            rows.push({ key, reload_class: p.reload_class, oldDisplay, newDisplay });
+          }
+          return rows;
+        },
+
+        fmtValue(v) {
+          if (v === null || v === undefined) return '∅';
+          if (Array.isArray(v)) return '[' + v.join(', ') + ']';
+          if (typeof v === 'boolean') return v ? 'true' : 'false';
+          if (v === '') return '""';
+          return String(v);
+        },
+
+        // Build + send the single batch PATCH; render the 207 per-key results honestly.
+        async applyChanges() {
+          if (this.dirtyCount === 0 || this.applying) return;
+          this.applying = true;
+          const settings = {};
+          for (const key of Object.keys(this.pending)) {
+            const p = this.pending[key];
+            settings[key] = { value: p.value, expected_updated_at: p.expected_updated_at };
+          }
+          try {
+            const resp = await signedFetch(undefined, '/api/admin/settings', {
+              method: 'PATCH',
+              body: { settings, reason: this.reason || '' },
+            });
+            const data = await resp.json();
+            // 207 (and any non-2xx batch error) → render the per-key map.
+            const map = data.settings || {};
+            const appliedKeys = [];
+            for (const key of Object.keys(map)) {
+              this.results[key] = map[key];
+              if (map[key].status && map[key].status !== 'rejected') appliedKeys.push(key);
+            }
+            if (!resp.ok && !data.settings) {
+              throw new Error(data.error || ('PATCH failed (HTTP ' + resp.status + ')'));
+            }
+            // Clear successfully-acted keys from the pending set; keep rejected/conflict ones.
+            for (const key of appliedKeys) {
+              this.revertField(key);
+            }
+            const anyRejected = Object.values(map).some(r => r.status === 'rejected');
+            if (anyRejected) {
+              trimcpShellToast('Some changes were rejected — see per-key errors', 'error');
+            } else {
+              this.confirmOpen = false;
+              this.reason = '';
+              trimcpShellToast('Changes applied', 'success');
+            }
+            // Re-read so source badges / updated_at / effective values reflect the store.
+            await this.fetchSettings();
+            await this.fetchPending();
+          } catch (err) {
+            trimcpShellToast(err.message || String(err), 'error');
+          } finally {
+            this.applying = false;
+          }
+        },
+
+        // --- per-key 207 result rendering ----------------------------------------
+        resultFor(key) { return this.results[key] || null; },
+        resultChipLabel(status) {
+          return ({
+            applied: '✓ live',
+            pending_reload: '⟳ pending reload',
+            pending_restart: '🔒 restart',
+            rejected: '✕ rejected',
+          })[status] || status;
+        },
+        resultChipClass(status) {
+          return ({
+            applied: 'bg-emerald-50 text-emerald-700 border-emerald-200',
+            pending_reload: 'bg-amber-50 text-amber-800 border-amber-300',
+            pending_restart: 'bg-slate-100 text-slate-600 border-slate-300',
+            rejected: 'bg-rose-50 text-rose-700 border-rose-200',
+          })[status] || 'bg-slate-100 text-slate-600 border-slate-200';
+        },
+
+        // --- 409 optimistic-lock conflict -----------------------------------------
+        hasConflict(key) {
+          const r = this.results[key];
+          return !!(r && r.status === 'rejected' && r.status_code === 409);
+        },
+        async reloadField(key) {
+          // Re-fetch current state so the admin re-decides against the live value.
+          delete this.results[key];
+          delete this.pending[key];
+          await this.fetchSettings();
+        },
+        overwriteField(key) {
+          // Re-stage with the just-fetched updated_at so the next PATCH won't conflict.
+          const field = this.findField(key);
+          if (!field) return;
+          delete this.results[key];
+          this.pending[key] = {
+            value: this.pending[key] ? this.pending[key].value : field.effective_value,
+            expected_updated_at: field.updated_at || null,
+            reload_class: field.reload_class,
+            is_secret: !!field.is_secret,
+            type: field.type,
+            oldValue: field.effective_value,
+          };
+        },
+
+        // --- secret rotate / clear ------------------------------------------------
+        isSecretRotating(key) { return !!this.secretRotating[key]; },
+        startRotate(key) {
+          this.secretRotating[key] = true;
+          const field = this.findField(key);
+          if (field) this.setPending(field, '');
+        },
+        cancelRotate(key) {
+          this.secretRotating[key] = false;
+          delete this.pending[key];
+        },
+        async clearSecret(key) {
+          if (!confirm('Clear this secret? This removes the store override (reset to env/default).')) return;
+          try {
+            const resp = await signedFetch(undefined, '/api/admin/settings/reset', {
+              method: 'POST',
+              body: { keys: [key] },
+            });
+            const data = await resp.json();
+            if (!resp.ok) throw new Error(data.error || 'reset failed');
+            trimcpShellToast('Secret cleared', 'success');
+            this.revertField(key);
+            await this.fetchSettings();
+            await this.fetchPending();
+          } catch (err) {
+            trimcpShellToast(err.message || String(err), 'error');
+          }
+        },
+
+        // --- WARM reload affordance ----------------------------------------------
+        // Domains with at least one pending_reload result whose field lives in this section.
+        pendingReloadDomainsForSection(sec) {
+          const doms = new Set();
+          for (const f of (sec.keys || [])) {
+            const r = this.results[f.key];
+            if (r && r.status === 'pending_reload') {
+              const dom = this.SECTION_DOMAIN[sec.section];
+              if (dom) doms.add(dom);
+            }
+          }
+          return Array.from(doms);
+        },
+        async reloadDomain(domain) {
+          if (this.reloadingDomains[domain]) return;
+          this.reloadingDomains[domain] = true;
+          try {
+            const resp = await signedFetch(undefined, '/api/admin/settings/reload', {
+              method: 'POST',
+              body: { domains: [domain] },
+            });
+            const data = await resp.json();
+            if (!resp.ok) throw new Error(data.error || 'reload failed');
+            const outcome = (data.outcomes && data.outcomes[domain]) || {};
+            if (outcome.status === 'error') throw new Error(outcome.message || 'reload error');
+            // Clear pending_reload chips for keys whose section maps to this domain.
+            for (const sec of this.sections) {
+              if (this.SECTION_DOMAIN[sec.section] !== domain) continue;
+              for (const f of (sec.keys || [])) {
+                const r = this.results[f.key];
+                if (r && r.status === 'pending_reload') delete this.results[f.key];
+              }
+            }
+            trimcpShellToast('Reloaded ' + domain + (outcome.message ? ' — ' + outcome.message : ''), 'success');
+          } catch (err) {
+            trimcpShellToast(err.message || String(err), 'error');
+          } finally {
+            this.reloadingDomains[domain] = false;
+          }
+        },
+
+        // --- export effective config (masked) ------------------------------------
+        async exportEffective() {
+          try {
+            const resp = await signedFetch(undefined, '/api/admin/settings/effective');
+            if (!resp.ok) throw new Error((await resp.json()).error || 'export failed');
+            const data = await resp.json();
+            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
+            const url = URL.createObjectURL(blob);
+            const a = document.createElement('a');
+            a.href = url;
+            a.download = 'trimcp-effective-config.json';
+            document.body.appendChild(a);
+            a.click();
+            a.remove();
+            URL.revokeObjectURL(url);
+          } catch (err) {
+            trimcpShellToast(err.message || String(err), 'error');
+          }
+        },
+
         // --- badge / chip helpers -------------------------------------------------
         reloadChipLabel(cls) {
           return ({ HOT: 'H', WARM: 'W', COLD: 'C' })[cls] || '?';
```
