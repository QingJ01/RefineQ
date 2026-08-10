export function visibleSelectedMaterials<T extends { id: string }>(
  materials: readonly T[],
  visibleMaterials: readonly T[],
  selectedIds: ReadonlySet<string>,
): T[] {
  const availableIds = new Set(materials.map((material) => material.id));
  return visibleMaterials.filter(
    (material) => availableIds.has(material.id) && selectedIds.has(material.id),
  );
}
