import VideoCard from './VideoCard'

// Column counts per CLAUDE.md, mobile / tablet / laptop / wide. The category page and a
// homepage section use different counts, so both live here once instead of being
// duplicated in the two places that render a grid.
const GRID_COLUMNS = {
  page: {
    longform: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',
    shorts: 'grid-cols-3 sm:grid-cols-4 lg:grid-cols-5',
  },
  section: {
    longform: 'grid-cols-1 sm:grid-cols-3',
    shorts: 'grid-cols-3 lg:grid-cols-5',
  },
}

// Homepage Shorts sections always fetch 5; the 4th and 5th are hidden below the laptop
// breakpoint in CSS rather than by reading viewport size in JavaScript, so there is no
// screen-size state to keep in sync.
const HIDE_BELOW_LAPTOP_INDEX = 3

export default function VideoGrid({ videos, metric, comparison, format, variant, rankOffset = 0 }) {
  const columns = GRID_COLUMNS[variant][format]
  const isShort = format === 'shorts'

  return (
    <div className={`grid ${columns} gap-4`}>
      {videos.map((video, index) => {
        const hideBelowLaptop = variant === 'section' && isShort && index >= HIDE_BELOW_LAPTOP_INDEX
        // A 9:16 thumbnail at a section's grid-cell width would be noticeably taller
        // than a 16:9 long-form section's cards. Capping the card's own width (not its
        // height directly, which would fight the aspect-ratio class in VideoCard) keeps
        // a Shorts section roughly as tall as a long-form one, without touching VideoCard.
        const capWidth = variant === 'section' && isShort
        return (
          <div
            key={video.video_id}
            className={`${hideBelowLaptop ? 'hidden lg:block' : ''} ${capWidth ? 'max-w-[140px] mx-auto' : ''}`}
          >
            <VideoCard
              video={video}
              metric={metric}
              comparison={comparison}
              rank={rankOffset + index + 1}
              isShort={isShort}
            />
          </div>
        )
      })}
    </div>
  )
}
