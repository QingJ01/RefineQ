import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { normalizeMathDelimiters, RichText } from "../components/rich-text";


describe("rich learning text", () => {
  it("normalizes common model LaTeX delimiters", () => {
    expect(normalizeMathDelimiters("当 \\(x\\) 趋近时：\\[x^2=1\\]"))
      .toContain("$x$");
    expect(normalizeMathDelimiters("当 \\(x\\) 趋近时：\\[x^2=1\\]"))
      .toContain("$$\nx^2=1\n$$");
  });

  it("renders Markdown emphasis and math instead of showing source symbols", () => {
    const html = renderToStaticMarkup(
      <RichText>{"**极限**记作 \\(\\lim_{x \\to a} f(x)=L\\)。"}</RichText>,
    );

    expect(html).toContain("<strong>极限</strong>");
    expect(html).toContain("class=\"katex\"");
    expect(html).toContain("aria-hidden=\"true\"");
  });

  it("does not auto-load remote images from untrusted learning content", () => {
    const html = renderToStaticMarkup(
      <RichText>{"![tracking pixel](https://attacker.example/pixel.png)"}</RichText>,
    );

    expect(html).not.toContain("<img");
    expect(html).not.toContain("attacker.example");
    expect(html).toContain("tracking pixel");
  });

  it("opens external links without replacing the active learning session", () => {
    const html = renderToStaticMarkup(
      <RichText>{"[reference](https://example.com/source)"}</RichText>,
    );

    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });
});
