import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { CATEGORIES, categoryBySlug, resolveFilters } from '../lib/filters'
import { fetchVideos } from '../lib/videos'
import FilterBar from '../components/FilterBar'
import VideoGrid from '../components/VideoGrid'
import ThemeToggle from '../components/ThemeToggle'
import SuggestChannelButton from '../components/SuggestChannelButton'

// One page, no pagination (NEXT_STEPS.md step 10f): 180 divides cleanly into every
// column count long-form (1/2/3/4) and Shorts (3/4/5) use, so neither grid ends ragged.
const PAGE_LIMIT = 180

export default function CategoryPage() {
  const { categories: categoriesParam } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const filters = resolveFilters(searchParams)

  const requestedSlugs = (categoriesParam || '').split(',').map((s) => s.trim()).filter(Boolean)
  const matched = requestedSlugs.map((slug) => categoryBySlug(slug)).filter(Boolean)
  // An unrecognised or empty slug list never blanks the page: fall back to every category
  // rather than showing nothing.
  const selectedCategories = matched.length > 0 ? matched : CATEGORIES
  const selectedSlugs = selectedCategories.map((c) => c.slug)
  const categoryDbValues = selectedCategories.map((c) => c.dbValue)

  // Category on/off lives in the path here, not a query param -- toggling navigates to a
  // new /category/... path, carrying every other filter unchanged. No chips and no
  // "clear" step for this level: there's nothing stored to clear, just a selection.
  const categoryState = {
    isOn: (slug) => selectedSlugs.includes(slug),
    setOn: (slug, on) => {
      const nextSlugs = on ? [...selectedSlugs, slug] : selectedSlugs.filter((s) => s !== slug)
      const orderedNextSlugs = CATEGORIES.map((c) => c.slug).filter((s) => nextSlugs.includes(s))
      navigate(`/category/${orderedNextSlugs.join(',')}?${searchParams.toString()}`)
    },
    offSlugsForChips: () => [],
  }

  const backToHomeParams = new URLSearchParams(searchParams)
  backToHomeParams.delete('nocat')

  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const categoriesKey = categoryDbValues.join(',')
  const sportsKey = filters.sports.join(',')
  const nosubKey = filters.nosub.join(',')
  const nochanKey = filters.nochan.join(',')
  const nodurKey = filters.nodur.join(',')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const data = await fetchVideos({ categories: categoryDbValues, filters, limit: PAGE_LIMIT })
        if (!cancelled) setVideos(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()

    return () => {
      cancelled = true
    }
    // filters and categoryDbValues are new references every render; their individual
    // fields are listed instead (categoriesKey/sportsKey/nosubKey/nochanKey/nodurKey stand
    // in for the array fields).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoriesKey, filters.metric, filters.comparison, filters.format, filters.date, filters.from, filters.to, sportsKey, nosubKey, nochanKey, nodurKey, filters.q])

  const heading = selectedCategories.map((c) => c.displayName).join(' + ')

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">YouTube Endurance Tracker</h1>
        <div className="flex items-center gap-2">
          <SuggestChannelButton />
          <ThemeToggle />
        </div>
      </div>

      <FilterBar categoryState={categoryState} />

      <Link to={`/?${backToHomeParams.toString()}`} className="text-sm text-blue-600 dark:text-blue-400 hover:underline mb-4 inline-block">
        &larr; Back to home
      </Link>

      <h2 className="text-lg font-semibold mb-3">{heading}</h2>

      {error && <p className="text-red-600 dark:text-red-400">Failed to load videos: {error}</p>}
      {loading && !error && <p className="text-gray-500 dark:text-gray-400">Loading…</p>}
      {!loading && !error && videos.length === 0 && (
        <p className="text-gray-500 dark:text-gray-400">No videos match the current filters.</p>
      )}
      {!loading && !error && videos.length > 0 && (
        <VideoGrid videos={videos} metric={filters.metric} comparison={filters.comparison} format={filters.format} variant="page" />
      )}
    </div>
  )
}
