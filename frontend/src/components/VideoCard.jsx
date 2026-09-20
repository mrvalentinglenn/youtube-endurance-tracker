const SCORE_COLUMNS = { views: 'score_views', likes: 'score_likes', comments: 'score_comments' }

const PROMOTION_CATEGORY = 'Brand'
const PROMOTION_SCORE_THRESHOLD = 500
const PROMOTION_TOOLTIP =
  'Extreme outlier scores may indicate this video was used for paid advertising.'

function formatCount(value) {
  // NULL means the creator hid likes or disabled comments -- never show 0, which would
  // record a disabled feature as an absence of engagement.
  if (value === null || value === undefined) return '—'
  return value.toLocaleString()
}

function formatDate(publishedAt) {
  return new Date(publishedAt).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function formatScore(score) {
  if (score === null || score === undefined) return 'no score'
  if (score >= 1000) return `${(score / 1000).toFixed(1)}K`
  return score.toFixed(1)
}

export default function VideoCard({ video, metric, comparison }) {
  const showScore = comparison === 'relative'
  const score = video[SCORE_COLUMNS[metric]]
  const hasScore = score !== null && score !== undefined
  const showPromotionNote =
    showScore && hasScore && video.category === PROMOTION_CATEGORY && score >= PROMOTION_SCORE_THRESHOLD

  return (
    <a
      href={`https://www.youtube.com/watch?v=${video.video_id}`}
      target="_blank"
      rel="noreferrer"
      className="block rounded-lg border border-gray-200 bg-white overflow-hidden hover:shadow-md transition-shadow"
    >
      <img src={video.thumbnail_url} alt={video.title} className="w-full aspect-video object-cover" />

      <div className="p-3 space-y-1">
        <h3 className="text-sm font-medium leading-snug line-clamp-2">{video.title}</h3>
        <p className="text-sm text-gray-600">{video.channel_name}</p>
        <p className="text-xs text-gray-500">{formatDate(video.published_at)}</p>

        <div className="flex gap-3 text-xs text-gray-700 pt-1">
          <span>{formatCount(video.views)} views</span>
          <span>{formatCount(video.likes)} likes</span>
          <span>{formatCount(video.comments)} comments</span>
        </div>

        {showScore && (
          <div className="pt-1 flex items-center gap-2">
            <span
              className="text-sm font-semibold"
              title={showPromotionNote ? PROMOTION_TOOLTIP : undefined}
            >
              Outlier Score: {formatScore(score)}
            </span>
            {video.is_still_growing && (
              <span className="text-xs text-blue-600 font-medium">still growing</span>
            )}
          </div>
        )}
      </div>
    </a>
  )
}
