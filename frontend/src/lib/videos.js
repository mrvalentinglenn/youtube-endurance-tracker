import { supabase } from './supabase'

// Every Supabase query detail for the results list lives here. Step 10 extends this
// function (filters, keyword search) instead of components touching Supabase directly.

const RESULT_LIMIT = 60
const DEFAULT_WINDOW_DAYS = 365 // CLAUDE.md's default: "last year". Step 10 replaces this
                                 // with a real publication-date filter.

const RAW_COLUMNS = { views: 'views', likes: 'likes', comments: 'comments' }
const SCORE_COLUMNS = { views: 'score_views', likes: 'score_likes', comments: 'score_comments' }

const SELECT_COLUMNS = [
  'video_id',
  'title',
  'thumbnail_url',
  'published_at',
  'duration_seconds',
  'channel_name',
  'category',
  'views',
  'likes',
  'comments',
  'score_views',
  'score_likes',
  'score_comments',
  'is_still_growing',
].join(', ')

export async function fetchVideos({ metric = 'views', comparison = 'absolute' } = {}) {
  const sortColumn = comparison === 'relative' ? SCORE_COLUMNS[metric] : RAW_COLUMNS[metric]

  const cutoff = new Date()
  cutoff.setUTCDate(cutoff.getUTCDate() - DEFAULT_WINDOW_DAYS)

  const { data, error } = await supabase
    .from('videos_scored')
    .select(SELECT_COLUMNS)
    .gte('published_at', cutoff.toISOString())
    // Format is a required choice (CLAUDE.md), hardcoded to long-form for now. Step 10
    // replaces this with a real Shorts/long-form control.
    .eq('is_short', false)
    // nullsFirst: false is load-bearing, not stylistic: Postgres sorts NULLs first on a
    // descending sort by default, which would put every unscored video at the top of
    // the Relative view -- exactly the hard rule CLAUDE.md forbids.
    .order(sortColumn, { ascending: false, nullsFirst: false })
    .limit(RESULT_LIMIT)

  if (error) throw error
  return data
}
