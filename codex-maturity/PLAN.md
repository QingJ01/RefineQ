# RefineQ maturity plan

## Rotation

1. Code structure and architecture clarity
2. Functional completeness
3. Engineering quality
4. Technical depth

## Current cycle

- Dimension: functional completeness
- Status: completed; independent verdict PASS, overall 96
- Selected outcome: legitimate academic topics that contain ambiguous control-language words
  (for example, `Output with feedback control` and `Return with compound interest`) can
  generate a trusted independent answer key, so normal answers can advance mastery and plan
  progress, while instruction-shaped topic labels remain fail-closed
- Trust design: mastery authority comes from a persisted, server-owned `answer_key_subject`, not
  from classifying free-form labels. Direct user/system topic creation records its explicit
  subject. Material-analysis topics record no subject unless an exact server registry maps the
  complete label to a canonical academic subject. Question generation may use untrusted material,
  but independent key generation receives only this persisted subject. Generated keys remain
  coaching context: deterministic fallback never updates mastery. The authoritative grader receives
  only the canonical subject, a delimited public question, the learner answer, and fixed server
  criteria; exact answer evidence spans and current snapshot provenance are verified server-side.
- Rejected alternatives: an open-ended command denylist cannot cover languages or synonyms, and a
  model canonicalizer cannot independently prove that an injected label is declarative.
- Constraint: do not revisit the rate-limit extraction or architecture-contract P2 in this cycle
- Exit gate: relevant verification passes and an independent read-only review accepts the cycle

## Completed cycle

- Cycle 1 architecture review: PASS, overall 91.
- Cycle 2 functional-completeness review: PASS, overall 96.

## Rotation status

- Stop condition reached after Cycle 2 because the independently reviewed overall score is 96.
- Engineering-quality and technical-depth rotations are not started; continuing would exceed the
  agreed maturity loop rather than address a blocking finding.

## Stop conditions

- Overall independently reviewed score reaches at least 95, or
- Three consecutive reviewed cycles produce no material improvement.
