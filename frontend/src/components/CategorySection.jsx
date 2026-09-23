import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchVideos } from '../lib/videos'
import VideoGrid from './VideoGrid'

const LONGFORM_LIMIT = 3
const SHORTS_LIMIT = 5

// One homepage section: fetches and renders and fails entirely on its own. No Promise.all
// anywhere -- five of these mounting independently is what makes the five queries run in
// parallel, and a slow or broken one never blanks the rest of the page.
export default function CategorySection({ category, filters, showMoreSearch }) {
  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const sportsKey = filters.sports.join(',')
  const nosubKey = filters.nosub.join(',')
  const nochanKey = filters.nochan.join(',')
  const nodurKey = filters.nodur.join(',')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      const limit = filters.format === 'shorts' ? SHORTS_LIMIT : LONGFORM_LIMIT
      try {
        const data = await fetchVideos({ categories: [category.dbValue], filters, limit })
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
    // filters is a resolved plain object, a new reference every render; depending on it
    // directly would refire this on every render regardless of whether any field
    // actually changed. Its individual fields are listed instead (sportsKey/nosubKey/
    // nochanKey/nodurKey stand in for the array fields, which are also new references
    // every render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category.dbValue, filters.metric, filters.comparison, filters.format, filters.date, filters.from, filters.to, sportsKey, nosubKey, nochanKey, nodurKey, filters.q])

  return (
    <section className="mb-10 border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
      <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 py-2.5">
        <h2 className="text-lg font-semibold text-center text-gray-900 dark:text-gray-100">
          {category.displayName}
        </h2>
      </div>

      <div className="px-4 pt-4">
        {error && (
          <p className="text-red-600 dark:text-red-400 text-sm">
            Failed to load {category.displayName}: {error}
          </p>
        )}
        {loading && !error && <p className="text-gray-500 dark:text-gray-400 text-sm">Loading…</p>}
        {!loading && !error && videos.length === 0 && (
          <p className="text-gray-500 dark:text-gray-400 text-sm">No videos match the current filters.</p>
        )}
        {!loading && !error && videos.length > 0 && (
          <VideoGrid videos={videos} metric={filters.metric} comparison={filters.comparison} format={filters.format} variant="section" />
        )}
      </div>

      <div className="px-4 py-4 flex justify-center">
        <Link
          to={`/category/${category.slug}?${showMoreSearch}`}
          className="text-sm border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 rounded px-4 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-800"
        >
          Show more
        </Link>
      </div>
    </section>
  )
}
