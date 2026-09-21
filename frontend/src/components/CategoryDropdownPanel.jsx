import { useEffect, useRef, useState } from 'react'
import { SPORTS } from '../lib/filters'
import {
  categoryTriState,
  clearCategoryExclusions,
  subcategoryState,
  toggleChannel,
  toggleSubcategory,
} from '../lib/channelFilterState'

const SPORT_COLUMN_BY_SLUG = Object.fromEntries(SPORTS.map((s) => [s.slug, s.column]))

// Native checkboxes have no indeterminate JSX prop -- it's a DOM property, set via ref.
function TriStateCheckbox({ state, onChange, disabled, className }) {
  const ref = useRef(null)
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = state === 'partial'
  }, [state])
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={state === 'checked'}
      onChange={onChange}
      disabled={disabled}
      className={className}
    />
  )
}

// One dropdown's contents. Parent (ChannelFilterDropdowns) owns which dropdown is open;
// this component owns only its own search text and manual expand/collapse overrides,
// which reset naturally each time it mounts (the panel unmounts on close).
export default function CategoryDropdownPanel({
  category,
  bucket,
  nosub,
  nochan,
  sports,
  isOn,
  isLastCategoryOn,
  onSetOn,
  onSetNosubNochan,
}) {
  const [search, setSearch] = useState('')
  const [manualExpanded, setManualExpanded] = useState({})

  const catState = categoryTriState(bucket, nosub, nochan, isOn)
  const catDisabled = catState === 'checked' && isLastCategoryOn

  function handleCategoryToggle() {
    if (catState === 'checked') {
      onSetOn(false)
    } else if (catState === 'unchecked') {
      onSetOn(true)
    } else {
      // partial -> checked: category is already on, only the inner exclusions clear.
      const { nosub: nextNosub, nochan: nextNochan } = clearCategoryExclusions(bucket, nosub, nochan)
      onSetNosubNochan(nextNosub, nextNochan)
    }
  }

  function handleSubcategoryToggle(subName, channels) {
    const { nosub: nextNosub, nochan: nextNochan } = toggleSubcategory(subName, channels, nosub, nochan)
    onSetNosubNochan(nextNosub, nextNochan)
  }

  function handleChannelToggle(channel, subName, channels) {
    const { nosub: nextNosub, nochan: nextNochan } = toggleChannel(channel, subName, channels, nosub, nochan)
    onSetNosubNochan(nextNosub, nextNochan)
  }

  const searchLower = search.trim().toLowerCase()

  return (
    <div className="p-3">
      <label className="flex items-center gap-2 font-medium text-sm text-gray-900 dark:text-gray-100 pb-2 border-b border-gray-200 dark:border-gray-800">
        <TriStateCheckbox
          state={catState}
          onChange={handleCategoryToggle}
          disabled={catDisabled}
          className="shrink-0"
        />
        {category.displayName}
        {catDisabled && (
          <span className="text-xs font-normal text-gray-400 dark:text-gray-500">(last category on)</span>
        )}
      </label>

      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search channels..."
        className="mt-2 w-full border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500 rounded px-2 py-1 text-sm"
      />

      <div className="mt-2 max-h-72 overflow-y-auto space-y-1">
        {Object.entries(bucket.subcategories).map(([subName, subBucket]) => {
          const matchingChannels = searchLower
            ? subBucket.channels.filter((c) => c.name.toLowerCase().includes(searchLower))
            : subBucket.channels
          if (searchLower && matchingChannels.length === 0) return null

          const hasExcludedChannel = subBucket.channels.some((c) => nochan.includes(c.channel_id))
          const hasSearchMatch = searchLower.length > 0
          const defaultExpanded = hasExcludedChannel
          const expanded = hasSearchMatch ? true : (manualExpanded[subName] ?? defaultExpanded)

          const subState = subcategoryState(subName, subBucket.channels, nosub, nochan)

          return (
            <div key={subName} className="pt-1">
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setManualExpanded((prev) => ({ ...prev, [subName]: !expanded }))}
                  className="w-4 text-xs text-gray-500 dark:text-gray-400 shrink-0"
                  aria-label={expanded ? `Collapse ${subName}` : `Expand ${subName}`}
                >
                  {expanded ? '▾' : '▸'}
                </button>
                <label className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200 flex-1">
                  <TriStateCheckbox
                    state={subState}
                    onChange={() => handleSubcategoryToggle(subName, subBucket.channels)}
                  />
                  {subName}
                </label>
              </div>

              {expanded && (
                <div className="pl-[1.375rem] pt-1 space-y-0.5">
                  {matchingChannels.map((channel) => {
                    const excluded = nosub.includes(subName) || nochan.includes(channel.channel_id)
                    const dimmed =
                      sports.length > 0 && !sports.some((slug) => channel[SPORT_COLUMN_BY_SLUG[slug]])
                    return (
                      <label
                        key={channel.channel_id}
                        className={`flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 ${dimmed ? 'opacity-40' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={!excluded}
                          onChange={() => handleChannelToggle(channel, subName, subBucket.channels)}
                        />
                        {channel.name}
                      </label>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
