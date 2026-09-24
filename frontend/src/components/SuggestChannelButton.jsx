import { useEffect, useRef, useState } from 'react'
import { CATEGORIES } from '../lib/filters'
import { closeAllFilterDropdowns } from '../lib/dropdownCoordination'
import { PlusIcon } from './icons'

const WEB3FORMS_URL = 'https://api.web3forms.com/submit'
const ACCESS_KEY = import.meta.env.VITE_WEB3FORMS_ACCESS_KEY
const MAX_NAME_LENGTH = 100

const STATUS = { IDLE: 'idle', SENDING: 'sending', SUCCESS: 'success', ERROR: 'error' }

const ERROR_MESSAGE = "Something went wrong sending your suggestion. Please try again."

// A form the browser is asked to submit via fetch, not a native GET/POST -- but the
// honeypot only works against bots that scan the page's inputs and fill them in, which
// doesn't care how the result is eventually sent. botcheck stays a real, rendered input,
// just one no sighted user or screen reader ever encounters.
function Honeypot({ inputRef }) {
  return (
    <input
      ref={inputRef}
      type="text"
      name="botcheck"
      tabIndex={-1}
      autoComplete="off"
      aria-hidden="true"
      className="hidden"
    />
  )
}

export default function SuggestChannelButton() {
  const [isOpen, setIsOpen] = useState(false)
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState(STATUS.IDLE)

  const modalRef = useRef(null)
  const nameInputRef = useRef(null)
  const honeypotRef = useRef(null)

  useEffect(() => {
    if (!ACCESS_KEY) {
      console.warn(
        'VITE_WEB3FORMS_ACCESS_KEY is not set -- "Suggest a channel" is hidden. ' +
          'The rest of the site is unaffected.'
      )
    }
  }, [])

  useEffect(() => {
    if (!isOpen) return undefined
    // Focus the name field on open, matching the spec; a tick after mount so the input
    // actually exists in the DOM the moment this runs.
    nameInputRef.current?.focus()

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
    setName('')
    setCategory('')
    setStatus(STATUS.IDLE)
  }

  const trimmedName = name.trim()
  const canSubmit = trimmedName.length > 0 && category !== '' && status !== STATUS.SENDING

  async function handleSubmit(e) {
    e.preventDefault()
    if (!canSubmit) return

    setStatus(STATUS.SENDING)
    try {
      const response = await fetch(WEB3FORMS_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_key: ACCESS_KEY,
          subject: `Channel suggestion: ${trimmedName}`,
          from_name: 'YouTube Endurance Tracker',
          channel_name: trimmedName,
          category,
          botcheck: honeypotRef.current ? honeypotRef.current.value : '',
        }),
      })
      const result = await response.json()
      if (result.success) {
        setName('')
        setCategory('')
        setStatus(STATUS.SUCCESS)
      } else {
        setStatus(STATUS.ERROR)
      }
    } catch {
      setStatus(STATUS.ERROR)
    }
  }

  if (!ACCESS_KEY) return null

  return (
    <>
      <button
        type="button"
        onClick={openModal}
        aria-label="Suggest a channel"
        title="Suggest a channel"
        className="flex items-center justify-center w-10 h-10 rounded border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 md:w-auto md:h-auto md:justify-start md:gap-1.5 md:whitespace-nowrap md:px-2.5 md:py-1.5 md:text-sm"
      >
        <PlusIcon className="w-5 h-5 md:hidden" aria-hidden="true" />
        <span className="hidden md:inline">Suggest a channel</span>
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div
            ref={modalRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="suggest-channel-heading"
            className="w-full max-w-md rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-lg p-5"
          >
            <h2 id="suggest-channel-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">
              Suggest a channel
            </h2>

            {status === STATUS.SUCCESS ? (
              <>
                <p className="text-sm text-gray-800 dark:text-gray-200">
                  Thanks! Your suggestion has been sent.
                </p>
                <div className="mt-4 flex justify-end">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="px-3 py-1 rounded border text-sm border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-300"
                  >
                    Close
                  </button>
                </div>
              </>
            ) : (
              <form onSubmit={handleSubmit}>
                <Honeypot inputRef={honeypotRef} />

                {status === STATUS.ERROR && (
                  <p className="text-sm text-red-600 dark:text-red-400 mb-3">{ERROR_MESSAGE}</p>
                )}

                <label className="block text-sm text-gray-700 dark:text-gray-300 mb-1" htmlFor="suggest-channel-name">
                  Channel name
                </label>
                <input
                  ref={nameInputRef}
                  id="suggest-channel-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={MAX_NAME_LENGTH}
                  className="w-full border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 rounded px-2 py-1 text-sm mb-3"
                />

                <label className="block text-sm text-gray-700 dark:text-gray-300 mb-1" htmlFor="suggest-channel-category">
                  Category
                </label>
                <select
                  id="suggest-channel-category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  required
                  className="w-full border border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 rounded px-2 py-1 text-sm mb-4"
                >
                  <option value="" disabled>
                    Choose a category
                  </option>
                  {CATEGORIES.map((c) => (
                    <option key={c.slug} value={c.displayName}>
                      {c.displayName}
                    </option>
                  ))}
                </select>

                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="px-3 py-1 rounded border text-sm border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-300"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!canSubmit}
                    className="px-3 py-1 rounded border text-sm border-gray-900 dark:border-gray-100 bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {status === STATUS.SENDING ? 'Sending…' : 'Send'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  )
}
