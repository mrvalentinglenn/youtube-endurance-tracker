import { DURATION_BUCKETS } from '../lib/filters'

// One dropdown, same shape as a category dropdown (button + in-flow panel below it), but
// flat: five checkboxes, no hierarchy, no search box. Long-form only -- the parent hides
// this entirely under Shorts (NEXT_STEPS.md step 10g), rather than this component
// deciding that itself, so there's one place that knows the format/duration relationship.
//
// Styled to look exactly like the Published control (a native <select>): same border,
// padding and font, with an explicit arrow character standing in for the arrow a <select>
// draws natively, since a <button> draws none on its own.
export default function DurationDropdown({ id, nodur, onSetNodur, isOpen, onToggleOpen }) {
  const onCount = DURATION_BUCKETS.length - nodur.length
  const label = nodur.length === 0 ? 'Duration: all' : `Duration · ${onCount} of ${DURATION_BUCKETS.length}`

  function toggleBucket(key) {
    const isOn = !nodur.includes(key)
    if (isOn) {
      onSetNodur([...nodur, key])
    } else {
      onSetNodur(nodur.filter((k) => k !== key))
    }
  }

  return (
    <div>
      <button
        id={id}
        type="button"
        onClick={onToggleOpen}
        aria-expanded={isOpen}
        className="h-[31px] inline-flex items-center gap-1 border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 rounded px-2 py-1 text-sm"
      >
        {label}
        <span aria-hidden="true" className="text-xs">▾</span>
      </button>

      {isOpen && (
        <div className="mt-2 w-full sm:max-w-xs border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 shadow-sm p-3 space-y-1">
          {DURATION_BUCKETS.map((bucket) => {
            const isOn = !nodur.includes(bucket.key)
            const isLastOn = isOn && onCount === 1
            return (
              <label
                key={bucket.key}
                className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200"
              >
                <input
                  type="checkbox"
                  checked={isOn}
                  disabled={isLastOn}
                  onChange={() => toggleBucket(bucket.key)}
                />
                {bucket.displayName}
                {isLastOn && (
                  <span className="text-xs font-normal text-gray-400 dark:text-gray-500">(last bucket on)</span>
                )}
              </label>
            )
          })}
        </div>
      )}
    </div>
  )
}
