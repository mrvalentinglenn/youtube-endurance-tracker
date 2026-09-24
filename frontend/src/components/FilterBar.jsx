import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DATE_OPTIONS, DEFAULT_FILTERS, SPORTS, categoryBySlug, resolveFilters, withParam } from '../lib/filters'
import { useChannelTree } from '../lib/channelTree'
import { CLOSE_FILTER_DROPDOWNS_EVENT } from '../lib/dropdownCoordination'
import ChannelFilterDropdowns from './ChannelFilterDropdowns'
import DurationDropdown from './DurationDropdown'
import ExclusionChips from './ExclusionChips'
import { XIcon } from './icons'

const METRICS = ['views', 'likes', 'comments']
const COMPARISONS = ['absolute', 'relative']
const FORMATS = ['longform', 'shorts']
const ALL_SPORT_SLUGS = SPORTS.map((s) => s.slug)

// Native title attribute, same approach as VideoCard's "still growing" and paid-promotion
// tooltips -- works on hover regardless of which button is currently selected, since it's
// set on every option's button unconditionally, not just the active one.
const COMPARISON_TOOLTIPS = {
  absolute: "Ranks videos by their total views, likes or comments. Large channels tend to come out on top.",
  relative:
    "Ranks videos by how far they outperformed their own channel's usual level. A high score often points to a strong title, thumbnail, topic or video, whatever the channel's size.",
}

function label(word) {
  return word[0].toUpperCase() + word.slice(1)
}

function ToggleGroup({ options, value, onChange, renderLabel, getTitle }) {
  return (
    <div className="flex gap-2">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          aria-pressed={value === option}
          title={getTitle ? getTitle(option) : undefined}
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

  // One state slot for which dropdown is open, shared by the five category dropdowns and
  // Duration -- opening one closes any other, the same discipline that already keeps five
  // category panels from opening at once, just widened by one more participant. Category
  // and Duration sit on different lines now, so click-outside needs two refs, not one: a
  // click is "outside" only when it lands in neither region. Escape and each button's own
  // onClick still just set openDropdown directly, so both keep working independent of this.
  const [openDropdown, setOpenDropdown] = useState(null)
  const categoryDropdownsRef = useRef(null)
  const durationDropdownRef = useRef(null)

  useEffect(() => {
    if (!openDropdown) return undefined

    function handlePointerDown(e) {
      const insideCategory = categoryDropdownsRef.current && categoryDropdownsRef.current.contains(e.target)
      const insideDuration = durationDropdownRef.current && durationDropdownRef.current.contains(e.target)
      if (!insideCategory && !insideDuration) {
        setOpenDropdown(null)
      }
    }
    function handleKeyDown(e) {
      if (e.key === 'Escape') setOpenDropdown(null)
    }
    function handleExternalClose() {
      setOpenDropdown(null)
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    // Dispatched by SuggestChannelButton when its modal opens, so opening it closes
    // whichever filter dropdown is currently open rather than sitting behind the modal.
    window.addEventListener(CLOSE_FILTER_DROPDOWNS_EVENT, handleExternalClose)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener(CLOSE_FILTER_DROPDOWNS_EVENT, handleExternalClose)
    }
  }, [openDropdown])

  function setNodur(nextNodur) {
    setFilter('nodur', nextNodur)
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

  // Mobile only (below md): the whole panel (category/subcategory/channel, sport,
  // published, duration, metric, comparison, format) collapses behind one "Filters"
  // button and opens as a sheet. q is deliberately left out of the badge count -- the
  // search box stays visible outside the panel at every width, so there's already a
  // visible sign of whether a search is active without counting it here too.
  const [isPanelOpen, setIsPanelOpen] = useState(false)

  const badgeCount = [
    filters.metric !== DEFAULT_FILTERS.metric,
    filters.comparison !== DEFAULT_FILTERS.comparison,
    filters.format !== DEFAULT_FILTERS.format,
    filters.date !== DEFAULT_FILTERS.date,
    filters.sports.length > 0,
    filters.nodur.length > 0,
    categoryState.offSlugsForChips().length > 0 || filters.nosub.length > 0 || filters.nochan.length > 0,
  ].filter(Boolean).length

  const summaryLine = `${filters.format === 'longform' ? 'Long-form' : 'Shorts'} · ${label(filters.metric)} · ${label(filters.comparison)}`

  function openPanel() {
    setIsPanelOpen(true)
  }

  function closePanel() {
    setIsPanelOpen(false)
    setOpenDropdown(null)
  }

  // Body scroll lock + Escape-to-close while the sheet is open. Only relevant below md
  // in practice (the Filters button that opens it doesn't exist at md+), but scoped to
  // isPanelOpen regardless -- harmless if the viewport is ever widened past md while it
  // happens to be open, since the sheet's own styling falls back to the static desktop
  // layout at that width anyway.
  useEffect(() => {
    if (!isPanelOpen) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function handleKeyDown(e) {
      if (e.key === 'Escape') closePanel()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isPanelOpen])

  // If the sheet is ever left open while the viewport crosses back up to md (e.g. a
  // tablet rotated, or a resize), close it -- otherwise the body scroll lock above would
  // stay engaged at a width where the "Filters" button (the only way to close it) no
  // longer exists.
  useEffect(() => {
    const mql = window.matchMedia('(min-width: 768px)')
    function handleChange(e) {
      if (e.matches) {
        setIsPanelOpen(false)
        setOpenDropdown(null)
      }
    }
    mql.addEventListener('change', handleChange)
    return () => mql.removeEventListener('change', handleChange)
  }, [])

  const exclusionChipsProps = {
    extraChips: categoryState.offSlugsForChips().map((slug) => ({
      key: `nocat:${slug}`,
      label: `${categoryBySlug(slug).displayName} (off)`,
      onRemove: () => categoryState.setOn(slug, true),
    })),
    nosub: filters.nosub,
    nochan: filters.nochan,
    tree,
    onRemoveNosub: (name) => setNosubNochan(filters.nosub.filter((s) => s !== name), filters.nochan),
    onRemoveNochan: (id) => setNosubNochan(filters.nosub, filters.nochan.filter((c) => c !== id)),
    onClearAll: handleClearAllExclusions,
  }

  return (
    <>
    <div className="mb-8 space-y-4 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
      {/* Mobile-only backdrop, shown while the sheet below is open. Above the header too
          (z-40, full-viewport), so the header's icon buttons aren't reachable behind it --
          tapping anywhere outside the sheet just closes it, like the backdrop everywhere else. */}
      {isPanelOpen && (
        <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={closePanel} aria-hidden="true" />
      )}

      {/* Lines 1-3 (category/subcategory/channel, sport/published/duration,
          metric/comparison/format): unchanged content and order, one instance. At md+ it's
          always this exact static block (matching the layout before mobile support existed).
          Below md it's hidden unless isPanelOpen, in which case it becomes a sheet sliding
          up from the bottom -- same components, same state, just repositioned. */}
      <div
        className={
          isPanelOpen
            ? 'fixed inset-x-0 bottom-0 z-50 max-h-[85vh] flex flex-col bg-white dark:bg-gray-900 rounded-t-2xl shadow-lg md:static md:inset-auto md:z-auto md:max-h-none md:flex md:flex-col md:bg-transparent md:dark:bg-transparent md:rounded-none md:shadow-none'
            : 'hidden md:flex md:flex-col'
        }
        {...(isPanelOpen ? { role: 'dialog', 'aria-modal': true, 'aria-labelledby': 'mobile-filters-heading' } : {})}
      >
        {isPanelOpen && (
          <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800 shrink-0">
            <h2 id="mobile-filters-heading" className="text-base font-semibold text-gray-900 dark:text-gray-100">
              Filters
            </h2>
            <button
              type="button"
              onClick={closePanel}
              // If a category/duration dropdown is open, this button sits outside both
              // refs the document-level mousedown handler checks, so it would otherwise
              // fire first on mousedown, collapse the dropdown, and -- since the sheet is
              // bottom-anchored with no fixed height -- shift this header down before the
              // matching click lands, missing the button entirely. Stopping the mousedown
              // here leaves this button's own onClick (which already closes any open
              // dropdown itself, via closePanel) as the only thing that runs.
              onMouseDown={(e) => e.stopPropagation()}
              aria-label="Close filters"
              className="flex items-center justify-center w-10 h-10 -m-2 text-gray-500 dark:text-gray-400"
            >
              <XIcon className="w-5 h-5" aria-hidden="true" />
            </button>
          </div>
        )}

      <div className={isPanelOpen ? 'space-y-4 overflow-y-auto p-4' : 'space-y-4 md:space-y-4'}>
      {/* Line 1: category / subcategory / channel */}
      <div ref={categoryDropdownsRef}>
        <span className="text-sm text-gray-700 dark:text-gray-300 block mb-1">Category / subcategory / channel</span>
        <ChannelFilterDropdowns
          status={treeStatus}
          tree={tree}
          nosub={filters.nosub}
          nochan={filters.nochan}
          sports={filters.sports}
          categoryState={categoryState}
          onSetNosubNochan={setNosubNochan}
          openSlug={openDropdown}
          onOpenSlugChange={setOpenDropdown}
        />

        <ExclusionChips {...exclusionChipsProps} />
      </div>

      {/* Line 2: Sport, Published, Duration, side by side. items-start on the outer row so
          Duration's panel opening (which grows only its own column) never re-centres Sport
          or Published -- each inner group keeps its own items-center for its label+control. */}
      <div className="flex flex-wrap items-start gap-6">
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

        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-gray-700 dark:text-gray-300" htmlFor="date-filter">
            Published
          </label>
          <select
            id="date-filter"
            value={filters.date}
            onChange={(e) => handleDateChange(e.target.value)}
            className="h-[31px] border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 rounded px-2 py-1 text-sm"
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

        {filters.format === 'longform' && (
          <div ref={durationDropdownRef} className="flex items-start gap-3">
            <label className="text-sm text-gray-700 dark:text-gray-300" htmlFor="duration-filter">
              Duration
            </label>
            <DurationDropdown
              id="duration-filter"
              nodur={filters.nodur}
              onSetNodur={setNodur}
              isOpen={openDropdown === 'duration'}
              onToggleOpen={() => setOpenDropdown(openDropdown === 'duration' ? null : 'duration')}
            />
          </div>
        )}
      </div>

      {/* Line 3: metric, comparison, format */}
      <div className="flex flex-wrap gap-6">
        <ToggleGroup options={METRICS} value={filters.metric} onChange={(v) => setFilter('metric', v)} />
        <ToggleGroup
          options={COMPARISONS}
          value={filters.comparison}
          onChange={(v) => setFilter('comparison', v)}
          getTitle={(v) => COMPARISON_TOOLTIPS[v]}
        />
        <ToggleGroup
          options={FORMATS}
          value={filters.format}
          onChange={(v) => setFilter('format', v)}
          renderLabel={(v) => (v === 'longform' ? 'Long-form' : 'Shorts')}
        />
      </div>
      </div>

      {isPanelOpen && (
        <div className="md:hidden shrink-0 p-4 border-t border-gray-200 dark:border-gray-800">
          <button
            type="button"
            onClick={closePanel}
            onMouseDown={(e) => e.stopPropagation()}
            className="w-full rounded border border-gray-900 dark:border-gray-100 bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900 py-2 text-sm font-medium"
          >
            Show results
          </button>
        </div>
      )}
      </div>

      {/* Line 4: keyword search -- stays visible outside the panel at every width */}
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

      {/* Mobile only: replaces the whole panel above (except the search line, which
          stays visible) with one button, a plain-text summary of the current sort, and
          the exclusion chips -- which must stay visible here regardless of whether the
          panel is open, so an active exclusion is never hidden. */}
      <div className="md:hidden mb-8 space-y-3">
        <button
          type="button"
          onClick={openPanel}
          className="relative inline-flex items-center gap-2 rounded border border-gray-300 dark:border-gray-700 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
        >
          Filters
          {badgeCount > 0 && (
            <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900 text-xs font-semibold">
              {badgeCount}
            </span>
          )}
        </button>
        <p className="text-sm text-gray-600 dark:text-gray-400">{summaryLine}</p>
        <ExclusionChips {...exclusionChipsProps} />
      </div>
    </>
  )
}
