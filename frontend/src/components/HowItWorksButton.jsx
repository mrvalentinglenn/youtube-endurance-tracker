import { useEffect, useRef, useState } from 'react'
import { closeAllFilterDropdowns } from '../lib/dropdownCoordination'
import { QuestionMarkIcon } from './icons'

export default function HowItWorksButton() {
  const [isOpen, setIsOpen] = useState(false)
  const modalRef = useRef(null)

  useEffect(() => {
    if (!isOpen) return undefined

    function handlePointerDown(e) {
      if (modalRef.current && !modalRef.current.contains(e.target)) {
        closeModal()
      }
    }
    function handleKeyDown(e) {
      if (e.key === 'Escape') closeModal()
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  function openModal() {
    closeAllFilterDropdowns()
    setIsOpen(true)
  }

  function closeModal() {
    setIsOpen(false)
  }

  return (
    <>
      <button
        type="button"
        onClick={openModal}
        aria-label="How it works"
        title="How it works"
        className="flex items-center justify-center w-10 h-10 rounded border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 md:w-auto md:h-auto md:justify-start md:gap-1.5 md:whitespace-nowrap md:px-2.5 md:py-1.5 md:text-sm"
      >
        <QuestionMarkIcon className="w-5 h-5 md:hidden" aria-hidden="true" />
        <span className="hidden md:inline">How it works</span>
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div
            ref={modalRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="how-it-works-heading"
            className="w-full max-w-md rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-lg p-5"
          >
            <h2 id="how-it-works-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">
              How it works
            </h2>

            <div className="space-y-3 text-sm text-gray-700 dark:text-gray-300">
              <p>
                The YouTube Endurance Tracker ranks the best-performing videos from more than 330
                YouTube channels in swimming, cycling, running and triathlon, across five
                categories: brands, professional teams, influencers, professional athletes and
                race organizers.
              </p>
              <p>
                Views, likes and comments are tracked until a video is 180 days old, then frozen.
                Since most videos gain few views after that, the count at 180 days is a good
                stand-in for all-time views.
              </p>
              <p>
                <strong>Absolute</strong> ranks videos by their raw numbers. <strong>Relative</strong>{' '}
                shows how well a video performed compared with a normal video from the same
                channel. A high relative score usually points to a strong thumbnail, title,
                subject, and/or storyline.
              </p>
            </div>

            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={closeModal}
                className="px-3 py-1 rounded border text-sm border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-300"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
