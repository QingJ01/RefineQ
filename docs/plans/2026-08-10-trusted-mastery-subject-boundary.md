# Trusted mastery subject boundary

## Decision

RefineQ will not infer mastery authority from the wording of a free-form topic label. A topic may
enter the authoritative grading path only when its learning-domain record contains a server-owned
`answer_key_subject`. An independently generated free-text answer key is coaching context, not
server truth and never authorizes deterministic fallback mastery.

Direct topic creation is an explicit learner/system action, so the learning service persists the
chosen topic name as its subject. Topics copied from material analysis are different: uploaded
material is untrusted, and selecting a model-extracted string does not make the string safe model
instructions. Those topics receive no subject by default. A small server registry may map an exact
complete material label to a canonical academic subject; the first entries are
`Output with feedback control -> feedback control` and
`Return with compound interest -> compound interest`.

## Data flow

The source action decides whether a subject exists and persists that decision with the topic.
Question generation continues to retrieve uploaded material for evidence and citations. Independent
key generation receives only the persisted subject; it never receives the material, the raw
material-derived label, the generated question, prior feedback, or learner answer. A topic without
a subject can still receive a grounded practice question and model feedback, but the result cannot
become deterministic mastery evidence.

The authoritative grader is a separate structured call. It receives the persisted canonical
subject, a delimited public question, the learner answer, and fixed server criteria. It receives
neither the generated answer key nor study material nor the raw material-derived label. A positive
judgment must include exact evidence spans that the server can find in the learner answer; the
server also checks subject overlap, substance, and prompt copying. Subject overlap uses exact ASCII
token sequences for abbreviations and normalized Unicode letter/number sequences for non-Latin
scripts, so `AI` cannot match `training` while `熵`, `極限`, and `강화학습` remain usable. Missing model configuration,
model failure, fabricated evidence spans, or deterministic fallback grading all fail closed for
mastery while still returning useful feedback.

This makes authorization explicit and language-independent. English synonyms, accented spellings,
Chinese/Japanese/Korean instructions, and future command forms all have the same outcome when they
come from material: no subject, no authoritative key. Natural academic keys can begin with a
definition, superclass, or evidence because key validity no longer depends on first-word matching.

## Compatibility and failure behavior

Existing direct seed, add-topic, and manual-plan-session operations remain explicit user actions and
persist their subject. Repeating add-topic or manual-plan-session for an existing matching topic
fills a missing subject without overwriting an existing one. Targeted material plans preserve any
already trusted topic record but never upgrade an untrusted topic unless the exact registry supplies
the canonical subject. Legacy records without the new field fail closed: practice remains
available, while mastery does not update until the topic is explicitly re-added or server-mapped.

Every persisted grading snapshot records the subject that authorized it. Pending, historical, and
retried questions are rechecked against the current topic at submission and again inside the final
learning-state mutation. Missing or changed provenance downgrades the snapshot to feedback-only, so
an upgrade or concurrent state change cannot credit stale authority.

The registry normalizes Unicode compatibility forms, case, and ordinary whitespace before an exact
full-label lookup. Prefixes, suffixes, and additional words never inherit a mapping.

## Verification

Tests must prove both approved material labels persist canonical subjects and complete the real
material-analysis, targeted-plan, question, structured-grade, BKT, and plan-session path. Unknown
English and non-Latin instructions
must remain untrusted without lexical classification. Direct academic subjects must accept natural
definition-first keys. Key prompts must contain the canonical subject and exclude raw material
labels and unique material sentinels. Grading prompts must exclude generated keys and raw study
material, and legacy pending/history tests must prove subject removal prevents mastery.
