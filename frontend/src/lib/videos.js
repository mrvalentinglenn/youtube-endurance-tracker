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

// One category, one query -- every other filter identical regardless of how many
// categories the caller is asking for. category = an exact match (not .in()), so a
// single-category request always lands on the (category, is_short, <col>) index
// (see DECISIONS.md, 2026-09-21, the statement-timeout investigation): that index
// can't serve an IN-list in sort order, which is exactly why multi-category requests
// are split into one of these per category rather than one query with .in().
function buildCategoryQuery(category, filters, limit, sortColumn) {
  let query = supabase
    .from('videos_scored')
    .select(SELECT_COLUMNS)
    .eq('category', category)
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

  if (filters.nochan.length > 0) {
    query = query.not('channel_id', 'in', `(${filters.nochan.map(quoteForInList).join(',')})`)
  }

  if (filters.q.trim()) {
    query = query.textSearch('fts', filters.q.trim(), { type: 'websearch', config: 'simple' })
  }

  // nullsFirst: false is load-bearing, not stylistic: Postgres sorts NULLs first on a
  // descending sort by default, which would put every unscored video at the top of
  // the Relative view -- exactly the hard rule CLAUDE.md forbids. The materialised
  // view's indexes are built desc nulls last specifically to match this, and the
  // client-side merge below (compareDescNullsLast) has to reproduce the same rule.
  return query.order(sortColumn, { ascending: false, nullsFirst: false }).limit(limit)
}

// Mirrors "desc, nulls last" exactly, so merging several categories' already-sorted
// top-`limit` results in the browser reproduces the same order a single query would
// have returned. Never let a NULL (no score) sort above a real number.
function compareDescNullsLast(a, b, sortColumn) {
  const aValue = a[sortColumn]
  const bValue = b[sortColumn]
  const aIsNull = aValue === null || aValue === undefined
  const bIsNull = bValue === null || bValue === undefined
  if (aIsNull && bIsNull) return 0
  if (aIsNull) return 1
  if (bIsNull) return -1
  return bValue - aValue
}

/**
 * categories: array of database category values (one for a homepage section, one or
 * several for a category page). filters: the object resolveFilters() returns. limit:
 * how many rows to return.
 */
export async function fetchVideos({ categories, filters, limit }) {
  const sortColumn = filters.comparison === 'relative' ? SCORE_COLUMNS[filters.metric] : RAW_COLUMNS[filters.metric]

  if (categories.length <= 1) {
    const { data, error } = await buildCategoryQuery(categories[0], filters, limit, sortColumn)
    if (error) throw error
    return data
  }

  // More than one category: no single index can both lead with category (for a fast
  // per-category walk) and serve an IN-list in sort order in one scan, so this fans
  // out one full-`limit` request per category instead of one request with .in().
  // Any video in the combined top `limit` must be in its own category's top `limit`
  // -- asking each category for anything less would risk dropping one early.
  const responses = await Promise.all(
    categories.map((category) => buildCategoryQuery(category, filters, limit, sortColumn))
  )

  // All-or-nothing: one category's failure must not produce a ranking that looks
  // complete but is quietly missing a whole category's videos.
  const failed = responses.find((r) => r.error)
  if (failed) throw failed.error

  const merged = responses.flatMap((r) => r.data)
  merged.sort((a, b) => compareDescNullsLast(a, b, sortColumn))
  return merged.slice(0, limit)
}
