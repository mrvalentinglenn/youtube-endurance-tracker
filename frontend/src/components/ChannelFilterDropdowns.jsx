import { CATEGORIES } from '../lib/filters'
import { categoryCheckedCount } from '../lib/channelFilterState'
import CategoryDropdownPanel from './CategoryDropdownPanel'

// Which dropdown is open (one slot, not one boolean per dropdown -- five category panels
// plus Duration able to open independently is exactly the bug this avoids) is owned by
// the parent (FilterBar) and passed down as openSlug/onOpenSlugChange, so a category
// dropdown and the Duration dropdown share the same slot and close each other. The open
// panel renders in-flow below the button row (not floating over the page): simpler and
// more robust than absolute positioning anchored to one of several buttons, and it
// naturally satisfies "full-width on small screens" without separate breakpoint logic.
//
// status/tree come from the parent rather than being fetched here, so the one
// channels_public fetch is shared with ExclusionChips instead of each fetching its own.
export default function ChannelFilterDropdowns({ status, tree, nosub, nochan, sports, categoryState, onSetNosubNochan, openSlug, onOpenSlugChange }) {
  if (status === 'error') {
    return (
      <p className="text-sm text-red-600 dark:text-red-400 mb-4">
        Couldn't load the channel list, so category, subcategory and channel filtering are
        unavailable right now. Videos still load with the other filters.
      </p>
    )
  }

  const onCount = CATEGORIES.filter((c) => categoryState.isOn(c.slug)).length
  const openCategory = openSlug ? CATEGORIES.find((c) => c.slug === openSlug) : null
  const openBucket = openCategory && tree ? tree.bySlug[openCategory.slug] : null

  return (
    <div className="mb-4">
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((category) => {
          const isOn = categoryState.isOn(category.slug)
          const bucket = tree?.bySlug[category.slug]
          const label =
            status === 'loading' || !bucket
              ? category.displayName
              : !isOn
                ? `${category.displayName} · off`
                : `${category.displayName} · ${categoryCheckedCount(bucket, nosub, nochan)} of ${bucket.total}`

          return (
            <button
              key={category.slug}
              type="button"
              onClick={() => onOpenSlugChange(openSlug === category.slug ? null : category.slug)}
              disabled={status === 'loading'}
              aria-expanded={openSlug === category.slug}
              className={`px-3 py-1.5 rounded border text-sm disabled:opacity-50 ${
                openSlug === category.slug
                  ? 'border-gray-900 dark:border-gray-100 text-gray-900 dark:text-gray-100'
                  : 'border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              {label}
            </button>
          )
        })}
      </div>

      {openCategory && openBucket && (
        <div className="mt-2 w-full sm:max-w-sm border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 shadow-sm">
          <CategoryDropdownPanel
            category={openCategory}
            bucket={openBucket}
            nosub={nosub}
            nochan={nochan}
            sports={sports}
            isOn={categoryState.isOn(openCategory.slug)}
            isLastCategoryOn={categoryState.isOn(openCategory.slug) && onCount === 1}
            onSetOn={(on) => categoryState.setOn(openCategory.slug, on)}
            onSetNosubNochan={onSetNosubNochan}
          />
        </div>
      )}
    </div>
  )
}
