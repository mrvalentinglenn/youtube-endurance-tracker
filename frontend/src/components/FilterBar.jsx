import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CATEGORIES, DATE_OPTIONS, SPORTS, SUBCATEGORIES, resolveFilters, withParam } from '../lib/filters'

const METRICS = ['views', 'likes', 'comments']
const COMPARISONS = ['absolute', 'relative']
const FORMATS = ['longform', 'shorts']
const SEARCH_DEBOUNCE_MS = 400

function label(word) {
  return word[0].toUpperCase() + word.slice(1)
}

function ToggleGroup({ options, value, onChange, renderLabel }) {
  return (
    <div className="flex gap-2">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          aria-pressed={value === option}
          className={`px-3 py-1 rounded border text-sm ${
            value === option
              ? 'bg-gray-900 text-white border-gray-900 dark:bg-gray-100 dark:text-gray-900 dark:border-gray-100'
              : 'border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-300'
          }`}
        >
          {renderLabel ? renderLabel(option) : label(option)}
        </button>
      ))}
    </div>
  )
}

// Self-contained: reads and writes the URL directly via useSearchParams, so both routes
// can render <FilterBar /> with no props. Filter state lives in the URL, not React state
// -- a refresh, a back-button step, or a pasted link all reproduce the same page.
export default function FilterBar() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = resolveFilters(searchParams)

  function setFilter(key, value, { replace = false } = {}) {
    setSearchParams((prev) => withParam(prev, key, value), { replace })
  }

  function handleDateChange(value) {
    setSearchParams((prev) => {
      let next = withParam(prev, 'date', value)
      if (value !== 'custom') {
        next.delete('from')
        next.delete('to')
      }
      return next
    })
  }

  function toggleInList(key, current, item) {
    const next = current.includes(item) ? current.filter((v) => v !== item) : [...current, item]
    setFilter(key, next)
  }

  // Local buffer for the search box: committed to the URL debounced, with replace so
  // the back button doesn't step through fragments of a word typed one keystroke apart.
  const [searchBuffer, setSearchBuffer] = useState(filters.q)
  const [syncedQ, setSyncedQ] = useState(filters.q)

  // Keep the buffer in sync when the URL changes externally (back button, a pasted
  // link) -- adjusted during render rather than in an effect, per React's guidance for
  // resetting local state when the value it mirrors changes outside this component.
  if (filters.q !== syncedQ) {
    setSyncedQ(filters.q)
    setSearchBuffer(filters.q)
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      setFilter('q', searchBuffer, { replace: true })
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only the buffer should retrigger the timer
  }, [searchBuffer])

  function handleClearSearch() {
    setSearchBuffer('')
    setFilter('q', '', { replace: false })
  }

  return (
    <div className="mb-8 space-y-4 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
      <div className="flex flex-wrap gap-6">
        <ToggleGroup options={METRICS} value={filters.metric} onChange={(v) => setFilter('metric', v)} />
        <ToggleGroup options={COMPARISONS} value={filters.comparison} onChange={(v) => setFilter('comparison', v)} />
        <ToggleGroup
          options={FORMATS}
          value={filters.format}
          onChange={(v) => setFilter('format', v)}
          renderLabel={(v) => (v === 'longform' ? 'Long-form' : 'Shorts')}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-gray-700 dark:text-gray-300" htmlFor="date-filter">
          Published
        </label>
        <select
          id="date-filter"
          value={filters.date}
          onChange={(e) => handleDateChange(e.target.value)}
          className="border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 rounded px-2 py-1 text-sm"
        >
          {DATE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.displayName}
            </option>
          ))}
        </select>

        {filters.date === 'custom' && (
          <>
            <input
              type="date"
              value={filters.from}
              onChange={(e) => setFilter('from', e.target.value)}
              className="border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 rounded px-2 py-1 text-sm"
            />
            <span className="text-sm text-gray-500 dark:text-gray-400">to</span>
            <input
              type="date"
              value={filters.to}
              onChange={(e) => setFilter('to', e.target.value)}
              className="border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 rounded px-2 py-1 text-sm"
            />
          </>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-gray-700 dark:text-gray-300">Sport</span>
        {SPORTS.map((sport) => (
          <button
            key={sport.slug}
            type="button"
            onClick={() => toggleInList('sports', filters.sports, sport.slug)}
            aria-pressed={filters.sports.includes(sport.slug)}
            className={`px-3 py-1 rounded border text-sm ${
              filters.sports.includes(sport.slug)
                ? 'bg-gray-900 text-white border-gray-900 dark:bg-gray-100 dark:text-gray-900 dark:border-gray-100'
                : 'border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-300'
            }`}
          >
            {sport.displayName}
          </button>
        ))}
        {filters.sports.length === 0 && (
          <span className="text-xs text-gray-400 dark:text-gray-500">(none selected = all sports)</span>
        )}
      </div>

      <div>
        <span className="text-sm text-gray-700 dark:text-gray-300 block mb-1">Subcategory</span>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((category) => (
            <details key={category.slug} className="border border-gray-200 dark:border-gray-700 rounded px-2 py-1">
              <summary className="text-sm cursor-pointer select-none text-gray-900 dark:text-gray-100">
                {category.displayName}
              </summary>
              <div className="pt-2 space-y-1">
                {SUBCATEGORIES[category.slug].map((subcategory) => (
                  <label
                    key={subcategory}
                    className="flex items-center gap-2 text-sm whitespace-nowrap text-gray-800 dark:text-gray-200"
                  >
                    <input
                      type="checkbox"
                      checked={!filters.nosub.includes(subcategory)}
                      onChange={() => toggleInList('nosub', filters.nosub, subcategory)}
                    />
                    {subcategory}
                  </label>
                ))}
              </div>
            </details>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={searchBuffer}
          onChange={(e) => setSearchBuffer(e.target.value)}
          placeholder="Search title and description..."
          className="border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500 rounded px-2 py-1 text-sm flex-1 max-w-sm"
        />
        {searchBuffer && (
          <button
            type="button"
            onClick={handleClearSearch}
            className="text-sm text-gray-500 dark:text-gray-400 hover:underline"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  )
}
