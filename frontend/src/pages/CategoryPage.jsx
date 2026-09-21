import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { CATEGORIES, categoryBySlug, resolveFilters } from '../lib/filters'
import { fetchVideos } from '../lib/videos'
import FilterBar from '../components/FilterBar'
import CategoryPills from '../components/CategoryPills'
import VideoGrid from '../components/VideoGrid'
import ThemeToggle from '../components/ThemeToggle'

const PAGE_LIMIT = 60

export default function CategoryPage() {
  const { categories: categoriesParam } = useParams()
  const [searchParams] = useSearchParams()
  const filters = resolveFilters(searchParams)

  const requestedSlugs = (categoriesParam || '').split(',').map((s) => s.trim()).filter(Boolean)
  const matched = requestedSlugs.map((slug) => categoryBySlug(slug)).filter(Boolean)
  // An unrecognised or empty slug list never blanks the page: fall back to every category
  // rather than showing nothing.
  const selectedCategories = matched.length > 0 ? matched : CATEGORIES
  const selectedSlugs = selectedCategories.map((c) => c.slug)
  const categoryDbValues = selectedCategories.map((c) => c.dbValue)

  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const categoriesKey = categoryDbValues.join(',')
  const sportsKey = filters.sports.join(',')
  const nosubKey = filters.nosub.join(',')

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
    // fields are listed instead (categoriesKey/sportsKey/nosubKey stand in for the
    // array fields).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoriesKey, filters.metric, filters.comparison, filters.format, filters.date, filters.from, filters.to, sportsKey, nosubKey, filters.q])

  const heading = selectedCategories.map((c) => c.displayName).join(' + ')

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">YouTube Endurance Tracker</h1>
        <ThemeToggle />
      </div>

      <FilterBar />
      <CategoryPills selectedSlugs={selectedSlugs} otherParamsString={searchParams.toString()} />

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
