import { useSearchParams } from 'react-router-dom'
import { CATEGORIES, resolveFilters, withParam } from '../lib/filters'
import FilterBar from '../components/FilterBar'
import CategorySection from '../components/CategorySection'
import ThemeToggle from '../components/ThemeToggle'
import SuggestChannelButton from '../components/SuggestChannelButton'
import HowItWorksButton from '../components/HowItWorksButton'

export default function HomePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = resolveFilters(searchParams)

  const visibleCategories = CATEGORIES.filter((c) => !filters.nocat.includes(c.slug))

  // The homepage's category on/off lives in nocat (deselected slugs). This is the one
  // interface FilterBar needs from the page: everything else it manages itself.
  const categoryState = {
    isOn: (slug) => !filters.nocat.includes(slug),
    setOn: (slug, on) => {
      setSearchParams((prev) => {
        const currentNocat = resolveFilters(prev).nocat
        const nextNocat = on ? currentNocat.filter((s) => s !== slug) : [...currentNocat, slug]
        return withParam(prev, 'nocat', nextNocat)
      })
    },
    offSlugsForChips: () => filters.nocat,
    clearAllTransform: (params) => withParam(params, 'nocat', []),
  }

  // nocat only means something on the homepage; "Show more" carries every other filter.
  const showMoreParams = new URLSearchParams(searchParams)
  showMoreParams.delete('nocat')
  const showMoreSearch = showMoreParams.toString()

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-6">
        <h1 className="text-2xl font-bold">YouTube Endurance Tracker</h1>
        <div className="flex items-center gap-2">
          <HowItWorksButton />
          <SuggestChannelButton />
          <ThemeToggle />
        </div>
      </div>

      <FilterBar categoryState={categoryState} />

      {visibleCategories.map((category) => (
        <CategorySection key={category.slug} category={category} filters={filters} showMoreSearch={showMoreSearch} />
      ))}
    </div>
  )
}
