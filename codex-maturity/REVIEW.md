# Phase B independent maturity review

## Cycle and scope

- Cycle: 2, functionality revision 4 narrow final review
- Dimension: functional completeness
- Baseline: `5a0158dc82f0ed9fc0728ef30124683a6a3d5822`
- Selected outcome: the two approved ambiguous material topics complete a safe, persisted mastery
  journey while unregistered material topics remain non-authoritative
- Authority design: persisted server-owned `answer_key_subject`; generated keys are coaching context
  only; authoritative AI grading is isolated from keys/materials and requires exact, substantive
  learner-answer evidence tied to the current subject
- Narrow revision reviewed: ASCII subject tokenization changed to `[a-z0-9+#]+`, excluding prose
  dots while preserving `+` and `#`; new real-service sentence-terminal regressions were added
- Review method: the complete candidate diff and prior findings were rechecked. The revised matcher
  was exercised through `LearningIntelligenceService.grade_answer`, followed by fresh focused,
  related, MCP-compatibility, lint, format, and diff gates. This report is the only
  reviewer-authored repository change.

## Verdict

**PASS**

- Material functional improvement: **yes**. Legitimate ambiguous topics now complete a persisted
  mastery journey without letting material or generated key text become mastery authority.
- Single focused improvement: **yes**. All changes serve the selected trusted-mastery subject
  outcome and its lifecycle/security boundaries.
- Exit gate: **met**. No P0 or P1 findings remain.

## Findings

### P0

None.

### P1

None.

### P2

1. **Stored authority has no explicit provenance-kind field.** This is non-blocking because every
   current writer is server-controlled, material-derived subjects require an exact registry match,
   and direct reauthorization preserves existing authority. A future enum such as `explicit_user`,
   `server_registry`, and `system_seed` would improve auditability and schema-policy evolution.

2. **The transactional subject-change fence lacks a committed barrier regression.** Independent
   fault injection pauses grading, changes the subject before commit, and confirms no mastery update,
   so no defect was found. Preserve that precise timing in an automated integration test because the
   authorization guarantee is concurrency-sensitive.

## Narrow-fix verification

- ASCII matching now tokenizes with `[a-z0-9+#]+`. A terminal prose dot is excluded, while `C++`
  and `C#` remain single technical tokens.
- Real configured-service grading with score `82`, `sufficient_evidence=true`, and an exact full
  learner-answer evidence span produced `passed=true` and `mastery_evidence=true` for correct long
  answers whose only canonical occurrence was sentence-terminal `AI.`, `ML.`, or `C++.`.
- The same real path kept canonical `AI` fail-closed for an otherwise substantive answer containing
  only `training`; matching remains an exact token sequence, not a substring.
- Prior positives remain green for `AI`, `ML`, single Han `熵`, Japanese `極限`, and Korean
  `강화학습`. NFKC plus compact Unicode letter/number matching and Unicode substantiveness were not
  weakened by the ASCII-only revision.

## Prior boundary closures reconfirmed

- `fallback_grade` always returns `mastery_evidence=false`; post-subject meta keys and other
  model-produced coaching keys cannot mutate BKT mastery.
- The authoritative grade prompt contains canonical subject, delimited public question, learner
  answer, and fixed criteria. Generated key, uploaded material, raw material label, and material
  sentinel are absent.
- Missing, fabricated, short, non-substring, and prompt-echo evidence spans fail closed. Missing or
  failed grading-model calls fall back without mastery evidence.
- Stored questions bind their canonical subject. Submission checks current provenance before model
  work and again transactionally before mutation; legacy pending/retry snapshots with absent or
  mismatched subjects cannot update mastery.
- Explicit add-topic/add-plan-session actions fill a missing subject through `setdefault` without
  overwriting an existing subject.
- Unregistered material labels receive no authoritative subject. Exact whole-label registry matching
  is required, and uploaded material never supplies a mastery-authoritative key or subject.
- `Output with feedback control` and `Return with compound interest` retain the composed upload ->
  attach -> analysis -> registry -> targeted plan -> API question -> structured grade -> BKT ->
  plan-session completion journey.
- MCP server-authored fallback questions retain a bound subject and the learning-loop/contract gate
  remains compatible.

## TDD and verification evidence

### Independently reproduced

- Exact real-service punctuation/script/token cases: **7 passed in 2.59s**.
- Registry/intelligence/personalized/AI-practice focused suite: **88 passed in 29.26s**.
- Broader learning unit plus AI-practice integration suite: **123 passed in 29.26s**.
- MCP learning-loop plus contract compatibility gate: **33 passed in 25.11s**.
- Manual real-service matrix: `AI.`, `ML.`, and `C++.` passed with mastery evidence; `training` did
  not match `AI`.
- Ruff check over all nine changed/new Python files: **passed**.
- Ruff format check: **9 files already formatted**.
- `git diff --check`: **passed**.

### Parent evidence reviewed

- Exact narrow cases: **7 passed**.
- Focused gate: **118 passed**.
- Full Python: **648 passed, 3 skipped**.
- Frontend: **205 tests passed**, ESLint passed, and Next build passed.
- Ruff/format/diff checks: clean.

## Independent candidate score

| Dimension | Score | Reason |
| --- | ---: | --- |
| Code structure and architecture clarity | 96 | Persisted provenance, coaching-key separation, isolated grading, and transactional binding form a clear authority model. |
| Functional completeness | 97 | Both selected product journeys, legacy recovery, multilingual/short subjects, punctuation forms, and fail-closed negatives now work. |
| Engineering quality | 95 | Focused, related, full, MCP, frontend, lint, format, and adversarial evidence are broad; the concurrency fence test remains a P2 coverage opportunity. |
| Technical depth | 96 | The solution combines provenance, model isolation, exact evidence, snapshot fencing, Unicode handling, and precise ASCII token boundaries. |
| **Overall** | **96** | Cycle 2 delivers a substantial, independently verified functionality improvement with no blocking finding. |

These scores apply only to accepted Cycle 2. Later cycles must be reviewed and scored independently.

## Recommendation for the next cycle

Do not expand Cycle 2 further. Carry the two P2 items as suggestions only: add explicit provenance
metadata when schema/audit work is next in scope, and preserve the subject-change fault injection as
an automated concurrency regression during the engineering-quality rotation.
