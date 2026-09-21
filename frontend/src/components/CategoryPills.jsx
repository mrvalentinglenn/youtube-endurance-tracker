import { Link } from 'react-router-dom'
import { CATEGORIES } from '../lib/filters'

// The category page's category selection lives in the path, not a query param -- toggling
// a pill navigates to a new /category/... path, carrying the other filters unchanged.
export default function CategoryPills({ selectedSlugs, otherParamsString }) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-6">
      <Link to={`/?${otherParamsString}`} className="text-sm text-blue-600 dark:text-blue-400 hover:underline mr-2">
        &larr; Back to home
      </Link>

      {CATEGORIES.map((category) => {
        const isSelected = selectedSlugs.includes(category.slug)
        const isLastOne = isSelected && selectedSlugs.length === 1

        const nextSlugs = isSelected
          ? selectedSlugs.filter((slug) => slug !== category.slug)
          : [...selectedSlugs, category.slug]
        // Keep the fixed homepage order in the URL too, so the path is stable regardless
        // of click order.
        const orderedNextSlugs = CATEGORIES.map((c) => c.slug).filter((slug) => nextSlugs.includes(slug))

        const pillClass = `px-3 py-1 rounded-full border text-sm ${
          isSelected
            ? 'bg-gray-900 text-white border-gray-900 dark:bg-gray-100 dark:text-gray-900 dark:border-gray-100'
            : 'border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-300'
        } ${isLastOne ? 'opacity-60 cursor-not-allowed' : 'hover:opacity-80'}`

        if (isLastOne) {
          return (
            <span key={category.slug} className={pillClass} title="At least one category must stay selected">
              {category.displayName}
            </span>
          )
        }

        return (
          <Link
            key={category.slug}
            to={`/category/${orderedNextSlugs.join(',')}?${otherParamsString}`}
            className={pillClass}
          >
            {category.displayName}
          </Link>
        )
      })}
    </div>
  )
}
