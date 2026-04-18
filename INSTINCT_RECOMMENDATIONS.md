# Observer Analysis: Instinct Recommendations for BDI_LLM_Formal_Ver

Based on analysis of session `bb5b5c38-b96e-4ba5-bd85-691ba49465b3` (2026-04-18), the following 3 instinct files should be created in `/Users/alexjiang/.claude/homunculus/projects/50e02ef6f615/instincts/personal/`:

---

## 1. psc-cache-redirect-enforcement.md

```yaml
---
id: psc-cache-redirect-enforcement
trigger: when deploying to PSC with sbatch+apptainer+vllm serving
confidence: 0.85
domain: workflow
source: session-observation
scope: project
project_id: 50e02ef6f615
project_name: BDI_LLM_Formal_Ver
---
```

**Summary**: Before launching any sbatch job with vLLM/Triton/HuggingFace, verify that ALL 7 cache env vars are explicitly redirected to `/ocean/projects/` via PSC_CACHE_GUARD hook validation.

**Evidence**: 
- Observed 2 times in session (lines 15-16, 19-20 of JSONL)
- PSC_CACHE_GUARD hook blocks deploys missing: VLLM_CACHE_ROOT, TRITON_CACHE_DIR, TORCHINDUCTOR_CACHE_DIR, XDG_CACHE_HOME, TMPDIR
- Root cause: `/jet/home` has 25 GiB quota; writing caches → `Errno 122 Disk quota exceeded` at runtime
- Observed: `/jet/home/zjiang9` was 25.04GiB used (over quota), `.cache` alone 15GB

**Required env vars**:
```
HF_HOME, HF_HUB_CACHE, VLLM_CACHE_ROOT, TRITON_CACHE_DIR, 
TORCHINDUCTOR_CACHE_DIR, XDG_CACHE_HOME, TMPDIR
```

---

## 2. psc-deployment-validation-checklist.md

```yaml
---
id: psc-deployment-validation-checklist
trigger: when staging a PSC sbatch job with model serving
confidence: 0.7
domain: workflow
source: session-observation
scope: project
project_id: 50e02ef6f615
project_name: BDI_LLM_Formal_Ver
---
```

**Summary**: Before submitting sbatch to PSC, run 3 validation checks in sequence: cache guard hook, disk quota check, and queue status scan.

**Evidence**:
- Observed 3 distinct validation operations in session (lines 7-8, 11-12, 15-16, 19-20)
- Pattern: User checks job queue status → runs cache guard hook → verifies disk quota
- Last observed: 2026-04-18T02:08:02Z

**Validation sequence**:
1. Run `psc_cache_guard.py` hook on sbatch script (exit 0 = pass, 2 = block)
2. Check `squeue` for pending job and queue position
3. Verify `/jet/home` disk quota and `.cache` distribution via `du -sh`

---

## 3. lesson-capture-to-memory.md

```yaml
---
id: lesson-capture-to-memory
trigger: when user fixes a PSC deployment issue or discovers a new gotcha
confidence: 0.5
domain: workflow
source: session-observation
scope: project
project_id: 50e02ef6f615
project_name: BDI_LLM_Formal_Ver
---
```

**Summary**: After resolving a PSC/HPC deployment issue, immediately update `/Users/alexjiang/.claude/projects/-Users-alexjiang/memory/MEMORY.md` with a new feedback entry to prevent recurrence.

**Evidence**:
- Observed 2 times in session (lines 1-4 of JSONL)
- Pattern: User edits MEMORY.md to add `[PSC deployment must redirect ALL caches]` feedback entry
- Last observed: 2026-04-18T02:04:53Z

**Format for new entries**:
```markdown
- [Brief lesson title](feedback_file.md) — 1-2 sentence description of the issue and workaround
```

---

## Summary Statistics

| Pattern | Count | Confidence | Domain |
|---------|-------|-----------|--------|
| Cache redirect enforcement | 2 | 0.85 | workflow |
| Deployment validation checklist | 3+ | 0.7 | workflow |
| Lesson capture to memory | 2 | 0.5 | workflow |

All patterns are **project-scoped** (PSC/Bridges2-specific), not global.
