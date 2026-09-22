import { supabase } from './supabase'

// The standard Snowball-project stopword lists -- the same lists Postgres's own built-in
// per-language configs ship with -- merged across the six languages this channel set
// publishes in. Used only to decide which words to drop from a multi-word keyword search
// before it reaches Postgres; the stored fts column stays 'simple' (no stemming, no
// built-in stopword removal) so one configuration keeps serving every language equally.
// See NEXT_STEPS.md step 10f's keyword-search investigation: stripping stopwords from a
// multi-word query is both a real performance win (fewer candidate rows for Postgres to
// re-check) and a relevance win (a phrase like "the best gear to run" stops requiring the
// literal words "the" and "to" to appear).
const ENGLISH = `i me my myself we our ours ourselves you your yours yourself yourselves he him
his himself she her hers herself it its itself they them their theirs themselves what which who
whom this that these those am is are was were be been being have has had having do does did
doing a an the and but if or because as until while of at by for with about against between into
through during before after above below to from up down in out on off over under again further
then once here there when where why how all any both each few more most other some such no nor
not only own same so than too very s t can will just don should now`.split(/\s+/)

const SPANISH = `de la que el en y a los del se las por un para con no una su al lo como mas o
pero sus le ya este si porque esta entre cuando muy sin sobre tambien me hasta hay donde quien
desde todo nos durante todos uno les ni contra otros ese eso ante ellos esto mi antes algunos
unos yo otro otras otra tanto esa estos mucho quienes nada muchos cual poco ella estar estas
algunas algo nosotros mis tu tus te ti tuyo`.split(/\s+/)

const GERMAN = `aber alle allem allen aller als also am an auch auf aus bei bin bis bist da
damit dann der den des dem die das dass du er es fuer gegen gewesen hab habe haben hat hatte
hatten hier hin hinter ich ihr ihre ihrem ihren ihrer ihres im in ist jetzt kann kein keine
keinem keinen keiner keines koennen konnte machen man mein meine mich mir mit muss musste nach
nicht nichts noch nun nur ob oder ohne sehr sein seine sich sie sind so um und uns unser unter
viel vom von vor war waren was weiter weitere wenn werde werden wie wieder will wir wird wirst wo
zu zum zur zwischen`.split(/\s+/)

const DUTCH = `de en van ik te dat die in een hij het niet zijn is was op aan met als voor had
er maar om hem dan zou of wat mijn men dit zo door over ze zich bij ook tot je mij uit der daar
haar naar heb hoe heeft hebben deze u want nog zal me zij nu ge geen omdat iets worden toch al
waren veel meer doen toen moet ben zonder kan hun dus alles onder ja eens hier wie werd altijd
doch wordt wezen kunnen ons zelf tegen na reeds wil kon niets uw iemand geweest andere`.split(/\s+/)

const FRENCH = `au aux avec ce ces dans de des du elle en et eux il je la le leur lui ma mais
me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes
toi ton tu un une vos votre vous c d j l a s y etant etais etait etaient suis es est sommes etes
sont serai seras sera serons serez seront ai as avons avez ont avais avait avions aviez avaient
aurai auras aura aurons aurez auront cette`.split(/\s+/)

const ITALIAN = `ad al allo ai agli all alla alle con col coi da dal dallo dai dagli dall dalla
dalle di del dello dei degli dell della delle in nel nello nei negli nell nella nelle su sul
sullo sui sugli sull sulla sulle per tra contra io tu lui lei noi voi loro mio mia miei mie tuo
tua tuoi tue suo sua suoi sue nostro nostra nostri nostre vostro vostra vostri vostre mi ti ci vi
lo la li le gli ne il un uno una ma ed se perche anche come dov dove che chi cui non piu quale
quanto quanti quanta quante quello quelli quella quelle questo questi questa queste si tutto
tutti c e i l o ho hai ha abbiamo avete hanno`.split(/\s+/)

const MERGED_STOPWORDS = new Set(
  [...ENGLISH, ...SPANISH, ...GERMAN, ...DUTCH, ...FRENCH, ...ITALIAN].map((w) => w.toLowerCase())
)

// Fetched once per browser session and cached: channel names rarely change, and a search
// shouldn't pay a network round trip just to decide which words are safe to strip. A
// failed fetch leaves the promise unset so the next call retries rather than caching a
// permanent empty result.
let channelNamesPromise = null

function fetchChannelNames() {
  if (!channelNamesPromise) {
    channelNamesPromise = supabase
      .from('channels_public')
      .select('name')
      .then(({ data, error }) => {
        if (error) {
          channelNamesPromise = null
          return new Set()
        }
        return new Set(data.map((c) => c.name.trim().toLowerCase()))
      })
  }
  return channelNamesPromise
}

// A word that is also a channel's name (e.g. "On", the running-shoe brand) must never be
// stripped: "on shoes" silently becoming a search for just "shoes" would lose exactly the
// brand the user typed to find.
async function getEffectiveStopwords() {
  const channelNames = await fetchChannelNames()
  if (channelNames.size === 0) return MERGED_STOPWORDS
  const effective = new Set(MERGED_STOPWORDS)
  for (const name of channelNames) {
    effective.delete(name)
  }
  return effective
}

/**
 * Strips stopwords from a keyword search, but only for a query of two or more words. A
 * single word is always searched exactly as typed (so "the" alone still searches for "the"
 * -- the fix for that case is the slim, category-ordered videos_search view it now runs
 * against, not this). A phrase that turns out to be stopwords only is searched as typed
 * too, rather than being emptied into something that would match nothing intended.
 */
export async function stripStopwordsForSearch(rawQuery) {
  const words = rawQuery.trim().split(/\s+/).filter(Boolean)
  if (words.length < 2) return rawQuery.trim()

  const stopwords = await getEffectiveStopwords()
  const kept = words.filter((w) => !stopwords.has(w.toLowerCase()))
  return kept.length > 0 ? kept.join(' ') : rawQuery.trim()
}
