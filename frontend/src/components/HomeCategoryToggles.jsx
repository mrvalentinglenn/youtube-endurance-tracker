import { useSearchParams } from 'react-router-dom'
import { CATEGORIES, resolveFilters, withParam } from '../lib/filters'

// Homepage-only: which category sections render. Stored as nocat -- the deselected set,
// same pattern as nosub -- so re-selecting a category is just removing it from the
// exclusion list, nothing to reconcile.
export default function HomeCategoryToggles() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = resolveFilters(searchParams)

  function toggle(slug) {
    const isSelected = !filters.nocat.includes(slug)
    const isLastSelected = isSelected && filters.nocat.length === CATEGORIES.length - 1
    if (isLastSelected) return // at least one category must stay selected

    const nextNocat = isSelected ? [...filters.nocat, slug] : filters.nocat.filter((s) => s !== slug)
    setSearchParams((prev) => withParam(prev, 'nocat', nextNocat))
  }

  return (
    <div className="flex flex-wrap gap-2 mb-6">
      {CATEGORIES.map((category) => {
        const isSelected = !filters.nocat.includes(category.slug)
        const isLastSelected = isSelected && filters.nocat.length === CATEGORIES.length - 1
        return (
          <button
            key={category.slug}
            type="button"
            onClick={() => toggle(category.slug)}
            aria-pressed={isSelected}
            title={isLastSelected ? 'At least one category must stay selected' : undefined}
            className={`px-3 py-1 rounded-full border text-sm ${
              isSelected
                ? 'bg-gray-900 text-white border-gray-900 dark:bg-gray-100 dark:text-gray-900 dark:border-gray-100'
                : 'border-gray-300 text-gray-400 dark:border-gray-700 dark:text-gray-500'
            } ${isLastSelected ? 'opacity-60 cursor-not-allowed' : 'hover:opacity-80'}`}
          >
            {category.displayName}
          </button>
        )
      })}
    </div>
  )
}
