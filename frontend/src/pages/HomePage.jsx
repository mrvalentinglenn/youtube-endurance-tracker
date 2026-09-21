import { useSearchParams } from 'react-router-dom'
import { CATEGORIES, resolveFilters } from '../lib/filters'
import FilterBar from '../components/FilterBar'
import HomeCategoryToggles from '../components/HomeCategoryToggles'
import CategorySection from '../components/CategorySection'
import ThemeToggle from '../components/ThemeToggle'

export default function HomePage() {
  const [searchParams] = useSearchParams()
  const filters = resolveFilters(searchParams)

  const visibleCategories = CATEGORIES.filter((c) => !filters.nocat.includes(c.slug))

  // nocat only means something on the homepage; "Show more" carries every other filter.
  const showMoreParams = new URLSearchParams(searchParams)
  showMoreParams.delete('nocat')
  const showMoreSearch = showMoreParams.toString()

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">YouTube Endurance Tracker</h1>
        <ThemeToggle />
      </div>

      <FilterBar />
      <HomeCategoryToggles />

      {visibleCategories.map((category) => (
        <CategorySection key={category.slug} category={category} filters={filters} showMoreSearch={showMoreSearch} />
      ))}
    </div>
  )
}
