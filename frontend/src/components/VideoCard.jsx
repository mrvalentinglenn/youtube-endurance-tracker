const SCORE_COLUMNS = { views: 'score_views', likes: 'score_likes', comments: 'score_comments' }

const PROMOTION_CATEGORY = 'Brand'
const PROMOTION_SCORE_THRESHOLD = 500
const PROMOTION_TOOLTIP =
  'Extreme outlier scores may indicate this video was used for paid advertising.'
const PROMOTION_BODY_LINE =
  'Metrics on this video may reflect paid advertising rather than organic reach.'

function isPromotionFlagged(video) {
  // Reads all three score columns, not just the displayed metric: the flag is a property
  // of the video, fixed regardless of which metric the user is looking at (CLAUDE.md,
  // DECISIONS.md 2026-09-20 "The paid-promotion trigger reads all three score columns").
  if (video.category !== PROMOTION_CATEGORY) return false
  return [video.score_views, video.score_likes, video.score_comments].some(
    (score) => score !== null && score !== undefined && score >= PROMOTION_SCORE_THRESHOLD
  )
}

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
  if (score >= 1000) return `${(score / 1000).toFixed(1)}K×`
  return `${score.toFixed(1)}×`
}

function formatDuration(seconds) {
  // NULL or 0 (the API's P0D, meaning "unavailable", not "zero seconds") shows no badge.
  if (!seconds) return null
  const total = Math.floor(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  const mm = hours > 0 ? String(minutes).padStart(2, '0') : minutes
  const ss = String(secs).padStart(2, '0')
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
}

function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-3.5 h-3.5">
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function CommentIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5">
      <path d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-4 4v-4H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" />
    </svg>
  )
}

function HeartIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5">
      <path d="M12 21s-7.5-4.6-10-9.1C.5 8.8 2 5 5.8 5c2 0 3.5 1.1 4.2 2.4C10.7 6.1 12.2 5 14.2 5 18 5 19.5 8.8 22 11.9 19.5 16.4 12 21 12 21z" />
    </svg>
  )
}

export default function VideoCard({ video, metric, comparison, rank, isShort }) {
  const flagged = isPromotionFlagged(video)
  const score = video[SCORE_COLUMNS[metric]]
  const durationText = formatDuration(video.duration_seconds)

  // Under Relative the badge always holds the score. Under Absolute it is absent unless
  // the video is flagged, in which case it holds the exclamation mark alone.
  const showScoreBadge = comparison === 'relative' || flagged

  return (
    <a
      href={`https://www.youtube.com/watch?v=${video.video_id}`}
      target="_blank"
      rel="noreferrer"
      className="block w-full"
    >
      <div className="text-xs font-semibold text-gray-500 mb-1">#{rank}</div>

      <div className={`relative w-full ${isShort ? 'aspect-[9/16]' : 'aspect-video'} rounded-lg overflow-hidden bg-gray-100`}>
        <img
          src={video.thumbnail_url}
          alt={video.title}
          className="absolute inset-0 w-full h-full object-cover"
        />

        {showScoreBadge && (
          <div
            className={`absolute top-2 left-2 rounded px-1.5 py-0.5 text-xs font-semibold text-white ${
              flagged ? 'bg-red-600' : 'bg-black/80'
            }`}
            title={flagged ? PROMOTION_TOOLTIP : undefined}
          >
            {comparison === 'relative' ? formatScore(score) : ''}
            {flagged && <span>!</span>}
          </div>
        )}

        {video.is_still_growing && (
          <div className="absolute top-2 right-2 rounded px-1.5 py-0.5 text-xs font-semibold text-white bg-orange-500">
            still growing
          </div>
        )}

        {durationText && (
          <div className="absolute bottom-2 right-2 rounded px-1.5 py-0.5 text-xs font-medium text-white bg-black/80">
            {durationText}
          </div>
        )}
      </div>

      <div className="p-2 space-y-1">
        <h3 className="text-sm font-medium leading-snug line-clamp-2">{video.title}</h3>
        <p className="text-sm text-gray-600">{video.channel_name}</p>
        <p className="text-xs text-gray-500">{formatDate(video.published_at)}</p>

        <div className="flex gap-3 text-xs text-gray-700 pt-1">
          <span className="flex items-center gap-1">
            <EyeIcon /> {formatCount(video.views)}
          </span>
          <span className="flex items-center gap-1">
            <CommentIcon /> {formatCount(video.comments)}
          </span>
          <span className="flex items-center gap-1">
            <HeartIcon /> {formatCount(video.likes)}
          </span>
        </div>

        {flagged && <p className="text-xs text-red-600 pt-1">{PROMOTION_BODY_LINE}</p>}
      </div>
    </a>
  )
}
