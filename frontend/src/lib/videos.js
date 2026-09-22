import { supabase } from './supabase'
import { dateRangeFor } from './filters'
import { stripStopwordsForSearch } from './stopwords'

// Every Supabase query detail lives here, for both routes. Neither the homepage sections
// nor the category page build a query themselves -- they all call fetchVideos.

const RAW_COLUMNS = { views: 'views', likes: 'likes', comments: 'comments' }
const SCORE_COLUMNS = { views: 'score_views', likes: 'score_likes', comments: 'score_comments' }
const SPORT_COLUMNS = { swimming: 'is_swimming', cycling: 'is_cycling', running: 'is_running', triathlon: 'is_triathlon' }

// fts is deliberately never selected here: it's a large tsvector the front end never
// displays. Only step 2 (below) reads full display columns, from videos_scored.
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

// Every filter except category and format -- shared by both step-1 sources
// (videos_slim and videos_search both carry the same subcategory/channel/sport/date
// columns as videos_scored).
function applyCommonFilters(query, filters) {
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

  return query
}

// --- Step 1: rank against a slim source (videos_slim, or videos_search for a keyword) ---
//
// Neither slim view has a per-sort-column index, only (category, is_short) -- and both are
// physically stored in that order (NEXT_STEPS.md step 10f), so this reads one short
// contiguous range instead of scanning the whole thing. With no pre-sorted index to walk,
// Postgres has no "walk in order, discard non-matching rows" plan available regardless of
// how rare an extra filter makes the match. videos_search additionally carries fts and its
// own GIN index, sized the same way for the same reason.
function buildRankedQuery(table, category, filters, limit, sortColumn, ftsQuery) {
  let query = supabase
    .from(table)
    .select(`video_id, ${sortColumn}`)
    .eq('category', category)
    .eq('is_short', filters.format === 'shorts')

  query = applyCommonFilters(query, filters)

  if (ftsQuery) {
    query = query.textSearch('fts', ftsQuery, { type: 'websearch', config: 'simple' })
  }

  // desc nulls last, then video_id ascending as a tiebreaker. Raw counts and scores tie
  // often (many videos share 0 comments), and without a tiebreaker the order among tied
  // rows is whatever this query's in-memory sort happens to produce -- not guaranteed to
  // agree with a second category's tie order when merging. Costs nothing extra: the sort
  // already happens in memory on this view's own small per-category result.
  return query
    .order(sortColumn, { ascending: false, nullsFirst: false })
    .order('video_id', { ascending: true })
    .limit(limit)
}

async function fetchRanking(table, category, filters, limit, sortColumn, ftsQuery) {
  const { data, error } = await buildRankedQuery(table, category, filters, limit, sortColumn, ftsQuery)
  if (error) throw error
  return data.map((row) => ({ video_id: row.video_id, sortValue: row[sortColumn] }))
}

// Mirrors step 1's own ORDER BY exactly -- desc, nulls last, then video_id ascending --
// so merging several categories' already-ranked lists in the browser reproduces the same
// order a single ranked query would give, with a deterministic answer among ties.
function compareRanked(a, b) {
  const aNull = a.sortValue === null || a.sortValue === undefined
  const bNull = b.sortValue === null || b.sortValue === undefined
  if (aNull && bNull) return a.video_id < b.video_id ? -1 : 1
  if (aNull) return 1
  if (bNull) return -1
  if (a.sortValue !== b.sortValue) return b.sortValue - a.sortValue
  return a.video_id < b.video_id ? -1 : 1
}

// --- Step 2: full display rows for an exact set of video_ids, from videos_scored --------
async function fetchFullRows(ids) {
  if (ids.length === 0) return []
  const { data, error } = await supabase.from('videos_scored').select(SELECT_COLUMNS).in('video_id', ids)
  if (error) throw error
  return data
}

// .in() returns rows in no guaranteed order, so the browser reorders them back into the
// order `ids` was ranked in -- that ordering IS the ranking; rank is positional on top of
// it. An id step 2 doesn't return (a video removed between the two calls, rare) is simply
// skipped rather than breaking the page.
function reorderByIds(rows, ids) {
  const byId = new Map(rows.map((row) => [row.video_id, row]))
  return ids.map((id) => byId.get(id)).filter(Boolean)
}

async function fetchTwoStep({ table, categories, filters, limit, sortColumn, ftsQuery }) {
  if (categories.length <= 1) {
    const ranked = await fetchRanking(table, categories[0], filters, limit, sortColumn, ftsQuery)
    const ids = ranked.map((r) => r.video_id)
    return reorderByIds(await fetchFullRows(ids), ids)
  }

  // One full-`limit` request per category, in parallel, merged and sliced in the browser
  // -- any video in the combined top `limit` must be in its own category's top `limit`,
  // so asking each for less would risk dropping one early.
  const rankings = await Promise.all(
    categories.map((category) => fetchRanking(table, category, filters, limit, sortColumn, ftsQuery))
  )
  const merged = rankings.flat().sort(compareRanked).slice(0, limit)
  const ids = merged.map((r) => r.video_id)
  return reorderByIds(await fetchFullRows(ids), ids)
}

/**
 * categories: array of database category values (one for a homepage section, one or
 * several for a category page). filters: the object resolveFilters() returns. limit:
 * how many rows to return.
 */
export async function fetchVideos({ categories, filters, limit }) {
  const sortColumn = filters.comparison === 'relative' ? SCORE_COLUMNS[filters.metric] : RAW_COLUMNS[filters.metric]
  const rawQuery = filters.q.trim()

  if (!rawQuery) {
    return fetchTwoStep({ table: 'videos_slim', categories, filters, limit, sortColumn, ftsQuery: null })
  }

  // videos_search carries the same slim columns as videos_slim, plus fts and its own GIN
  // index. Stopwords are stripped from the search text only (never from the URL/search
  // box's own stored value), and only for a query of two or more words -- see
  // stopwords.js.
  const ftsQuery = await stripStopwordsForSearch(rawQuery)
  return fetchTwoStep({ table: 'videos_search', categories, filters, limit, sortColumn, ftsQuery })
}
