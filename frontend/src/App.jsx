import { useEffect, useState } from 'react'
import { fetchVideos } from './lib/videos'
import VideoCard from './components/VideoCard'

const METRICS = ['views', 'likes', 'comments']
const COMPARISONS = ['absolute', 'relative']

// Format is a required choice (CLAUDE.md); hardcoded to long-form for now, matching
// videos.js's hardcoded filter. Step 10 replaces both with a real control.
const IS_SHORT = false

const GRID_COLUMNS = {
  false: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4', // long-form
  true: 'grid-cols-3 sm:grid-cols-4 lg:grid-cols-5', // Shorts
}

// Positional, not stored: a video's rank belongs to the current query, not the video
// itself. Takes an offset so pagination (not built yet) won't need to rewrite this.
function rankFor(index, offset = 0) {
  return offset + index + 1
}

function label(word) {
  return word[0].toUpperCase() + word.slice(1)
}

export default function App() {
  const [metric, setMetric] = useState('views')
  const [comparison, setComparison] = useState('absolute')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const data = await fetchVideos({ metric, comparison })
        if (!cancelled) setRows(data)
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
  }, [metric, comparison])

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">YouTube Endurance Tracker</h1>

      <div className="flex flex-wrap gap-6 mb-6">
        <div className="flex gap-2">
          {METRICS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMetric(m)}
              aria-pressed={metric === m}
              className={`px-3 py-1 rounded border text-sm ${
                metric === m ? 'bg-gray-900 text-white border-gray-900' : 'border-gray-300 text-gray-700'
              }`}
            >
              {label(m)}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          {COMPARISONS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setComparison(c)}
              aria-pressed={comparison === c}
              className={`px-3 py-1 rounded border text-sm ${
                comparison === c ? 'bg-gray-900 text-white border-gray-900' : 'border-gray-300 text-gray-700'
              }`}
            >
              {label(c)}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-red-600">Failed to load videos: {error}</p>}

      {loading && !error && <p className="text-gray-500">Loading…</p>}

      {!loading && !error && (
        <div className={`grid ${GRID_COLUMNS[IS_SHORT]} gap-4`}>
          {rows.map((video, index) => (
            <VideoCard
              key={video.video_id}
              video={video}
              metric={metric}
              comparison={comparison}
              rank={rankFor(index)}
              isShort={IS_SHORT}
            />
          ))}
        </div>
      )}
    </div>
  )
}
