import { categoryBySlug } from '../lib/filters'

// One removable chip per stored exclusion, at its own level -- a subcategory exclusion
// is one chip regardless of how many channels it currently covers. Falls back to the
// raw stored value (bare subcategory name, or the channel ID itself) when the tree
// hasn't loaded or failed to load: the chip is still real and still removable, it just
// can't show a friendly label without the fetch that provides it.
export default function ExclusionChips({ extraChips, nosub, nochan, tree, onRemoveNosub, onRemoveNochan, onClearAll }) {
  const nosubChips = nosub.map((name) => {
    const categorySlug = tree?.subcategoryToCategorySlug.get(name)
    const category = categorySlug ? categoryBySlug(categorySlug) : null
    return {
      key: `nosub:${name}`,
      label: category ? `${category.displayName} › ${name}` : name,
      onRemove: () => onRemoveNosub(name),
    }
  })

  const nochanChips = nochan.map((id) => {
    const info = tree?.channelsById.get(id)
    return {
      key: `nochan:${id}`,
      label: info ? info.name : id,
      onRemove: () => onRemoveNochan(id),
    }
  })

  const allChips = [...extraChips, ...nosubChips, ...nochanChips]
  if (allChips.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      {allChips.map((chip) => (
        <span
          key={chip.key}
          className="inline-flex items-center gap-1.5 text-xs rounded-full border border-gray-300 dark:border-gray-700 pl-2.5 pr-1.5 py-1 text-gray-700 dark:text-gray-200"
        >
          {chip.label}
          <button
            type="button"
            onClick={chip.onRemove}
            aria-label={`Remove ${chip.label}`}
            className="text-gray-400 dark:text-gray-500 hover:text-gray-900 dark:hover:text-gray-100"
          >
            {'✕'}
          </button>
        </span>
      ))}
      {allChips.length >= 2 && (
        <button
          type="button"
          onClick={onClearAll}
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          Clear all
        </button>
      )}
    </div>
  )
}
