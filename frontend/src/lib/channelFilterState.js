// Pure derivation and transition rules for the channel-filter tree (the five dropdowns
// and their chips). No React, no URL knowledge -- callers own nosub/nochan (and the
// page-specific category on/off flag) and the URL; these functions only compute the
// next value, so the rules can be read and checked independently of the UI.

export function isChannelExcluded(channelId, subcategory, nosub, nochan) {
  return nosub.includes(subcategory) || nochan.includes(channelId)
}

// 'checked' | 'unchecked' | 'partial'
export function subcategoryState(subcategoryName, channels, nosub, nochan) {
  if (nosub.includes(subcategoryName)) return 'unchecked'
  const anyExcluded = channels.some((c) => nochan.includes(c.channel_id))
  return anyExcluded ? 'partial' : 'checked'
}

// 'checked' | 'unchecked' | 'partial'. `on` is the page-specific on/off flag (nocat on
// the homepage, path membership on the category page). While off, the state is always
// 'unchecked' regardless of what's stored inside -- exclusions are inert, not reflected
// in the checkbox, until the category is switched back on.
export function categoryTriState(bucket, nosub, nochan, on) {
  if (!on) return 'unchecked'
  const anySubOff = Object.keys(bucket.subcategories).some((name) => nosub.includes(name))
  const anyChannelOff = bucket.channelIds.some((id) => nochan.includes(id))
  return anySubOff || anyChannelOff ? 'partial' : 'checked'
}

export function categoryCheckedCount(bucket, nosub, nochan) {
  let count = 0
  for (const [subName, subBucket] of Object.entries(bucket.subcategories)) {
    if (nosub.includes(subName)) continue
    for (const channel of subBucket.channels) {
      if (!nochan.includes(channel.channel_id)) count += 1
    }
  }
  return count
}

// Channel checkbox click. subcategoryChannels: every channel in the same subcategory
// (needed for the "re-check one channel inside an excluded subcategory" case). Returns
// the next { nosub, nochan }.
export function toggleChannel(channel, subcategoryName, subcategoryChannels, nosub, nochan) {
  const subExcluded = nosub.includes(subcategoryName)
  const directlyExcluded = nochan.includes(channel.channel_id)
  const effectivelyChecked = !subExcluded && !directlyExcluded

  if (effectivelyChecked) {
    return { nosub, nochan: [...nochan, channel.channel_id] }
  }

  if (subExcluded) {
    // The subcategory can no longer speak for all of its channels once one is
    // individually re-checked, so it comes off nosub and every OTHER channel in it
    // goes onto nochan individually, preserving their exclusion.
    const others = subcategoryChannels
      .filter((c) => c.channel_id !== channel.channel_id)
      .map((c) => c.channel_id)
    return {
      nosub: nosub.filter((s) => s !== subcategoryName),
      nochan: [...nochan.filter((id) => id !== channel.channel_id), ...others],
    }
  }

  return { nosub, nochan: nochan.filter((id) => id !== channel.channel_id) }
}

// Subcategory checkbox click (checked <-> {unchecked, partial}). Checked -> unchecked
// adds the name to nosub. Unchecked or partial -> checked removes it. Either direction
// also drops this subcategory's channels from nochan: on the way out they're now
// redundant (nosub already covers them); on the way in they'd otherwise leave it
// looking partial immediately after the click.
export function toggleSubcategory(subcategoryName, channels, nosub, nochan) {
  const channelIds = channels.map((c) => c.channel_id)
  const currentlyOff = nosub.includes(subcategoryName)
  const nextNosub = currentlyOff
    ? nosub.filter((s) => s !== subcategoryName)
    : [...nosub, subcategoryName]
  const nextNochan = nochan.filter((id) => !channelIds.includes(id))
  return { nosub: nextNosub, nochan: nextNochan }
}

// Category checkbox click when its current tri-state is 'partial': clears every
// exclusion stored inside it. The checked<->unchecked transitions don't call this --
// they only flip the page-specific on/off flag and leave nosub/nochan untouched, so
// exclusions "apply again" if the category is turned back on later.
export function clearCategoryExclusions(bucket, nosub, nochan) {
  const subNames = new Set(Object.keys(bucket.subcategories))
  const channelIds = new Set(bucket.channelIds)
  return {
    nosub: nosub.filter((s) => !subNames.has(s)),
    nochan: nochan.filter((id) => !channelIds.has(id)),
  }
}
