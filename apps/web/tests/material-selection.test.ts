import { describe, expect, it } from "vitest";

import { visibleSelectedMaterials } from "../lib/material-selection";

describe("material selection visibility boundary", () => {
  it("never submits selected materials hidden by the active filters", () => {
    const materials = [
      { id: "visible", status: "indexed" },
      { id: "hidden", status: "failed" },
    ];

    expect(visibleSelectedMaterials(
      materials,
      [materials[0]],
      new Set(["visible", "hidden"]),
    )).toEqual([materials[0]]);
  });
});
