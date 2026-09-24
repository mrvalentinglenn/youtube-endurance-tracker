// Single source of truth for the three forms every category name takes: the database
// value (inconsistent casing -- real, must be matched exactly), the URL slug, and the
// display name. Nothing else in the front end may hardcode a category name in any form.
// Fixed order is the homepage section order, a product decision, not alphabetical.
export const CATEGORIES = [
  { dbValue: 'Brand', slug: 'brands', displayName: 'Brands' },
  { dbValue: 'Influencer', slug: 'influencers', displayName: 'Influencers' },
  { dbValue: 'Professional athlete', slug: 'athletes', displayName: 'Professional Athletes' },
  { dbValue: 'Professional Team', slug: 'teams', displayName: 'Professional Teams' },
  { dbValue: 'Race Organizer', slug: 'organizers', displayName: 'Race Organizers' },
]

export function categoryBySlug(slug) {
  return CATEGORIES.find((c) => c.slug === slug)
}

export function categoryByDbValue(dbValue) {
  return CATEGORIES.find((c) => c.dbValue === dbValue)
}

export const SPORTS = [
  { slug: 'swimming', column: 'is_swimming', displayName: 'Swimming' },
  { slug: 'cycling', column: 'is_cycling', displayName: 'Cycling' },
  { slug: 'running', column: 'is_running', displayName: 'Running' },
  { slug: 'triathlon', column: 'is_triathlon', displayName: 'Triathlon' },
]

// Long-form only (NEXT_STEPS.md step 10g) -- Shorts are all short, so the bucket edges
// would mean nothing there. min/max are in duration_seconds, inclusive on both ends;
// '45+' has no max. A video with duration_seconds NULL or 0 (the API's P0D, meaning
// unavailable, not zero-length) matches none of these and is excluded the moment any
// bucket is switched off, shown again once every bucket is back on.
export const DURATION_BUCKETS = [
  { key: 'u1', displayName: 'Under 1 min', min: 1, max: 59 },
  { key: '1-3', displayName: '1-3 min', min: 60, max: 179 },
  { key: '3-20', displayName: '3-20 min', min: 180, max: 1199 },
  { key: '20-45', displayName: '20-45 min', min: 1200, max: 2699 },
  { key: '45+', displayName: '45+ min', min: 2700, max: null },
]

export const DATE_OPTIONS = [
  { value: '6m', displayName: 'Last 6 months', months: 6 },
  { value: '1y', displayName: 'Last year', months: 12 },
  { value: '2y', displayName: 'Last 2 years', months: 24 },
  { value: '3y', displayName: 'Last 3 years', months: 36 },
  { value: 'all', displayName: 'All time', months: null },
  { value: 'custom', displayName: 'Custom period', months: null },
]

export const DEFAULT_FILTERS = {
  metric: 'views',
  comparison: 'absolute',
  format: 'longform',
  date: 'all',
  from: '',
  to: '',
  sports: [],
  nosub: [],
  nochan: [],
  nocat: [],
  nodur: [],
  q: '',
}

const VALID_METRICS = ['views', 'likes', 'comments']
const VALID_COMPARISONS = ['absolute', 'relative']
const VALID_FORMATS = ['longform', 'shorts']
const VALID_DATES = DATE_OPTIONS.map((d) => d.value)
const VALID_SPORT_SLUGS = SPORTS.map((s) => s.slug)
const VALID_CATEGORY_SLUGS = CATEGORIES.map((c) => c.slug)
const VALID_DURATION_KEYS = DURATION_BUCKETS.map((b) => b.key)

function parseCommaList(raw, allowed) {
  if (!raw) return []
  const allowedSet = allowed ? new Set(allowed) : null
  return raw
    .split(',')
    .map((v) => v.trim())
    .filter((v) => v !== '' && (!allowedSet || allowedSet.has(v)))
}

function oneOf(raw, allowed, fallback) {
  return allowed.includes(raw) ? raw : fallback
}

// The single resolver. Takes a URLSearchParams (from either route) and returns every
// filter resolved to its URL value or its default -- a missing or invalid param
// resolves to the default, so a bare or malformed URL is always a valid state.
export function resolveFilters(searchParams) {
  const date = oneOf(searchParams.get('date'), VALID_DATES, DEFAULT_FILTERS.date)
  return {
    metric: oneOf(searchParams.get('metric'), VALID_METRICS, DEFAULT_FILTERS.metric),
    comparison: oneOf(searchParams.get('comparison'), VALID_COMPARISONS, DEFAULT_FILTERS.comparison),
    format: oneOf(searchParams.get('format'), VALID_FORMATS, DEFAULT_FILTERS.format),
    date,
    from: date === 'custom' ? searchParams.get('from') || '' : '',
    to: date === 'custom' ? searchParams.get('to') || '' : '',
    sports: parseCommaList(searchParams.get('sports'), VALID_SPORT_SLUGS),
    // nosub and nochan have no allow-list: subcategories and channel IDs now come from
    // a fetch (channels_public), not a hardcoded list, and resolveFilters runs
    // synchronously before that fetch can complete. A stale or invalid entry simply
    // matches nothing in the fetched tree and is inert -- same as a dead nochan ID.
    nosub: parseCommaList(searchParams.get('nosub')),
    nochan: parseCommaList(searchParams.get('nochan')),
    nocat: parseCommaList(searchParams.get('nocat'), VALID_CATEGORY_SLUGS),
    nodur: parseCommaList(searchParams.get('nodur'), VALID_DURATION_KEYS),
    q: searchParams.get('q') || '',
  }
}

// Writes one filter into a URLSearchParams, omitting the param entirely when the value
// equals the default so URLs stay minimal and a return-to-defaults is a bare URL.
export function withParam(searchParams, key, value) {
  const next = new URLSearchParams(searchParams)
  const isDefault =
    Array.isArray(DEFAULT_FILTERS[key]) ? Array.isArray(value) && value.length === 0 : value === DEFAULT_FILTERS[key]

  if (isDefault) {
    next.delete(key)
  } else if (Array.isArray(value)) {
    next.set(key, value.join(','))
  } else {
    next.set(key, value)
  }
  return next
}

// UTC date range for the resolved `date`/`from`/`to` filters. Returns { from, to } as
// Date objects or null. "All time" and an incomplete custom range both mean no restriction.
export function dateRangeFor(filters) {
  if (filters.date === 'all') return { from: null, to: null }

  if (filters.date === 'custom') {
    const from = filters.from ? new Date(`${filters.from}T00:00:00Z`) : null
    const to = filters.to ? new Date(`${filters.to}T23:59:59Z`) : null
    return { from, to }
  }

  const option = DATE_OPTIONS.find((d) => d.value === filters.date)
  const months = option ? option.months : DATE_OPTIONS.find((d) => d.value === DEFAULT_FILTERS.date).months
  const from = new Date()
  from.setUTCMonth(from.getUTCMonth() - months)
  return { from, to: null }
}
