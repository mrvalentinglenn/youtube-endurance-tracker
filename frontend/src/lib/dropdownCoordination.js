// FilterBar owns its own "which dropdown is open" state, and nothing outside it needs to
// read that state -- only to ask it to close. A custom window event is a smaller change
// than lifting that state up through both pages just for this one cross-component nudge:
// SuggestChannelButton (a header-level sibling of FilterBar on both routes) dispatches this
// when its modal opens; FilterBar listens for it alongside its existing mousedown/Escape
// handling.
export const CLOSE_FILTER_DROPDOWNS_EVENT = 'ete:close-filter-dropdowns'

export function closeAllFilterDropdowns() {
  window.dispatchEvent(new Event(CLOSE_FILTER_DROPDOWNS_EVENT))
}
