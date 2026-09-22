import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DATE_OPTIONS, SPORTS, categoryBySlug, resolveFilters, withParam } from '../lib/filters'
import { useChannelTree } from '../lib/channelTree'
import ChannelFilterDropdowns from './ChannelFilterDropdowns'
import ExclusionChips from './ExclusionChips'

const METRICS = ['views', 'likes', 'comments']
const COMPARISONS = ['absolute', 'relative']
const FORMATS = ['longform', 'shorts']
const ALL_SPORT_SLUGS = SPORTS.map((s) => s.slug)

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

// Reads and writes the URL directly via useSearchParams for everything except category
// on/off, which is genuinely page-specific (nocat on the homepage, the path on the
// category page) -- categoryState is the one thing each page still has to supply.
export default function FilterBar({ categoryState }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = resolveFilters(searchParams)
  const { status: treeStatus, tree } = useChannelTree()

  function setFilter(key, value, { replace = false } = {}) {
    setSearchParams((prev) => withParam(prev, key, value), { replace })
  }

  // nosub and nochan are set together, in one navigation, by every transition in
  // channelFilterState.js -- two separate setSearchParams calls in the same handler
  // would risk one clobbering the other's stale snapshot of the URL.
  function setNosubNochan(nextNosub, nextNochan) {
    setSearchParams((prev) => {
      let next = withParam(prev, 'nosub', nextNosub)
      next = withParam(next, 'nochan', nextNochan)
      return next
    })
  }

  function handleClearAllExclusions() {
    setSearchParams((prev) => {
      let next = withParam(prev, 'nosub', [])
      next = withParam(next, 'nochan', [])
      return categoryState.clearAllTransform ? categoryState.clearAllTransform(next) : next
    })
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

  // Sports are stored as "which are selected", but displayed and clicked as "which are
  // active", where the empty (default) list displays as all four active -- so the
  // active set for display/toggling purposes is never the raw stored list itself.
  const activeSports = filters.sports.length === 0 ? ALL_SPORT_SLUGS : filters.sports

  // Toggling a sport is relative to the active set, not the stored one: from the
  // default (nothing stored, all four active), clicking cycling stores the other
  // three, not just cycling. If a toggle would result in every sport active again,
  // it collapses back to [] -- "all four selected" is the same query as none
  // selected (fetchVideos only adds the OR clause when sports.length > 0), so
  // CLAUDE.md's "a control back at its default removes its param" applies to this
  // semantic default too, not just the literal empty-array one withParam handles.
  function toggleSport(slug) {
    const isActive = activeSports.includes(slug)
    const nextActive = isActive ? activeSports.filter((s) => s !== slug) : [...activeSports, slug]
    const normalized = nextActive.length === ALL_SPORT_SLUGS.length ? [] : nextActive
    setFilter('sports', normalized)
  }

  // Local buffer for the search box: the query only runs on a deliberate submit (the
  // Search button, or Enter), never while typing -- no debounce, no query fired for a
  // word the user hasn't finished typing. Committed with push, like "Show more" and every
  // other deliberate action: a search is a real navigation step, worth its own back-button
  // stop, unlike the old typing-debounce which used replace specifically to avoid that.
  const [searchBuffer, setSearchBuffer] = useState(filters.q)
  const [syncedQ, setSyncedQ] = useState(filters.q)

  // Keep the buffer in sync when the URL changes externally (back button, a pasted
  // link) -- adjusted during render rather than in an effect, per React's guidance for
  // resetting local state when the value it mirrors changes outside this component.
  if (filters.q !== syncedQ) {
    setSyncedQ(filters.q)
    setSearchBuffer(filters.q)
  }

  function handleSearchSubmit() {
    setFilter('q', searchBuffer, { replace: false })
  }

  function handleSearchKeyDown(e) {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSearchSubmit()
    }
  }

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
        {SPORTS.map((sport) => {
          const isActive = activeSports.includes(sport.slug)
          const isLastActive = isActive && activeSports.length === 1
          return (
            <button
              key={sport.slug}
              type="button"
              onClick={() => toggleSport(sport.slug)}
              disabled={isLastActive}
              aria-pressed={isActive}
              title={isLastActive ? 'At least one sport must stay selected' : undefined}
              className={`px-3 py-1 rounded border text-sm ${
                isActive
                  ? 'bg-gray-900 text-white border-gray-900 dark:bg-gray-100 dark:text-gray-900 dark:border-gray-100'
                  : 'border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-300'
              } ${isLastActive ? 'opacity-60 cursor-not-allowed' : ''}`}
            >
              {sport.displayName}
            </button>
          )
        })}
      </div>

      <div>
        <span className="text-sm text-gray-700 dark:text-gray-300 block mb-1">Category / subcategory / channel</span>
        <ChannelFilterDropdowns
          status={treeStatus}
          tree={tree}
          nosub={filters.nosub}
          nochan={filters.nochan}
          sports={filters.sports}
          categoryState={categoryState}
          onSetNosubNochan={setNosubNochan}
        />
        <ExclusionChips
          extraChips={categoryState.offSlugsForChips().map((slug) => ({
            key: `nocat:${slug}`,
            label: `${categoryBySlug(slug).displayName} (off)`,
            onRemove: () => categoryState.setOn(slug, true),
          }))}
          nosub={filters.nosub}
          nochan={filters.nochan}
          tree={tree}
          onRemoveNosub={(name) => setNosubNochan(filters.nosub.filter((s) => s !== name), filters.nochan)}
          onRemoveNochan={(id) => setNosubNochan(filters.nosub, filters.nochan.filter((c) => c !== id))}
          onClearAll={handleClearAllExclusions}
        />
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={searchBuffer}
          onChange={(e) => setSearchBuffer(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          placeholder="Search title and description..."
          className="border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500 rounded px-2 py-1 text-sm flex-1 max-w-sm"
        />
        <button
          type="button"
          onClick={handleSearchSubmit}
          className="px-3 py-1 rounded border text-sm border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-300"
        >
          Search
        </button>
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
