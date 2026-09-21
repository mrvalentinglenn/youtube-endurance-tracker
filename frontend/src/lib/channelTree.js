import { useEffect, useState } from 'react'
import { supabase } from './supabase'
import { CATEGORIES, categoryByDbValue } from './filters'

// channels_public: readable by anon, unlike the channels table itself. 342 rows --
// small enough to fetch whole and build the tree client-side rather than querying
// per-dropdown.
const CHANNELS_PUBLIC_COLUMNS = 'channel_id, name, category, subcategory, is_swimming, is_cycling, is_running, is_triathlon'

function buildTree(rows) {
  const bySlug = {}
  for (const category of CATEGORIES) {
    bySlug[category.slug] = { dbValue: category.dbValue, total: 0, channelIds: [], subcategories: {} }
  }

  const channelsById = new Map()
  const subcategoryToCategorySlug = new Map()

  for (const row of rows) {
    const category = categoryByDbValue(row.category)
    // Defensive, not expected: a category value channels_public returns that isn't one
    // of the 5 known ones is skipped rather than crashing the whole tree.
    if (!category) continue

    const bucket = bySlug[category.slug]
    bucket.total += 1
    bucket.channelIds.push(row.channel_id)

    if (!bucket.subcategories[row.subcategory]) {
      bucket.subcategories[row.subcategory] = { channels: [], total: 0 }
    }
    bucket.subcategories[row.subcategory].channels.push(row)
    bucket.subcategories[row.subcategory].total += 1

    channelsById.set(row.channel_id, { name: row.name, categorySlug: category.slug, subcategory: row.subcategory })
    subcategoryToCategorySlug.set(row.subcategory, category.slug)
  }

  // Alphabetical within each subcategory, so the list is scannable and stable across
  // re-renders (the fetch order isn't guaranteed otherwise).
  for (const bucket of Object.values(bySlug)) {
    for (const subBucket of Object.values(bucket.subcategories)) {
      subBucket.channels.sort((a, b) => a.name.localeCompare(b.name))
    }
  }

  return { bySlug, channelsById, subcategoryToCategorySlug }
}

// Fetches once per mount (each full route change remounts the page, and therefore
// FilterBar; filter-only interactions within a page never do). status is 'loading',
// 'ready' or 'error' -- on 'error' the dropdowns show a message and disable themselves,
// but nothing here blocks fetchVideos, which doesn't depend on this hook at all.
export function useChannelTree() {
  const [state, setState] = useState({ status: 'loading', tree: null })

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const { data, error } = await supabase.from('channels_public').select(CHANNELS_PUBLIC_COLUMNS)
        if (error) throw error
        if (!cancelled) setState({ status: 'ready', tree: buildTree(data) })
      } catch {
        if (!cancelled) setState({ status: 'error', tree: null })
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
