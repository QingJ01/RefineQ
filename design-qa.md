# RefineQ universal learning session — design QA

## Comparison target

- Source visual truth: `C:\Users\QingJ\.codex\generated_images\019fd1da-993a-7040-82d4-830cf70f321b\exec-d646e72f-ef91-452c-a4eb-d0515cc81185.png`
- Browser-rendered implementation: `D:\project\personal agent\apps\web\test-results\learning-journey-learner-c-d28a5-capability-learning-journey-chromium\capability-learning-practice.png`
- Responsive evidence: `D:\project\personal agent\apps\web\test-results\learning-journey-learner-c-d28a5-capability-learning-journey-chromium\capability-learning-mobile.png`
- State: authenticated learner, product-thinking capability, case method selected, uploaded interview source, applied task open, empty answer state.
- Browser: local Google Chrome through Playwright.

## Viewport and normalization

- Source pixels: 1487 × 1058 at 96 dpi.
- Implementation pixels / CSS viewport: 1440 × 1024 at device scale factor 1 and 96 dpi.
- Mobile implementation pixels / CSS viewport: 390 × 844 at device scale factor 1.
- The source and desktop implementation have the same effective aspect ratio (difference under 0.1%). The source was visually normalized to the 1440 × 1024 implementation frame without cropping for the combined comparison input.
- Both full-size images were opened together in one comparison input. The main task, typography, source rail, coach, controls, and sidebar were readable at original detail, so a separate focused crop was not needed.

## Findings

No actionable P0, P1, or P2 differences remain.

- Typography: Manrope plus the Chinese system fallback produces the same compact, friendly product hierarchy as the source. Headings, micro-labels, controls, and supporting copy remain readable without clipping.
- Spacing and layout: the persistent sidebar, wide learning canvas, four-step header, main/rail split, task controls, and bottom review card follow the source composition. The canvas now fills the desktop viewport rather than ending above a large empty region.
- Colors and tokens: warm white surfaces, quiet gray borders, blue selected states, green completion, and apricot review treatment consistently map to the source palette. Contrast and focus states remain visible.
- Image quality: the contextual coach uses the generated raster coach asset at a measured 60 px slot; it is sharp, correctly cropped, and not replaced by CSS or inline-SVG artwork. Product icons use the installed icon library consistently.
- Copy and content: capability language is no longer exam-only. The case task keeps the uploaded evidence excerpt and the “场景—核心问题—现有替代—行为证据” framework in view while the learner answers. Uploaded-source metadata is localized.
- Interaction and accessibility: sidebar routes, mode selector, source drawer, save/replace task, answer submission, progress record, contextual coach, keyboard skip link, mobile navigation, and destructive confirmation all worked in Chrome. No uncaught page errors were observed. The expected HTTP 409 from an intentionally unconfigured coach model was handled in the UI and excluded from unexpected console failures.

## Comparison history

### Iteration 1 — blocked

- [P2] The applied-task state removed the case context and left an oversized empty answer field. This broke the source design’s continuity between explanation and action.
- [P2] The desktop canvas stopped early and left a large empty band below the product frame.
- [P2] The visually hidden coach label had no CSS utility, so it occupied the form grid and reversed the apparent input/button layout.
- [P2] Capability routing exposed weak raw English tokens such as `thinking`, and learning-record details exposed internal `topic_*` identifiers.

Fixes made:

- Kept the grounded material excerpt and the four-part analysis framework inside the task state; reduced answer-field height and generated mode-specific fallback tasks.
- Made the session canvas fill the available desktop height while retaining content-driven height on tablet/mobile.
- Added the accessible `.sr-only` utility and reverified the coach composer.
- Added curated product, operations, writing, and research capability topics; replaced internal evidence fields with learner-facing labels.

### Iteration 2 — passed

- Re-captured the same product/case/task state in Chrome at 1440 × 1024.
- Re-opened the source and revised implementation together in one comparison input.
- The earlier P2 findings are visibly resolved: the task retains case evidence and structure, the frame fills the viewport, the coach input is aligned, and learner-facing content no longer shows raw topic identifiers.

## Follow-up polish

- [P3] The source places the capability title and date just outside the main card; the implementation keeps the title inside the card to preserve the existing application shell and scroll containment.
- [P3] The source mock shows two illustrative documents, while the implementation truthfully shows the one document uploaded during the tested journey.

## Implementation checklist

- [x] Desktop source and implementation compared in one input.
- [x] Same case-practice interaction state captured.
- [x] Mobile navigation and responsive layout captured.
- [x] P0/P1/P2 findings fixed and re-captured.
- [x] Primary interactions and browser errors checked.
- [x] Unit, integration, build, and end-to-end verification completed.

final result: passed
