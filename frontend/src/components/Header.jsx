import ThemeToggle from './ThemeToggle'
import SuggestChannelButton from './SuggestChannelButton'
import HowItWorksButton from './HowItWorksButton'

// Shared by both routes (used to be duplicated in HomePage.jsx and CategoryPage.jsx).
// Below md, the title shrinks and can wrap to a second line rather than pushing the
// buttons around -- flex-1 min-w-0 lets it do that instead of overflowing, while
// flex-shrink-0 on the button group keeps the three (icon-only below md) buttons a
// fixed size on the same row. At md and up, every class here resolves to exactly the
// original "flex items-center justify-between mb-6" layout.
export default function Header() {
  return (
    <div className="flex items-start justify-between gap-2 mb-6 md:items-center">
      <h1 className="flex-1 min-w-0 text-lg font-bold md:text-2xl">YouTube Endurance Tracker</h1>
      <div className="flex items-center gap-2 flex-shrink-0">
        <HowItWorksButton />
        <SuggestChannelButton />
        <ThemeToggle />
      </div>
    </div>
  )
}
