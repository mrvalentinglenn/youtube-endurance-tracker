import { supabase } from './supabase'
import { dateRangeFor } from './filters'

// Every Supabase query detail lives here, for both routes. Neither the homepage sections
// nor the category page build a query themselves -- they all call fetchVideos.

const RAW_COLUMNS = { views: 'views', likes: 'likes', comments: 'comments' }
const SCORE_COLUMNS = { views: 'score_views', likes: 'score_likes', comments: 'score_comments' }
const SPORT_COLUMNS = { swimming: 'is_swimming', cycling: 'is_cycling', running: 'is_running', triathlon: 'is_triathlon' }

// fts is deliberately never selected: it's a large tsvector the front end never displays.
const SELECT_COLUMNS = [
  'video_id',
  'title',
  'thumbnail_url',
  'published_at',
  'duration_seconds',
  'channel_name',
  'avatar_url',
  'category',
  'views',
  'likes',
  'comments',
  'score_views',
  'score_likes',
  'score_comments',
  'is_still_growing',
].join(', ')

function quoteForInList(value) {
  return `"${value.replace(/"/g, '\\"')}"`
}

/**
 * categories: array of database category values (one for a homepage section, several
 * for a merged category page). filters: the object resolveFilters() returns. limit:
 * how many rows to fetch.
 */
export async function fetchVideos({ categories, filters, limit }) {
  const sortColumn = filters.comparison === 'relative' ? SCORE_COLUMNS[filters.metric] : RAW_COLUMNS[filters.metric]

  let query = supabase
    .from('videos_scored')
    .select(SELECT_COLUMNS)
    .in('category', categories)
    .eq('is_short', filters.format === 'shorts')

  const { from, to } = dateRangeFor(filters)
  if (from) query = query.gte('published_at', from.toISOString())
  if (to) query = query.lte('published_at', to.toISOString())

  if (filters.sports.length > 0) {
    // "At least one selected sport", not all of them: an .or() across the selected
    // is_* columns, never .and() -- a helmet brand tagged cycling and triathlon must
    // survive cycling alone being deselected.
    const clauses = filters.sports.map((slug) => `${SPORT_COLUMNS[slug]}.eq.true`).join(',')
    query = query.or(clauses)
  }

  if (filters.nosub.length > 0) {
    query = query.not('subcategory', 'in', `(${filters.nosub.map(quoteForInList).join(',')})`)
  }

  if (filters.q.trim()) {
    query = query.textSearch('fts', filters.q.trim(), { type: 'websearch', config: 'simple' })
  }

  // nullsFirst: false is load-bearing, not stylistic: Postgres sorts NULLs first on a
  // descending sort by default, which would put every unscored video at the top of
  // the Relative view -- exactly the hard rule CLAUDE.md forbids. The materialised
  // view's indexes are built desc nulls last specifically to match this.
  query = query.order(sortColumn, { ascending: false, nullsFirst: false }).limit(limit)

  const { data, error } = await query
  if (error) throw error
  return data
}
